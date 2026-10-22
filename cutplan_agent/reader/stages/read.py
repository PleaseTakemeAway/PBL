"""Stage 1 read: DXF → entities.json. No model.

Every modelspace entity, whatever its layer, as flat records in drawing units
(dxf_reader.read_dxf). Later stages refer to entities by their index in this file.

PYTHONPATH=. python cutplan_agent/reader/stages/read.py part.dxf --output-dir out/part
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cutplan_agent.reader.dxf_adapter import _count
from cutplan_agent.reader.dxf_reader import read_dxf
from cutplan_agent.reader.stages import workdir


def run(
    work_dir: str | Path,
    *,
    source: str | Path,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    work_dir, source = Path(work_dir), Path(source)
    workdir.prepare(
        "read", work_dir, Path(output_dir) if output_dir else None, overwrite=overwrite
    )
    entities, info = read_dxf(source)
    record = {
        "source": str(source),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "reader": info["reader"],
        "units": info["units"],
        "entity_counts": _count(entities),
    }
    path = workdir.write_json(
        work_dir / "entities.json",
        {**record, "entities": workdir.entities_to_list(entities)},
    )
    return {"stage": "read", **record, "outputs": [str(path)]}


def main(argv: list[str] | None = None) -> int:
    parser = workdir.stage_parser("Stage 1: read every DXF entity into entities.json")
    parser.add_argument("drawing", type=Path, help="DXF file")
    args = parser.parse_args(argv)
    return workdir.cli(run, args, source=args.drawing)


if __name__ == "__main__":
    raise SystemExit(main())
