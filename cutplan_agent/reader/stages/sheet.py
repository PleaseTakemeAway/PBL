"""Stage 07 sheet: assemble the sheet analysis. No model.

Draws the final labelled sheet and writes sheet_analysis.json, whose vlm_trace collects the
model calls of title_ocr, title_fields and view_labels.
in : stages/01_read.json … stages/06_view_labels.json
out: stages/07_sheet.json, analysis/sheet.png, analysis/sheet_analysis.json

PYTHONPATH=. python cutplan_agent/reader/stages/sheet.py <work>
"""

from pathlib import Path

from cutplan_agent.reader.dxf_adapter import write_sheet_analysis
from cutplan_agent.reader.stages.workspace import (
    Workspace,
    box,
    cli,
    entities_from_json,
    stage_function,
    stage_parser,
    title_from_json,
    views_from_json,
)

STAGE = "sheet"
MODEL_STAGES = ("title_ocr", "title_fields", "view_labels")


@stage_function(STAGE)
def run(ws: Workspace) -> dict:
    read = ws.load("read")
    entities = entities_from_json(read["entities"])
    regex = ws.load("title_regex")
    found = ws.load("views")
    labelled = ws.load("view_labels")
    traces = [ws.load(stage).get("trace", {}) for stage in MODEL_STAGES]
    # same order as before the split: every OCR call, then every reasoning call
    trace = [
        t for role in ("ocr", "reason") for calls in traces for t in calls.get(role, [])
    ]
    analysis = write_sheet_analysis(
        Path(read["source"]),
        ws.analysis_dir,
        info=read["info"],
        entities=entities,
        title_regions=[box(r) for r in regex["title_regions"]],
        title_region=box(regex["title_region"]),
        title=title_from_json(labelled["title_block"]),
        found={
            "frames": [box(f) for f in found["frames"]],
            "excluded_regions": [box(r) for r in found["excluded_regions"]],
            "views": views_from_json(labelled["views"], entities),
            "segmentation": found["segmentation"],
            "sheet_type": found["sheet_type"],
            "sheet_type_evidence": found["sheet_type_evidence"],
        },
        labelled=labelled,
        trace=trace,
    )
    return ws.save(
        STAGE,
        {
            "status": "done",
            "sheet_type": analysis["sheet_type"],
            "part_class": analysis["part_class"],
            "reconstructable": analysis["reconstructable"],
            "outputs": {
                "sheet_png": analysis["renders"]["sheet"],
                "sheet_analysis": str(ws.analysis_dir / "sheet_analysis.json"),
            },
        },
    )


def describe(record: dict) -> str:
    return (
        f"sheet_type={record['sheet_type']} part_class={record['part_class']} "
        f"reconstructable={record['reconstructable']}\n"
        f"{record['outputs']['sheet_png']}, {record['outputs']['sheet_analysis']}"
    )


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__).parse_args(argv)
    return cli(args.work, lambda: run(args.work), describe)


if __name__ == "__main__":
    raise SystemExit(main())
