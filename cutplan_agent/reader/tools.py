"""The reader stages as tools for a model that orchestrates them (orchestrator.py).

A tool takes JSON arguments and returns a small JSON dict: the stage status, the stage's
describe() summary and its model calls, never the whole stage file (01_read.json alone holds
every DXF entity). The stage functions are the ones in stages/*.py, so a tool call writes the
same files as the stage script or `main.py --batch`.

Tools:
  list_drawings      DXF files under a folder, with the workspace each one gets
  stage_status       which stages a workspace has, and their status
  show_stage         one stage's summary, review items and model replies
  run_<stage>        one stage (run_read ... run_develop; with three_d also the 3D stages
                     run_reconstruct, run_confirm, run_export)
  run_stages         a range of stages in order, like stages/run.py

The models the stages call (OCR, reasoning) are fixed when the tools are built; the
orchestrating model only picks stages and their options. Workspaces must lie under the
output folder, so a tool cannot write anywhere else.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cutplan_agent.reader.stages.run import MODULES, run_drawing
from cutplan_agent.reader.stages.workspace import (
    STAGES,
    THREE_D,
    StageNotReady,
    Workspace,
    headline,
)
from cutplan_agent.reader.vlm import VLMClient

# Stage options the orchestrator may set, as JSON Schema properties. Model clients are not
# among them: they come from the command line or the CUTPLAN_* environment.
STAGE_OPTIONS: dict[str, dict[str, dict]] = {
    "read": {"drawing": {"type": "string", "description": "DXF file path"}},
    "views": {
        "gap_ratio": {
            "type": "number",
            "description": "gap that separates view clusters, as a fraction of the sheet "
            "diagonal (default 0.008)",
        }
    },
    "view_labels": {
        "projection_default": {
            "type": "string",
            "enum": ["first", "third"],
            "description": "projection when neither the title block nor the model "
            "decides (default third)",
        }
    },
    "document": {
        "units": {
            "type": "string",
            "enum": ["mm", "cm", "m", "inch"],
            "description": "override the drawing units",
        }
    },
    "reconstruct": {
        "tolerance": {"type": "number", "description": "geometric tolerance"},
        "max_candidates": {
            "type": "integer",
            "description": "candidates to keep (default 10)",
        },
    },
}
REQUIRED = {"read": ["drawing"]}
# Which model client each model stage receives.
CLIENT_ROLE = {
    "title_ocr": "ocr",
    "title_fields": "reason",
    "view_labels": "reason",
    "unfold_params": "reason",
    "confirm": "reason",
}
WORK = {
    "type": "string",
    "description": "drawing workspace, e.g. the `work` that list_drawings returns",
}
STAGE_NAME = {"type": "string", "enum": list(STAGES)}
RAW_LIMIT = 1500  # characters of a model reply that show_stage returns


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema of the arguments object
    call: Callable[..., dict]


def stage_description(stage: str) -> str:
    """The stage script's summary paragraph and its `in :` line."""
    doc = inspect.getdoc(MODULES[stage]) or stage
    summary = " ".join(doc.split("\n\n")[0].split())
    reads = next(
        (line for line in doc.splitlines() if line.startswith("in ")), ""
    ).strip()
    return f"{summary} Reads {reads.split(':', 1)[1].strip()}." if reads else summary


def schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def model_calls(record: dict) -> list[dict]:
    """The model calls a stage made: role, task, ok and the error when it failed."""
    calls = []
    for role, entries in (record.get("trace") or {}).items():
        for entry in entries:
            call = {"role": role, "task": entry.get("task"), "ok": entry.get("ok")}
            if entry.get("error"):
                call["error"] = entry["error"]
            calls.append(call)
    return calls


def stage_result(ws: Workspace, record: dict) -> dict:
    stage = record["stage"]
    out = {
        "stage": stage,
        "status": record["status"],
        "headline": headline(record),
        "file": str(ws.path(stage)),
    }
    if record["status"] == "done":
        out["summary"] = MODULES[stage].describe(record)
    calls = model_calls(record)
    if calls:
        out["model_calls"] = calls
    return out


