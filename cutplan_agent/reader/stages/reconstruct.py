"""Stage 7 reconstruct: document → 3D wireframe candidates → STEP.

reconstruct.ReconstructionPipeline runs its own steps 1-5 on document.json (interpret,
match views, generate and rank candidates, list ambiguities). The reasoning model then
compares the reprojected top candidates with the original views (candidates.png,
vision_adapter.confirm_candidates); the validator's ranking stays authoritative.
Products: provenance.json, report.md, and for a valid candidate reconstruction.step
and parameters.json. reconstruct.json in the work directory keeps the summary and the
model call.

PYTHONPATH=. python cutplan_agent/reader/stages/reconstruct.py --output-dir out/part [model options]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cutplan_agent.reader.stages import workdir
from cutplan_agent.reconstruct.pipeline import ReconstructionPipeline
from cutplan_agent.reconstruct.step6 import ReconstructionExporter


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


def run(
    work_dir: str | Path,
    *,
    clients=None,
    tolerance: float | None = None,
    max_candidates: int = 10,
    confirm: bool = True,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    """Returns {"reconstruction": <batch record>, "review_status": ...}.

    tolerance=None takes the document's suggested_tolerance_mm (0.01 mm if absent).
    """
    from cutplan_agent.reader.vlm import make_clients

    work_dir = Path(work_dir)
    output_dir = Path(output_dir) if output_dir else work_dir.parent
    drawing = workdir.load_document(work_dir)
    workdir.prepare("reconstruct", work_dir, output_dir, overwrite=overwrite)
    ocr, reason = clients or make_clients()
    marks = workdir.trace_marks((ocr, reason))
    effective_tolerance = (
        tolerance
        if tolerance is not None
        else float(drawing.metadata.get("suggested_tolerance_mm", 0.01))
    )
    # Result의 역할? 어떤 식으로 구현 했는지 설명하기
    result = ReconstructionPipeline(effective_tolerance, max_candidates).run(drawing)
    if confirm and reason.enabled:
        from cutplan_agent.reader.vision_adapter import confirm_candidates

        confirm_candidates(result, reason, work_dir)

    # Exporter의 역할? 어떤 식으로 구현 했는지 설명하기
    exporter = ReconstructionExporter(effective_tolerance)
    exporter.export_provenance(result, output_dir / "provenance.json")
    exporter.export_report(result, output_dir / "report.md")
    valid_ids = {e.candidate_id for e in result.evaluations if e.valid}
    best = next((c for c in result.candidates if c.id in valid_ids), None)
    if best is None:
        summary = {
            "attempted": True,
            "valid": False,
            "candidate_count": len(result.candidates),
            "review_status": result.review_request.get("status"),
            "artifacts": {
                "provenance": str(output_dir / "provenance.json"),
                "report": str(output_dir / "report.md"),
            },
        }
    else:
        evaluation = next(e for e in result.evaluations if e.candidate_id == best.id)
        exporter.export_step(best, output_dir / "reconstruction.step")
        exporter.export_parameters(best, output_dir / "parameters.json")
        summary = {"attempted": True, **candidate_record(best, evaluation, output_dir)}
    out = {
        "reconstruction": summary,
        "review_status": result.review_request.get("status"),
    }
    workdir.write_json(
        work_dir / "reconstruct.json",
        {
            **out,
            "tolerance_mm": effective_tolerance,
            "candidate_confirmation": result.metadata.get("candidate_confirmation"),
            "trace": workdir.trace_since((ocr, reason), marks),
        },
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = workdir.stage_parser(
        "Stage 7: reconstruct a 3D wireframe from document.json and export STEP",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Matching tolerance in mm (default: from the document, else 0.01)",
    )
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip the reasoning-VLM comparison of ranked 3D candidates",
    )
    args = parser.parse_args(argv)
    return workdir.cli(
        run,
        args,
        clients=workdir.clients_from_args(args),
        tolerance=args.tolerance,
        max_candidates=args.max_candidates,
        confirm=not args.no_confirm,
    )


if __name__ == "__main__":
    raise SystemExit(main())
