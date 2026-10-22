"""Stage 05 views: drawing frames, excluded regions (title blocks, tables), view clusters and
sheet type (orthographic / nesting / unknown). No model.

in : stages/01_read.json, stages/02_title_regex.json
out: stages/05_views.json

PYTHONPATH=. python cutplan_agent/reader/stages/views.py <work> [--gap-ratio 0.008]
"""

from cutplan_agent.reader.dxf_adapter import find_views
from cutplan_agent.reader.stages.workspace import (
    Workspace,
    box,
    cli,
    stage_function,
    stage_parser,
    views_to_json,
)

STAGE = "views"


@stage_function(STAGE)
def run(ws: Workspace, *, gap_ratio: float = 0.008) -> dict:
    entities = ws.entities()
    regions = [box(r) for r in ws.load("title_regex")["title_regions"]]
    found = find_views(entities, regions, gap_ratio=gap_ratio)
    return ws.save(
        STAGE,
        {
            "status": "done",
            "gap_ratio": gap_ratio,
            "frames": found["frames"],
            "excluded_regions": found["excluded_regions"],
            "segmentation": found["segmentation"],
            "sheet_type": found["sheet_type"],
            "sheet_type_evidence": found["sheet_type_evidence"],
            "views": views_to_json(found["views"], entities),
        },
    )


def describe(record: dict) -> str:
    sizes = ", ".join(
        f"{v['id']}:{v['bbox'][2] - v['bbox'][0]:.0f}x{v['bbox'][3] - v['bbox'][1]:.0f}"
        for v in record["views"]
    )
    return (
        f"sheet_type={record['sheet_type']} {record['sheet_type_evidence']}; "
        f"{len(record['views'])} views [{sizes}]; {len(record['frames'])} frames, "
        f"{len(record['excluded_regions'])} excluded regions"
    )


def main(argv: list[str] | None = None) -> int:
    parser = stage_parser(__doc__)
    parser.add_argument("--gap-ratio", type=float, default=0.008)
    args = parser.parse_args(argv)
    return cli(args.work, lambda: run(args.work, gap_ratio=args.gap_ratio), describe)


if __name__ == "__main__":
    raise SystemExit(main())
