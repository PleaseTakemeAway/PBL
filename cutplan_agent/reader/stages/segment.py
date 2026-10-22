"""Stage 3 segment: views and sheet type → views.json. No model.

Drawing frames, title and table regions are excluded; the remaining part geometry is
clustered into view candidates, and dimensions and texts are attached to the nearest
one (dxf_adapter.segment_views). classify_sheet then calls the sheet orthographic,
nesting (cutting plan) or unknown. On a nesting sheet every cluster is a plate.

PYTHONPATH=. python cutplan_agent/reader/stages/segment.py --output-dir out/part
"""

from __future__ import annotations

from math import hypot
from pathlib import Path

from cutplan_agent.reader.dxf_adapter import (
    TABLE_KEYS,
    _expand,
    _nesting_plates,
    _sheet_bbox,
    classify_sheet,
    detect_frames,
    find_title_regions,
    segment_views,
)
from cutplan_agent.reader.stages import workdir


def run(
    work_dir: str | Path,
    *,
    gap_ratio: float = 0.008,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    work_dir = Path(work_dir)
    entities, _ = workdir.load_entities(work_dir)
    workdir.prepare(
        "segment",
        work_dir,
        Path(output_dir) if output_dir else None,
        overwrite=overwrite,
    )
    sheet = _sheet_bbox(entities)
    frames, frame_handles = detect_frames(entities, sheet)
    title_regions = find_title_regions(entities, sheet)
    tables = []
    for e in entities:
        if e.kind == "text" and e.text and any(k in e.text.upper() for k in TABLE_KEYS):
            tables.append(
                _expand(
                    e.bbox(), 0.01 * hypot(sheet[2] - sheet[0], sheet[3] - sheet[1])
                )
            )
    excluded = title_regions + tables
    views, seg = segment_views(entities, excluded, gap_ratio, frame_handles, frames)
    sheet_type, evidence = classify_sheet(entities, views)
    review: list[dict] = []
    plates: list[dict] = []
    if sheet_type == "nesting":
        plates = _nesting_plates(views, entities, sheet)
        review.append(
            {
                "issue": "nesting / cutting-plan sheet: orthographic reconstruction not applicable; use `plates`"
            }
        )
        for pl in plates:
            if "caption" not in pl:
                review.append({"view": pl["id"], "issue": "plate without size caption"})
            elif not pl.get("caption_matches_outline"):
                review.append(
                    {
                        "view": pl["id"],
                        "issue": f"caption {pl['caption']} does not match drawn outline {pl['size_drawn']}",
                    }
                )
    path = workdir.write_json(
        work_dir / "views.json",
        {
            "sheet_bbox": sheet,
            "frames": frames,
            "title_regions": title_regions,
            "excluded_regions": excluded,
            "segmentation": seg,
            "sheet_type": sheet_type,
            "sheet_type_evidence": evidence,
            "plates": plates,
            "review": review,
            "views": workdir.views_to_list(views, entities),
        },
    )
    return {
        "stage": "segment",
        "sheet_type": sheet_type,
        "views": [{"id": v.id, "bbox": v.bbox, "counts": v.counts()} for v in views],
        "plates": len(plates),
        "outputs": [str(path)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = workdir.stage_parser(
        "Stage 3: split the sheet into view candidates and decide the sheet type"
    )
    parser.add_argument(
        "--gap-ratio",
        type=float,
        default=0.008,
        help="Clustering gap as a fraction of the frame diagonal (default 0.008)",
    )
    args = parser.parse_args(argv)
    return workdir.cli(run, args, gap_ratio=args.gap_ratio)


if __name__ == "__main__":
    raise SystemExit(main())
