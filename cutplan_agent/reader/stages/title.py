"""Stage 2 title: title block → title.json (+ title_block.png when OCR runs).

Regex over the DXF texts first. Only when a field is still missing does the OCR model
read title_block.png and the reasoning model structure that transcription
(dxf_adapter.parse_title_block). `sources` in title.json says where each field came
from, and `trace` keeps the model calls, OCR text included.

PYTHONPATH=. python cutplan_agent/reader/stages/title.py --output-dir out/part [model options]
"""

from __future__ import annotations

from pathlib import Path

from cutplan_agent.reader.dxf_adapter import (
    _sheet_bbox,
    find_title_region,
    parse_title_block,
)
from cutplan_agent.reader.stages import workdir


def run(
    work_dir: str | Path,
    *,
    clients=None,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    from cutplan_agent.reader.vlm import make_clients

    work_dir = Path(work_dir)
    entities, _ = workdir.load_entities(work_dir)
    workdir.prepare(
        "title", work_dir, Path(output_dir) if output_dir else None, overwrite=overwrite
    )
    ocr, reason = clients or make_clients()
    marks = workdir.trace_marks((ocr, reason))
    region = find_title_region(entities, _sheet_bbox(entities))
    title = parse_title_block(entities, region, ocr, work_dir, reason=reason)
    path = workdir.write_json(
        work_dir / "title.json",
        {
            "title_region": region,
            "title_block": title.as_dict(),
            "trace": workdir.trace_since((ocr, reason), marks),
        },
    )
    outputs = [str(path)]
    if (work_dir / "title_block.png").is_file():
        outputs.append(str(work_dir / "title_block.png"))
    return {"stage": "title", "title_block": title.as_dict(), "outputs": outputs}


def main(argv: list[str] | None = None) -> int:
    parser = workdir.stage_parser(
        "Stage 2: read the title block (regex, then OCR + reasoning for missing fields)",
    )
    args = parser.parse_args(argv)
    return workdir.cli(run, args, clients=workdir.clients_from_args(args))


if __name__ == "__main__":
    raise SystemExit(main())
