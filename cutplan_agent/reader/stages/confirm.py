"""Stage 12 confirm: the reasoning model compares the original views with the reprojected top
candidates and picks one. Model: reasoning. The validator ranking stays authoritative; a
different pick becomes a review item.

in : stages/11_reconstruct.json
out: stages/12_confirm.json (pick, updated review request, model call), analysis/candidates.png

PYTHONPATH=. python cutplan_agent/reader/stages/confirm.py <work> --reason-model ...
"""

from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    clients_from_args,
    fresh,
    result_from_json,
    stage_function,
    stage_parser,
)
from cutplan_agent.reader.vision_adapter import confirm_candidates
from cutplan_agent.reader.vlm import VLMClient

STAGE = "confirm"


@stage_function(STAGE)
def run(ws: Workspace, *, reason: VLMClient | None = None) -> dict:
    reason = fresh(reason, "reason")
    built = ws.load("reconstruct")
    if built["status"] != "done":
        return ws.save(
            STAGE, {"status": "skipped", "reason": f"reconstruct: {built['reason']}"}
        )
    if not reason.enabled:
        return ws.save(
            STAGE, {"status": "skipped", "reason": "no reasoning model configured"}
        )
    result = result_from_json(built["result"])
    ws.analysis_dir.mkdir(parents=True, exist_ok=True)
    confirmation = confirm_candidates(result, reason, ws.analysis_dir)
    return ws.save(
        STAGE,
        {
            "status": "done",
            "confirmation": confirmation,
            # confirm_candidates stores its record in the result only when it asked the model
            "recorded": "candidate_confirmation" in result.metadata,
            "review_request": result.review_request,
            "trace": {"reason": reason.trace},
        },
    )


def describe(record: dict) -> str:
    c = record["confirmation"]
    if not c.get("used"):
        return "no valid candidate to show the model"
    return (
        f"candidates={c['candidates']} pick={c.get('pick')} confidence={c.get('confidence')} "
        f"error={c.get('error')}\nreason: {c.get('reason')}\n"
        f"review: {record['review_request'].get('status')} image={c['image']}"
    )


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__, models=("reason",)).parse_args(argv)
    _, reason = clients_from_args(args)
    return cli(args.work, lambda: run(args.work, reason=reason), describe)


if __name__ == "__main__":
    raise SystemExit(main())