class ReaderTools:
    def __init__(
        self,
        output_dir: str | Path,
        clients: tuple[VLMClient, VLMClient],
        input_dir: str | Path = "data_v3/synthetic",
        three_d: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.input_dir = Path(input_dir)
        self.clients = {"ocr": clients[0], "reason": clients[1]}
        # The 3D stages get no tool and run_stages skips them unless three_d
        # (docs/v3_upgrade.md 1.1).
        self.three_d = three_d
        self.stages = tuple(s for s in STAGES if three_d or s not in THREE_D)
        self.tools = {t.name: t for t in self._build()}

    # ------------------------------------------------------------------ dispatch
    def call(self, name: str, arguments: Any) -> dict:
        """Run one tool. Every failure comes back as {"error": ...}, never as an exception,
        so the model sees it and can try something else."""
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"unknown tool {name!r}; tools: {sorted(self.tools)}"}
        if not isinstance(arguments, dict):
            return {"error": "arguments must be a JSON object"}
        props = tool.parameters["properties"]
        unknown = sorted(set(arguments) - set(props))
        missing = [k for k in tool.parameters["required"] if k not in arguments]
        if unknown or missing:
            return {
                "error": f"unknown arguments {unknown}, missing arguments {missing}; "
                f"{name} takes {sorted(props)}"
            }
        try:
            return tool.call(**arguments)
        except StageNotReady as exc:
            return {"status": "not_ready", "error": str(exc)}
        except Exception as exc:
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    def workspace(self, work: str) -> Workspace:
        """A workspace under the output folder. A relative path is taken from the current
        folder when it already points under the output folder, otherwise from the output
        folder, so both `runs/reader/agent/x` and `x` work."""
        root = self.output_dir.resolve()
        path = Path(work)
        if not path.is_absolute() and not (Path.cwd() / path).resolve().is_relative_to(
            root
        ):
            path = root / path
        path = path.resolve()
        if not path.is_relative_to(root) or path == root:
            raise ValueError(f"work must be a folder under {self.output_dir}")
        return Workspace(path)

    # ------------------------------------------------------------------ tools
    def _build(self) -> list[Tool]:
        tools = [
            Tool(
                "list_drawings",
                "List the DXF drawings under a folder (default: the input folder) with "
                "the workspace each one uses and the stages it already has.",
                schema(
                    {
                        "folder": {"type": "string", "description": "folder to search"},
                        "name": {
                            "type": "string",
                            "description": "only drawings whose file name contains this",
                        },
                    },
                    [],
                ),
                self.list_drawings,
            ),
            Tool(
                "stage_status",
                "Status of every stage in a workspace: done, skipped (with the reason), "
                "failed (with the error) or not run.",
                schema({"work": WORK}, ["work"]),
                self.stage_status,
            ),
            Tool(
                "show_stage",
                "One stage's summary, review items and model calls with the start of "
                "each raw model reply.",
                schema({"work": WORK, "stage": STAGE_NAME}, ["work", "stage"]),
                self.show_stage,
            ),
        ]
        run_names = {"type": "string", "enum": list(self.stages)}
        for stage in self.stages:
            tools.append(
                Tool(
                    f"run_{stage}",
                    stage_description(stage)
                    + " Running a stage deletes the stage files after it.",
                    schema(
                        {"work": WORK, **STAGE_OPTIONS.get(stage, {})},
                        ["work", *REQUIRED.get(stage, [])],
                    ),
                    self._stage_caller(stage),
                )
            )
        tools.append(
            Tool(
                "run_stages",
                "Run the stages from `first` to `last` in order, each on the files the "
                "previous one wrote (stages/run.py). Stops at the first failure.",
                schema(
                    {
                        "work": WORK,
                        "first": {**run_names, "description": "default read"},
                        "last": {
                            **run_names,
                            "description": f"default {self.stages[-1]}",
                        },
                        "drawing": {
                            "type": "string",
                            "description": "DXF file path; needed when first is read",
                        },
                    },
                    ["work"],
                ),
                self.run_stages,
            )
        )
        return tools

    def _stage_caller(self, stage: str) -> Callable[..., dict]:
        module = MODULES[stage]
        role = CLIENT_ROLE.get(stage)

        def call(work: str, **options) -> dict:
            ws = self.workspace(work)
            if stage == "read":
                drawing = Path(options.pop("drawing"))
                if drawing.suffix.lower() != ".dxf" or not drawing.is_file():
                    return {"error": f"{drawing} is not a DXF file"}
                return stage_result(ws, module.run(ws, drawing))
            if role:
                options[role] = self.clients[role]
            return stage_result(ws, module.run(ws, **options))

        return call

    def list_drawings(self, folder: str | None = None, name: str | None = None) -> dict:
        base = Path(folder) if folder else self.input_dir
        if not base.is_dir():
            return {"error": f"{base} is not a folder"}
        files = sorted(p for p in base.rglob("*") if p.suffix.lower() == ".dxf")
        if name:
            files = [p for p in files if name.lower() in p.name.lower()]
        drawings = []
        for path in files:
            ws = Workspace(self.output_dir / path.stem)
            drawings.append(
                {
                    "id": path.stem,
                    "drawing": str(path),
                    "work": str(ws.root),
                    "stages_done": [s for s in STAGES if ws.has(s)],
                }
            )
        return {"folder": str(base), "count": len(drawings), "drawings": drawings}

    def stage_status(self, work: str) -> dict:
        ws = self.workspace(work)
        stages = {}
        for stage in STAGES:
            if not ws.has(stage):
                stages[stage] = "not run"
                continue
            record = json.loads(ws.path(stage).read_text(encoding="utf-8"))
            why = record.get("reason") or record.get("error")
            stages[stage] = record["status"] + (f" ({why})" if why else "")
        return {"work": str(ws.root), "stages": stages}

    def show_stage(self, work: str, stage: str) -> dict:
        ws = self.workspace(work)
        if stage not in STAGES:
            return {"error": f"unknown stage {stage!r}"}
        if not ws.has(stage):
            return {"stage": stage, "status": "not run"}
        record = json.loads(ws.path(stage).read_text(encoding="utf-8"))
        out = stage_result(ws, record)
        for key in ("reason", "error"):
            if record.get(key):
                out[key] = record[key]
        if record.get("review"):
            out["review"] = record["review"]
        replies = [
            {
                "role": role,
                "task": t.get("task"),
                "raw": (t.get("raw") or "")[:RAW_LIMIT],
            }
            for role, entries in (record.get("trace") or {}).items()
            for t in entries
            if t.get("raw")
        ]
        if replies:
            out["model_replies"] = replies
        return out

    def run_stages(
        self,
        work: str,
        first: str = "read",
        last: str | None = None,
        drawing: str | None = None,
    ) -> dict:
        last = last or self.stages[-1]
        ws = self.workspace(work)
        if first not in self.stages or last not in self.stages:
            return {"error": f"stages are {list(self.stages)}"}
        if STAGES.index(first) > STAGES.index(last):
            return {"error": "first comes after last"}
        if first == "read" and not drawing:
            return {"error": "the read stage needs `drawing`"}
        done: list[dict] = []
        try:
            run_drawing(
                drawing,
                ws.root,
                (self.clients["ocr"], self.clients["reason"]),
                first=first,
                last=last,
                three_d=self.three_d,
                on_stage=lambda stage, record: done.append(stage_result(ws, record)),
            )
        except StageNotReady as exc:
            return {"status": "not_ready", "error": str(exc), "stages": done}
        except Exception as exc:
            return {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "stages": done,
            }
        return {"status": "done", "stages": done}
