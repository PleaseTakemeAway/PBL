"""Stage 02 title_regex: find the title block and read its fields with regular expressions. No model.

in : stages/01_read.json
out: stages/02_title_regex.json (title regions, title_block, fields still missing)

PYTHONPATH=. python cutplan_agent/reader/stages/title_regex.py <work>
"""

from cutplan_agent.reader.dxf_adapter import (
    _sheet_bbox,
    find_title_region,
    find_title_regions,
    missing_title_fields,
    regex_title_block,
)
from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    stage_function,
    stage_parser,
)

STAGE = "title_regex"


@stage_function(STAGE)
def run(ws: Workspace) -> dict:
    entities = ws.entities()
    sheet = _sheet_bbox(entities)
    region = find_title_region(entities, sheet)
    title = regex_title_block(entities, region)
    return ws.save(
        STAGE,
        {
            "status": "done",
            "title_regions": find_title_regions(entities, sheet),
            "title_region": region,
            "title_block": title.as_dict(),
            "missing": missing_title_fields(title),
        },
    )


def describe(record: dict) -> str:
    title = record["title_block"]
    found = {k: title[k] for k in title["sources"]}
    region = record["title_region"]
    shown = [round(v, 1) for v in region] if region else None
    return f"region={shown}; regex: {found}; missing: {record['missing']}"


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__).parse_args(argv)
    return cli(args.work, lambda: run(args.work), describe)


if __name__ == "__main__":
    raise SystemExit(main())
