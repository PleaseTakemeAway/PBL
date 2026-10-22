"""Stage 4 label: view types, projection, part class → sheet_analysis.json.

Relative position gives every view a fallback label (label_by_position). The reasoning
model then looks at sheet_labeled.png, reads the skills documents and decides view
types, projection, part_class and whether the views alone define the shape
(label_with_vlm). Where the two disagree, `review` says so. sheet.png shows the final
labels. sheet_analysis.json gathers what stages 1-4 found, with every model call so
far in `vlm_trace`.

PYTHONPATH=. python cutplan_agent/reader/stages/label.py --output-dir out/part [model options]
"""

from __future__ import annotations

import json
from pathlib import Path

from cutplan_agent.reader.dxf_adapter import (
    label_by_position,
    label_with_vlm,
    render,
)
from cutplan_agent.reader.stages import workdir


def run(
    work_dir: str | Path,
    *,
    clients=None,
    projection_default: str = "third",
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    from cutplan_agent.reader.vlm import make_clients

    work_dir = Path(work_dir)
    entities, read = workdir.load_entities(work_dir)
    found = workdir.read_json(work_dir, "title.json")
    seg = workdir.read_json(work_dir, "views.json")
    workdir.prepare(
        "label", work_dir, Path(output_dir) if output_dir else None, overwrite=overwrite
    )
    ocr, reason = clients or make_clients()
    marks = workdir.trace_marks((ocr, reason))
    title = workdir.title_from_dict(found["title_block"])
    views = workdir.views_from_list(seg["views"], entities)
    sheet_type = seg["sheet_type"]
    review: list[dict] = list(seg["review"])
    projection = title.projection or projection_default
    decision: dict = {"used": False}
    if sheet_type != "nesting":
        label_by_position(views, projection)
        fallback = {v.id: v.label for v in views}
        decision = label_with_vlm(views, entities, title, reason, work_dir)
        if decision.get("projection"):
            projection = decision["projection"]
            if title.projection is None:
                title.projection, title.sources["projection"] = (
                    projection,
                    f"vlm_reason:{reason.config.model}",
                )
        disagreements = [
            {"view": v.id, "position": fallback[v.id], "vlm": v.label}
            for v in views
            if decision.get("used") and fallback[v.id] != v.label
        ]
        if not decision.get("used"):
            review.append(
                {
                    "issue": "view labels come from relative position only (no reasoning VLM); confirm front/top/right"
                }
            )
        if decision.get("reconstructable") is False:
            review.append(
                {
                    "issue": "model judged the shape not reconstructable from orthographic views alone",
                    "notes": decision.get("notes"),
                }
            )
        review += [
            {
                "view": d["view"],
                "issue": f"position fallback said {d['position']}, VLM said {d['vlm']}",
            }
            for d in disagreements
        ]
        if sheet_type == "unknown":
            review.append(
                {
                    "issue": "sheet type unclear (neither clean orthographic layout nor nesting captions)",
                    "evidence": seg["sheet_type_evidence"],
                }
            )
    render(
        [e for e in entities if e.kind != "other"],
        work_dir / "sheet.png",
        boxes=[(v.bbox, f"{v.id}:{v.label}") for v in views],
        width_in=18,
    )
    # OCR calls before reasoning calls, as each client keeps them
    calls = found["trace"] + workdir.trace_since((ocr, reason), marks)
    vlm_trace = [r for r in calls if r["role"] == "ocr"] + [
        r for r in calls if r["role"] != "ocr"
    ]
    analysis = {
        "source": read["source"],
        "reader": read["reader"],
        "file_units": read["units"],
        "entity_counts": read["entity_counts"],
        "sheet_bbox": seg["sheet_bbox"],
        "frames": seg["frames"],
        "title_regions": seg["title_regions"],
        "title_region": found["title_region"],
        "excluded_regions": seg["excluded_regions"],
        "segmentation": seg["segmentation"],
        "sheet_type": sheet_type,
        "sheet_type_evidence": seg["sheet_type_evidence"],
        "projection": projection,
        "part_class": decision.get("part_class"),
        "part_class_probabilities": decision.get("part_class_probabilities"),
        "part_class_probability_source": decision.get("probability_source"),
        "reconstructable": decision.get("reconstructable"),
        "title_block": title.as_dict(),
        "views": [
            {
                "id": v.id,
                "bbox": v.bbox,
                "label": v.label,
                "confidence": v.confidence,
                "source": v.label_source,
                "reason": v.reason,
                "counts": v.counts(),
            }
            for v in views
        ],
        "plates": seg["plates"],
        "vlm_decision": {k: v for k, v in decision.items() if k != "raw"},
        "vlm_trace": vlm_trace,
        "review": review,
        "renders": {"sheet": str(work_dir / "sheet.png")},
    }
    (work_dir / "sheet_analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, default=list),
        encoding="utf-8",
    )
    outputs = [str(work_dir / "sheet_analysis.json"), str(work_dir / "sheet.png")]
    if decision.get("image"):
        outputs.append(decision["image"])
    return {
        "stage": "label",
        "sheet_type": sheet_type,
        "projection": projection,
        "part_class": analysis["part_class"],
        "reconstructable": analysis["reconstructable"],
        "views": [
            {"id": v.id, "label": v.label, "source": v.label_source} for v in views
        ],
        "review": review,
        "outputs": outputs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = workdir.stage_parser(
        "Stage 4: label views, projection and part class (reasoning model, position fallback)",
    )
    parser.add_argument(
        "--projection",
        choices=["first", "third"],
        default="third",
        help="Fallback projection when neither title block nor model decides",
    )
    args = parser.parse_args(argv)
    return workdir.cli(
        run,
        args,
        clients=workdir.clients_from_args(args),
        projection_default=args.projection,
    )


if __name__ == "__main__":
    raise SystemExit(main())
