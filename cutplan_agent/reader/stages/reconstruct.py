"""Stage 11 reconstruct: 3D wireframe candidates from the orthographic views, ranked by the
validator (reconstruct/ steps 1-5). No model.

Skipped when the view_labels model judged the shape not reconstructable from the views.
in : analysis/sheet_analysis.json, stages/08_document.json
out: stages/11_reconstruct.json (full ReconstructionResult: views, candidates, evaluations, review)

PYTHONPATH=. python cutplan_agent/reader/stages/reconstruct.py <work> [--tolerance MM] [--max-candidates 10]
"""

from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    stage_function,
    stage_parser,
)
from cutplan_agent.reconstruct.pipeline import ReconstructionPipeline

STAGE = "reconstruct"
NOT_RECONSTRUCTABLE = (
    "prediction says the shape is not reconstructable from orthographic views alone"
)


@stage_function(STAGE)
def run(
    ws: Workspace, *, tolerance: float | None = None, max_candidates: int = 10
) -> dict:
    analysis = ws.analysis()
    document = ws.document()
    if document is None:
        reason = ws.load("document").get("reason") or "no document"
        return ws.save(STAGE, {"status": "skipped", "reason": f"document: {reason}"})
    if analysis.get("reconstructable") is False:
        return ws.save(
            STAGE,
            {
                "status": "skipped",
                "reason": NOT_RECONSTRUCTABLE,
                "not_reconstructable": True,
            },
        )
    effective = (
        tolerance
        if tolerance is not None
        else float(document.metadata.get("suggested_tolerance_mm", 0.01))
    )
    result = ReconstructionPipeline(effective, max_candidates).run(document)
    return ws.save(
        STAGE,
        {
            "status": "done",
            "tolerance": effective,
            "max_candidates": max_candidates,
            "valid": [e.candidate_id for e in result.evaluations if e.valid],
            "result": result.to_dict(),
        },
    )


def describe(record: dict) -> str:
    result = record["result"]
    scores = ", ".join(
        f"{e['candidate_id']}={e['score']:.3f}{'' if e['valid'] else ' (invalid)'}"
        for e in result["evaluations"]
    )
    return (
        f"{len(result['candidates'])} candidates, valid={record['valid']} "
        f"tolerance={record['tolerance']}\nscores: {scores}\n"
        f"review: {result['review_request'].get('status')}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = stage_parser(__doc__)
    parser.add_argument("--tolerance", type=float, help="matching tolerance in mm")
    parser.add_argument("--max-candidates", type=int, default=10)
    args = parser.parse_args(argv)
    return cli(
        args.work,
        lambda: run(
            args.work, tolerance=args.tolerance, max_candidates=args.max_candidates
        ),
        describe,
    )


if __name__ == "__main__":
    raise SystemExit(main())
