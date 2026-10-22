"""Per-drawing workspace shared by the reader stage scripts.

<work>/stages/NN_<stage>.json   one file per stage: status, inputs read, model calls, results
<work>/analysis/                title_block.png, sheet_labeled.png, sheet.png, sheet_analysis.json,
                                candidates.png (same place as before the stage split)
<work>/flat_pattern.*, provenance.json, report.md, reconstruction.step, parameters.json

A stage reads earlier stage files, never in-memory objects, so running the scripts one by
one gives the same files as `main.py --batch`. Saving a stage deletes the files of the
stages after it: a stage file that exists was computed from the current upstream files.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import tempfile
from copy import copy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from cutplan_agent.reader.dxf_adapter import TitleBlock, ViewCandidate
from cutplan_agent.reader.dxf_reader import RawEntity
from cutplan_agent.reader.vlm import VLMClient, VLMConfig, make_clients
from cutplan_agent.reconstruct.models import DrawingDocument, ReconstructionResult

# Order of the DXF stages; the file name of a stage is <index+1>_<name>.json.
STAGES = (
    "read",
    "title_regex",
    "title_ocr",
    "title_fields",
    "views",
    "view_labels",
    "sheet",
    "document",
    "unfold_params",
    "develop",
    "reconstruct",
    "confirm",
    "export",
)
# Optional stage before the DXF chain (stages/convert.py): DWG or DXF -> the DXF that read opens.
# Its file is 00_convert.json. It is not in STAGES, so main.py --batch and stages/run.py, which
# start at read with a DXF, do not run it.
CONVERT = "convert"


def step_number(stage: str) -> int:
    """0 for convert, 1-13 for the DXF stages."""
    return 0 if stage == CONVERT else STAGES.index(stage) + 1


class StageNotReady(RuntimeError):
    """An input stage has not run in this workspace, or it failed."""


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.stages_dir = self.root / "stages"
        self.analysis_dir = self.root / "analysis"
        self._inputs: list[str] = []

    def path(self, stage: str) -> Path:
        return self.stages_dir / f"{step_number(stage):02d}_{stage}.json"

    def has(self, stage: str) -> bool:
        return self.path(stage).is_file()

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def read_json(self, path: Path) -> Any:
        self._inputs.append(self._rel(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def load(self, stage: str) -> dict:
        path = self.path(stage)
        if not path.is_file():
            raise StageNotReady(
                f"{path} not found: run cutplan_agent/reader/stages/{stage}.py first"
            )
        record = self.read_json(path)
        if record["status"] == "failed":
            raise StageNotReady(f"{path}: {stage} failed ({record.get('error')})")
        return record

    def save(self, stage: str, data: dict) -> dict:
        index = step_number(stage) - 1
        record = {
            "stage": stage,
            "step": index + 1,
            **data,
            "inputs": sorted(set(self._inputs)),
        }
        self._inputs = []
        write_json(self.path(stage), record)
        for later in STAGES[index + 1 :]:
            self.path(later).unlink(missing_ok=True)
        return record

    # ------------------------------------------------------------------ shared inputs
    def entities(self) -> list[RawEntity]:
        return entities_from_json(self.load("read")["entities"])

    def analysis(self) -> dict:
        """sheet_analysis.json written by the sheet stage."""
        self.load("sheet")
        return self.read_json(self.analysis_dir / "sheet_analysis.json")

    def document(self) -> DrawingDocument | None:
        """The orthographic document, or None when the document stage did not build one."""
        if not self.has("document"):
            return None
        stage = self.load("document")
        if stage["status"] != "done":
            return None
        return DrawingDocument.from_dict(stage["document"], stage["document"]["source"])


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, default=list)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return path


# ---------------------------------------------------------------------- (de)serialization
def box(value) -> tuple | None:
    return tuple(value) if value is not None else None


def entities_to_json(entities: list[RawEntity]) -> list[dict]:
    return [asdict(e) for e in entities]


def entities_from_json(items: list[dict]) -> list[RawEntity]:
    return [
        RawEntity(
            **{
                **item,
                "points": [tuple(p) for p in item["points"]],
                "center": box(item["center"]),
                "attributes": {
                    k: tuple(v) if isinstance(v, list) else v
                    for k, v in item["attributes"].items()
                },
            }
        )
        for item in items
    ]


def views_to_json(views: list[ViewCandidate], entities: list[RawEntity]) -> list[dict]:
    """View clusters with their entities as indices into the read stage's list."""
    index = {id(e): i for i, e in enumerate(entities)}
    return [
        {
            "id": v.id,
            "bbox": v.bbox,
            "label": v.label,
            "confidence": v.confidence,
            "label_source": v.label_source,
            "reason": v.reason,
            "counts": v.counts(),
            "entities": [index[id(e)] for e in v.entities],
            "dimensions": [index[id(e)] for e in v.dimensions],
            "texts": [index[id(e)] for e in v.texts],
        }
        for v in views
    ]


