"""Stage 13 export: write provenance.json and report.md, and for the best valid candidate
reconstruction.step and parameters.json. No model.

in : stages/11_reconstruct.json, stages/12_confirm.json when it ran
out: stages/13_export.json, provenance.json, report.md, reconstruction.step, parameters.json

PYTHONPATH=. python cutplan_agent/reader/stages/export.py <work>
"""

from pathlib import Path
from typing import Any

from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    result_from_json,
    stage_function,
    stage_parser,
)
from cutplan_agent.reconstruct.step6 import ReconstructionExporter

STAGE = "export"


def candidate_record(candidate, evaluation, item_dir: Path) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "valid": evaluation.valid,
        "score": evaluation.score,
        "extents_mm": dict(zip("xyz", candidate.extents)),
        "vertices": len(candidate.vertices),
        "edges": len(candidate.edges),
        "features": candidate.features,
        "parameters": candidate.parameters,
        "artifacts": {
            "step": str(item_dir / "reconstruction.step") if evaluation.valid else None,
            "parameters": str(item_dir / "parameters.json")
            if evaluation.valid
            else None,
            "provenance": str(item_dir / "provenance.json"),
            "report": str(item_dir / "report.md"),
        },
    }


@stage_function(STAGE)
def run(ws: Workspace) -> dict:
    built = ws.load("reconstruct")
    if built["status"] != "done":
        return ws.save(
            STAGE, {"status": "skipped", "reason": f"reconstruct: {built['reason']}"}
        )
    result = result_from_json(built["result"])
    if ws.has("confirm"):
        confirmed = ws.load("confirm")
        if confirmed["status"] == "done":
            if confirmed["recorded"]:
                result.metadata["candidate_confirmation"] = confirmed["confirmation"]
            result.review_request = confirmed["review_request"]
    root = ws.root
    exporter = ReconstructionExporter(built["tolerance"])
    exporter.export_provenance(result, root / "provenance.json")
    exporter.export_report(result, root / "report.md")
    valid_ids = {e.candidate_id for e in result.evaluations if e.valid}
    best = next((c for c in result.candidates if c.id in valid_ids), None)
    if best is None:
        # a stale model from an earlier run must not survive
        (root / "reconstruction.step").unlink(missing_ok=True)
        (root / "parameters.json").unlink(missing_ok=True)
        outcome = "no_valid_candidate"
        reconstruction = {
            "attempted": True,
            "valid": False,
            "candidate_count": len(result.candidates),
            "review_status": result.review_request.get("status"),
            "artifacts": {
                "provenance": str(root / "provenance.json"),
                "report": str(root / "report.md"),
            },
        }
    else:
        evaluation = next(e for e in result.evaluations if e.candidate_id == best.id)
        exporter.export_step(best, root / "reconstruction.step")
        exporter.export_parameters(best, root / "parameters.json")
        outcome = "reconstructed"
        reconstruction = {
            "attempted": True,
            **candidate_record(best, evaluation, root),
        }
    return ws.save(
        STAGE,
        {"status": "done", "outcome": outcome, "reconstruction": reconstruction},
    )


def describe(record: dict) -> str:
    r = record["reconstruction"]
    files = ", ".join(v for v in r["artifacts"].values() if v)
    best = f" {r['candidate_id']} extents={r['extents_mm']}" if r.get("valid") else ""
    return f"{record['outcome']}{best}\n{files}"


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__).parse_args(argv)
    return cli(args.work, lambda: run(args.work), describe)


if __name__ == "__main__":
    raise SystemExit(main())
