"""Stage 06 view_labels: name every view cluster. Model: reasoning (with the part_class skills).

Nesting sheets: each cluster is a plate with its caption (no model). Other sheets: a
relative-position fallback first, then the reasoning model decides view types, projection,
part class and whether the views alone define the shape; disagreements become review items.
in : stages/01_read.json, stages/04_title_fields.json, stages/05_views.json
out: stages/06_view_labels.json (labels, model reply incl. raw, review, model call),
     analysis/sheet_labeled.png (the model's input image)

PYTHONPATH=. python cutplan_agent/reader/stages/view_labels.py <work> --reason-model ... [--projection third]
"""

from cutplan_agent.reader.dxf_adapter import label_sheet
from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    clients_from_args,
    fresh,
    stage_function,
    stage_parser,
    title_from_json,
    views_from_json,
    views_to_json,
)
from cutplan_agent.reader.vlm import VLMClient

STAGE = "view_labels"


@stage_function(STAGE)
def run(
    ws: Workspace,
    *,
    reason: VLMClient | None = None,
    projection_default: str = "third",
) -> dict:
    reason = fresh(reason, "reason")
    entities = ws.entities()
    found = ws.load("views")
    views = views_from_json(found["views"], entities)
    title = title_from_json(ws.load("title_fields")["title_block"])
    ws.analysis_dir.mkdir(parents=True, exist_ok=True)
    labelled = label_sheet(
        views,
        entities,
        title,
        found["sheet_type"],
        found["sheet_type_evidence"],
        reason,
        ws.analysis_dir,
        projection_default=projection_default,
    )
    return ws.save(
        STAGE,
        {
            "status": "done",
            "projection_default": projection_default,
            "projection": labelled["projection"],
            "title_block": title.as_dict(),
            "views": views_to_json(views, entities),
            "plates": labelled["plates"],
            "decision": labelled["decision"],
            "review": labelled["review"],
            "trace": {"reason": reason.trace},
        },
    )


def describe(record: dict) -> str:
    decision = record["decision"]
    labels = " ".join(f"{v['id']}:{v['label']}" for v in record["views"])
    lines = [
        f"projection={record['projection']} part_class={decision.get('part_class')} "
        f"reconstructable={decision.get('reconstructable')} model_used={decision['used']}",
        f"labels: {labels}",
    ]
    if record["plates"]:
        lines.append(
            "plates: " + "; ".join(p.get("caption", "?") for p in record["plates"])
        )
    lines += [f"review: {r}" for r in record["review"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = stage_parser(__doc__, models=("reason",))
    parser.add_argument(
        "--projection",
        choices=["first", "third"],
        default="third",
        help="fallback projection when neither title block nor model decides",
    )
    args = parser.parse_args(argv)
    _, reason = clients_from_args(args)
    return cli(
        args.work,
        lambda: run(args.work, reason=reason, projection_default=args.projection),
        describe,
    )


if __name__ == "__main__":
    raise SystemExit(main())
