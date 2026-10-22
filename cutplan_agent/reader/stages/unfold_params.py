"""Stage 09 unfold_params: read the development (전개) parameters of the decided part class.
Model: reasoning (with the unfold skills); overall view dimensions fill what the model leaves empty.

Without the document stage (--analyze-only) the model gets only the sheet analysis.
in : analysis/sheet_analysis.json, stages/08_document.json when it built a document
out: stages/09_unfold_params.json (parameters with per-field source, model call incl. raw reply)

PYTHONPATH=. python cutplan_agent/reader/stages/unfold_params.py <work> --reason-model ...
"""

from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    clients_from_args,
    fresh,
    stage_function,
    stage_parser,
)
from cutplan_agent.reader.unfold import read_unfold_params
from cutplan_agent.reader.vlm import VLMClient

STAGE = "unfold_params"


@stage_function(STAGE)
def run(ws: Workspace, *, reason: VLMClient | None = None) -> dict:
    reason = fresh(reason, "reason")
    analysis = ws.analysis()
    if ws.has("document") and ws.load("document").get("not_orthographic"):
        # as before the split: a nesting sheet stops at the document stage
        return ws.save(
            STAGE, {"status": "skipped", "reason": ws.load("document")["reason"]}
        )
    document = ws.document()
    record = read_unfold_params(analysis, document, reason)
    status = "done" if record["status"] == "params_read" else record["status"]
    return ws.save(
        STAGE,
        {
            "status": status,
            **({"reason": record["reason"]} if "reason" in record else {}),
            **({"error": record["error"]} if "error" in record else {}),
            "with_document": document is not None,
            "record": record,
            "trace": {"reason": reason.trace},
        },
    )


def describe(record: dict) -> str:
    r = record["record"]
    return (
        f"{r['part_class']} -> {r['part_type']} (model said {r['model_part_type']}); "
        f"confidence={r['confidence']}\nparams: {r['params']}\nsources: {r['sources']}"
    )


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__, models=("reason",)).parse_args(argv)
    _, reason = clients_from_args(args)
    return cli(args.work, lambda: run(args.work, reason=reason), describe)


if __name__ == "__main__":
    raise SystemExit(main())