def views_from_json(
    items: list[dict], entities: list[RawEntity]
) -> list[ViewCandidate]:
    return [
        ViewCandidate(
            item["id"],
            box(item["bbox"]),
            [entities[i] for i in item["entities"]],
            [entities[i] for i in item["dimensions"]],
            [entities[i] for i in item["texts"]],
            item["label"],
            item["confidence"],
            item["label_source"],
            item["reason"],
        )
        for item in items
    ]


def title_from_json(value: dict) -> TitleBlock:
    title = TitleBlock(**value)
    title.region = box(title.region)
    return title


def result_from_json(value: dict) -> ReconstructionResult:
    return ReconstructionResult.from_dict(value)


# ---------------------------------------------------------------------- model clients
def fresh(client: VLMClient | None, role: str) -> VLMClient:
    """A copy with an empty trace (None: a disabled client), so a stage records only its own calls."""
    if client is None:
        return VLMClient(VLMConfig(model=""), role)
    clone = copy(client)
    clone.trace = []
    return clone


# ---------------------------------------------------------------------- stage functions and CLI
def stage_function(name: str) -> Callable:
    """Accept a workspace or a path; on an error, write a failed stage file and re-raise."""

    def wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def run(work: Workspace | str | Path, *args, **kwargs) -> dict:
            ws = work if isinstance(work, Workspace) else Workspace(work)
            try:
                return fn(ws, *args, **kwargs)
            except StageNotReady:
                raise
            except Exception as exc:
                ws.save(
                    name, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                )
                raise

        return run

    return wrap


def stage_parser(
    doc: str, *, models: tuple[str, ...] = (), drawing: bool = False
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=doc, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    if drawing:
        parser.add_argument("drawing", type=Path, help="DXF file")
    parser.add_argument(
        "work",
        type=Path,
        help="drawing workspace holding stages/ and analysis/ (batch: <output-dir>/<drawing id>)",
    )
    for role in models:
        parser.add_argument(
            f"--{role}-model", help=f"overrides CUTPLAN_{role.upper()}_MODEL"
        )
        parser.add_argument(f"--{role}-base-url", help="OpenAI-compatible endpoint")
        parser.add_argument(f"--{role}-provider", choices=["openai", "anthropic"])
    if models:
        parser.add_argument(
            "--no-vlm", action="store_true", help="run without models (fallbacks only)"
        )
    return parser


def clients_from_args(args: argparse.Namespace) -> tuple[VLMClient, VLMClient]:
    return make_clients(
        disabled=getattr(args, "no_vlm", False),
        ocr_model=getattr(args, "ocr_model", None),
        reason_model=getattr(args, "reason_model", None),
        ocr_base_url=getattr(args, "ocr_base_url", None),
        reason_base_url=getattr(args, "reason_base_url", None),
        ocr_provider=getattr(args, "ocr_provider", None),
        reason_provider=getattr(args, "reason_provider", None),
    )


def headline(record: dict) -> str:
    why = record.get("reason") or record.get("error")
    return f"{record['step']:02d} {record['stage']}: {record['status']}" + (
        f" ({why})" if why and record["status"] != "done" else ""
    )


def cli(work: Path, call: Callable[[], dict], describe: Callable[[dict], str]) -> int:
    """Run one stage from the command line and print what it produced."""
    try:
        record = call()
    except StageNotReady as exc:
        print(exc, file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(headline(record))
    if record["status"] == "done":
        print(describe(record))
    print(f"-> {Workspace(work).path(record['stage'])}")
    return 0
