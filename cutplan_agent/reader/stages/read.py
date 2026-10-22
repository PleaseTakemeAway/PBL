"""Stage 01 read: every DXF entity, layer-agnostic. No model.

in : the DXF file, or when none is given the DXF recorded in stages/00_convert.json
out: stages/01_read.json (entities, file units, reader, source sha256)

PYTHONPATH=. python cutplan_agent/reader/stages/read.py <drawing.dxf> <work>
(a DWG goes through convert.py first; run.py <work> then reads the converted DXF)
"""

import hashlib
from pathlib import Path

from cutplan_agent.reader.dxf_adapter import _count
from cutplan_agent.reader.dxf_reader import read_dxf
from cutplan_agent.reader.stages.workspace import (
    CONVERT,
    Workspace,
    cli,
    entities_to_json,
    stage_function,
    stage_parser,
)

STAGE = "read"


@stage_function(STAGE)
def run(ws: Workspace, drawing: str | Path | None = None) -> dict:
    if drawing is None:
        drawing = ws.load(CONVERT)["dxf"]
    path = Path(drawing)
    entities, info = read_dxf(path)
    return ws.save(
        STAGE,
        {
            "status": "done",
            "source": str(path),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "info": info,
            "entity_counts": _count(entities),
            "entities": entities_to_json(entities),
        },
    )


def describe(record: dict) -> str:
    return (
        f"{len(record['entities'])} entities {record['entity_counts']}; "
        f"units={record['info']['units']} reader={record['info']['reader']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = stage_parser(__doc__, drawing=True)
    args = parser.parse_args(argv)
    return cli(args.work, lambda: run(args.work, args.drawing), describe)


if __name__ == "__main__":
    raise SystemExit(main())
