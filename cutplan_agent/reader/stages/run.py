"""Run the reader stages for one DXF drawing in order; main.py --batch calls run_drawing per drawing.

Every stage writes <work>/stages/NN_<stage>.json, including stages that an option or an
earlier result skips, so the folder shows what happened at each step.

The 3D stages (reconstruct, confirm, export) are skipped unless --with-3d is given: the reader
ends at the flat pattern (develop) since 2026-10-27 (docs/v3_upgrade.md 1.1).

PYTHONPATH=. python cutplan_agent/reader/stages/run.py <drawing.dxf> <work> [--to STAGE]
PYTHONPATH=. python cutplan_agent/reader/stages/run.py <work> --from STAGE [--to STAGE]
    --from STAGE  start here and reuse the earlier stage files already in <work>
    --to STAGE    stop after this stage
    --with-3d     also run the 3D stages
"""

import argparse
import sys
from pathlib import Path
from typing import Callable

from cutplan_agent.reader.stages import (
    confirm,
    develop,
    document,
    export,
    read,
    reconstruct,
    sheet,
    title_fields,
    title_ocr,
    title_regex,
    unfold_params,
    view_labels,
    views,
)
from cutplan_agent.reader.stages.workspace import (
    CONVERT,
    STAGES,
    THREE_D,
    THREE_D_OFF,
    StageNotReady,
    Workspace,
    clients_from_args,
    headline,
)
from cutplan_agent.reader.vlm import VLMClient

MODULES = {
    "read": read,
    "title_regex": title_regex,
    "title_ocr": title_ocr,
    "title_fields": title_fields,
    "views": views,
    "view_labels": view_labels,
    "sheet": sheet,
    "document": document,
    "unfold_params": unfold_params,
    "develop": develop,
    "reconstruct": reconstruct,
    "confirm": confirm,
    "export": export,
}


def run_drawing(
    drawing: str | Path | None,
    work: str | Path,
    clients: tuple[VLMClient, VLMClient],
    *,
    first: str = "read",
    last: str = "export",
    analyze_only: bool = False,
    unfold: bool = True,
    confirm: bool = True,
    three_d: bool = False,
    units: str | None = None,
    tolerance: float | None = None,
    max_candidates: int = 10,
    projection_default: str = "third",
    gap_ratio: float = 0.008,
    on_stage: Callable[[str, dict], None] | None = None,
) -> dict[str, dict]:
    """Run stages first..last; return {stage: stage record}. A stage error is re-raised after
    the failed stage file and skipped files for the remaining stages are written."""
    ws = Workspace(work)
    ocr, reason = clients
    m = MODULES  # the `confirm` argument shadows the module name
    calls = {
        "read": lambda: m["read"].run(ws, drawing),
        "title_regex": lambda: m["title_regex"].run(ws),
        "title_ocr": lambda: m["title_ocr"].run(ws, ocr=ocr),
        "title_fields": lambda: m["title_fields"].run(ws, reason=reason),
        "views": lambda: m["views"].run(ws, gap_ratio=gap_ratio),
        "view_labels": lambda: m["view_labels"].run(
            ws, reason=reason, projection_default=projection_default
        ),
        "sheet": lambda: m["sheet"].run(ws),
        "document": lambda: m["document"].run(ws, units=units),
        "unfold_params": lambda: m["unfold_params"].run(ws, reason=reason),
        "develop": lambda: m["develop"].run(ws),
        "reconstruct": lambda: m["reconstruct"].run(
            ws, tolerance=tolerance, max_candidates=max_candidates
        ),
        "confirm": lambda: m["confirm"].run(ws, reason=reason),
        "export": lambda: m["export"].run(ws),
    }
    disabled = {}
    if analyze_only:
        disabled.update(
            {
                s: "--analyze-only"
                for s in ("document", "reconstruct", "confirm", "export")
            }
        )
    if not unfold:
        disabled.update({s: "--no-unfold" for s in ("unfold_params", "develop")})
    if not confirm:
        disabled["confirm"] = "--no-confirm"
    if not three_d:
        for s in THREE_D:
            disabled.setdefault(s, THREE_D_OFF)
    plan = STAGES[STAGES.index(first) : STAGES.index(last) + 1]
    records: dict[str, dict] = {}
    for i, stage in enumerate(plan):
        if stage in disabled:
            records[stage] = ws.save(
                stage, {"status": "skipped", "reason": disabled[stage]}
            )
        else:
            try:
                records[stage] = calls[stage]()
            except StageNotReady:
                raise  # an input stage is missing (e.g. --from too late): nothing ran
            except Exception:
                for later in plan[i + 1 :]:
                    ws.save(later, {"status": "skipped", "reason": f"{stage} failed"})
                raise
        if on_stage:
            on_stage(stage, records[stage])
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="[drawing.dxf] work",
        help="the DXF (needed only when the read stage runs) and the drawing workspace",
    )
    parser.add_argument("--from", dest="first", choices=STAGES, default="read")
    parser.add_argument("--to", dest="last", choices=STAGES, default="export")
    for role in ("ocr", "reason"):
        parser.add_argument(f"--{role}-model")
        parser.add_argument(f"--{role}-base-url")
        parser.add_argument(f"--{role}-provider", choices=["openai", "anthropic"])
    parser.add_argument("--no-vlm", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--no-unfold", action="store_true")
    parser.add_argument("--no-confirm", action="store_true")
    parser.add_argument("--with-3d", action="store_true", help="also run the 3D stages")
    parser.add_argument("--units", choices=["mm", "cm", "m", "inch"])
    parser.add_argument("--tolerance", type=float)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--projection", choices=["first", "third"], default="third")
    args = parser.parse_args(argv)
    if STAGES.index(args.first) > STAGES.index(args.last):
        parser.error("--from comes after --to")
    if len(args.paths) > 2:
        parser.error("give at most a DXF and a workspace")
    drawing, work = (None, *args.paths) if len(args.paths) == 1 else args.paths
    if drawing is None and args.first == "read" and not Workspace(work).has(CONVERT):
        parser.error(
            "the read stage needs the DXF: run.py <drawing.dxf> <work>, "
            "or convert.py <drawing.dwg> <work> first"
        )

    def show(stage: str, record: dict) -> None:
        print(headline(record))
        if record["status"] == "done":
            for line in MODULES[stage].describe(record).splitlines():
                print(f"    {line}")

    try:
        run_drawing(
            drawing,
            work,
            clients_from_args(args),
            first=args.first,
            last=args.last,
            analyze_only=args.analyze_only,
            unfold=not args.no_unfold,
            confirm=not args.no_confirm,
            three_d=args.with_3d,
            units=args.units,
            tolerance=args.tolerance,
            max_candidates=args.max_candidates,
            projection_default=args.projection,
            on_stage=show,
        )
    except StageNotReady as exc:
        print(exc, file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"-> {Workspace(work).stages_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
