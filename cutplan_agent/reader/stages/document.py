"""Stage 08 document: convert the labelled views into the front/top/right drawing contract
used by 3D reconstruction (arcs tessellated, left/bottom/back mirrored, dimensions attached,
title scale checked against the drawn extents). No model.

A nesting sheet stops here (status skipped, not_orthographic).
in : stages/01_read.json, stages/06_view_labels.json, analysis/sheet_analysis.json
out: stages/08_document.json

PYTHONPATH=. python cutplan_agent/reader/stages/document.py <work> [--units mm]
"""

from pathlib import Path

from cutplan_agent.reader.dxf_adapter import NotOrthographicSheet, build_document
from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    entities_from_json,
    stage_function,
    stage_parser,
    title_from_json,
    views_from_json,
)

STAGE = "document"


@stage_function(STAGE)
def run(ws: Workspace, *, units: str | None = None) -> dict:
    analysis = ws.analysis()
    if analysis["sheet_type"] == "nesting":
        return ws.save(
            STAGE,
            {
                "status": "skipped",
                "reason": str(NotOrthographicSheet(analysis)),
                "not_orthographic": True,
            },
        )
    read = ws.load("read")
    entities = entities_from_json(read["entities"])
    labelled = ws.load("view_labels")
    document = build_document(
        Path(read["source"]),
        entities,
        views_from_json(labelled["views"], entities),
        title_from_json(labelled["title_block"]),
        analysis,
    )
    if units:
        document.metadata["units"] = units
    document.metadata["source_sha256"] = read["source_sha256"]
    return ws.save(
        STAGE,
        {
            "status": "done",
            "units_override": units,
            "views": [v.name for v in document.views],
            "document": document.to_dict(),
        },
    )


def describe(record: dict) -> str:
    meta = record["document"]["metadata"]
    return (
        f"views={record['views']} units={meta['units']} scale={meta['drawing_scale']} "
        f"({meta['geometry_scale_mode']}) dimensions={meta.get('dimensions')}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = stage_parser(__doc__)
    parser.add_argument("--units", choices=["mm", "cm", "m", "inch"])
    args = parser.parse_args(argv)
    return cli(args.work, lambda: run(args.work, units=args.units), describe)


if __name__ == "__main__":
    raise SystemExit(main())
