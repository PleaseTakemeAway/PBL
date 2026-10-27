"""CLI. 레포 루트에서 실행한다.

PYTHONPATH=. python cutplan_agent/reader/main.py tests/fixtures/box.json --output-dir output
PYTHONPATH=. python cutplan_agent/reader/main.py part.dxf --analyze-only --reason-model qwen2.5vl:32b

The 3D reconstruction runs only with --with-3d; without it a run ends at the flat pattern
(docs/v3_upgrade.md 1.1).
"""

import argparse
import sys
from pathlib import Path

from cutplan_agent.reader.drawing_io import load_drawing
from cutplan_agent.reader.stages.workspace import THREE_D_OFF
from cutplan_agent.reader.unfold import run_unfold
from cutplan_agent.reconstruct.pipeline import ReconstructionPipeline
from cutplan_agent.reconstruct.step6 import ReconstructionExporter


def _print_unfold(record: dict) -> None:
    if record["status"] != "developed":
        print(
            f"flat pattern: {record['status']} ({record.get('error') or record.get('reason')})"
        )
        return
    blank = record["blank"]
    shown = ", ".join(
        f"{k}={blank[k]:.2f}"
        for k in (
            "length",
            "width",
            "outer_radius",
            "inner_radius",
            "angle_deg",
            "blank_diameter",
        )
        if isinstance(blank.get(k), (int, float))
    )
    print(
        f"flat pattern: {record['part_class']} -> {record['part_type']}: {shown}; params from {sorted(set(record['sources'].values()))}"
    )
    print(f"  outputs: {record['artifacts']['dxf']}, {record['artifacts']['png']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Six-stage orthographic drawing reconstruction"
    )
    parser.add_argument(
        "drawing",
        type=Path,
        nargs="+",
        help="One drawing, or one or more DXF files/directories in batch mode",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Predict all DXFs in the supplied files/directories and aggregate reconstructions",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="In batch mode, inspect only the immediate files in each directory",
    )
    parser.add_argument(
        "--units", choices=["mm", "cm", "m", "inch"], help="Override input units"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Matching tolerance in mm (default: 0.01 for JSON/DXF, pixel-derived for images)",
    )
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace prior generated outputs; remove stale STEP/parameters if no valid candidate remains",
    )
    parser.add_argument(
        "--input-mode",
        choices=["vision", "dxf"],
        default="vision",
        help="vision (default): read the sheet as an image via OCR VLM + OpenCV; dxf: parse DXF entities directly",
    )
    parser.add_argument(
        "--dxf-mode",
        choices=["auto", "layers"],
        default="auto",
        help="with --input-mode dxf: auto (analyze sheet) or legacy FRONT/TOP/RIGHT layers",
    )
    parser.add_argument(
        "--dpi", type=int, default=200, help="Rasterization DPI for PDF/DXF inputs"
    )
    parser.add_argument(
        "--with-3d",
        action="store_true",
        help="Also run the 3D reconstruction (off since 2026-10-27, docs/v3_upgrade.md 1.1)",
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip the reasoning-VLM comparison of ranked 3D candidates",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Where sheet renders and sheet_analysis.json go (default: <output-dir>/analysis)",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Run OCR, view labelling and calibration, write sheet_analysis.json, skip reconstruction",
    )
    parser.add_argument(
        "--no-unfold",
        action="store_true",
        help="Skip the class → dimensions → flat-pattern (전개도) stage",
    )
    parser.add_argument(
        "--no-vlm",
        action="store_true",
        help="Disable both VLMs; use regex + relative-position fallbacks only",
    )
    parser.add_argument(
        "--ocr-model",
        help="Small OCR VLM (overrides CUTPLAN_OCR_MODEL), e.g. qwen2.5vl:3b",
    )
    parser.add_argument(
        "--reason-model",
        help="Reasoning VLM (overrides CUTPLAN_REASON_MODEL), e.g. qwen2.5vl:32b or claude-sonnet-4-5",
    )
    parser.add_argument(
        "--ocr-base-url", help="OpenAI-compatible endpoint for the OCR model"
    )
    parser.add_argument("--reason-base-url", help="Endpoint for the reasoning model")
    parser.add_argument(
        "--reason-provider",
        choices=["openai", "anthropic"],
        help="Provider for the reasoning model",
    )
    parser.add_argument(
        "--projection",
        choices=["first", "third"],
        default="third",
        help="Fallback projection when neither title block nor model decides",
    )

    args = parser.parse_args(argv)
    from cutplan_agent.reader.vlm import make_clients

    clients = make_clients(
        disabled=args.no_vlm,
        ocr_model=args.ocr_model,
        reason_model=args.reason_model,
        ocr_base_url=args.ocr_base_url,
        reason_base_url=args.reason_base_url,
        reason_provider=args.reason_provider,
    )
    inputs = args.drawing
    batch_mode = args.batch or len(inputs) > 1 or any(path.is_dir() for path in inputs)
    if batch_mode:
        from cutplan_agent.reader.batch import run_batch

        try:
            result = run_batch(
                inputs,
                clients,
                args.output_dir,
                recursive=not args.no_recursive,
                analyze_only=args.analyze_only,
                overwrite=args.overwrite,
                units=args.units,
                tolerance=args.tolerance,
                max_candidates=args.max_candidates,
                input_mode=args.input_mode,
                dxf_mode=args.dxf_mode,
                dpi=args.dpi,
                projection_default=args.projection,
                confirm=not args.no_confirm,
                unfold=not args.no_unfold,
                three_d=args.with_3d,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"Batch failed: {exc}", file=sys.stderr)
            return 1
        summary = result["reconstruction"]["summary"]
        print(
            f"batch total={summary['total']} predicted={summary['predicted']} reconstructed={summary['reconstructed']} "
            f"prediction_only={summary['prediction_only']} no_valid_candidate={summary['no_valid_candidate']} failed={summary['failed']}"
        )
        print(f"predictions: {Path(result['paths']['predictions']).resolve()}")
        print(f"reconstruction: {Path(result['paths']['reconstruction']).resolve()}")
        accuracy = result["accuracy"]
        if accuracy["labeled_count"]:
            print(
                f"accuracy: {accuracy['correct']}/{accuracy['labeled_count']} ({accuracy['accuracy_pct']:.2f}%)"
            )
            print("| label | 개수 | 실제 맞춘 횟수 | accuracy |")
            print("|---|---:|---:|---:|")
            for row in accuracy["by_label"]:
                value = (
                    f"{row['accuracy_pct']:.2f}%"
                    if row["accuracy_pct"] is not None
                    else "N/A"
                )
                print(
                    f"| {row['label']} | {row['count']} | {row['correct']} | {value} |"
                )
        else:
            print("accuracy: unavailable (no sibling label.json files)")
        print(f"accuracy table: {Path(result['paths']['accuracy']).resolve()}")
        if "flat_patterns" in result["paths"]:
            fp = result["flat_patterns"]
            print(
                f"flat patterns: developed={fp['status_counts'].get('developed', 0)}/{fp['total']} "
                f"label_within_1pct={fp['within_1pct']}/{fp['evaluated']} -> {Path(result['paths']['flat_patterns']).resolve()}"
            )
        return 1 if summary["failed"] else 0

    args.drawing = inputs[0]
    work_dir = args.work_dir or args.output_dir / "analysis"

    if args.analyze_only:
        suffix = args.drawing.suffix.lower()
        if suffix == ".json":
            print("--analyze-only needs a DXF or image input", file=sys.stderr)
            return 1
        try:
            if suffix == ".dxf" and args.input_mode == "dxf":
                from cutplan_agent.reader.dxf_adapter import analyze_dxf

                a = analyze_dxf(
                    args.drawing,
                    clients[0],
                    clients[1],
                    work_dir,
                    projection_default=args.projection,
                )["analysis"]
            else:
                from cutplan_agent.reader.vision_adapter import analyze_image

                a = analyze_image(
                    args.drawing,
                    clients[0],
                    clients[1],
                    work_dir,
                    projection_default=args.projection,
                    dpi=args.dpi,
                )["analysis"]
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"Analysis failed: {exc}", file=sys.stderr)
            return 1
        if "ocr_source" in a:
            print(
                f"ocr={a['ocr_source']} texts={a['text_count']} kinds={a['text_kinds']} calibration={a['calibration']}"
            )
        else:
            print(f"reader={a['reader']} entities={a['entity_counts']}")
        print(
            f"sheet_type={a['sheet_type']} projection={a['projection']} part_class={a['part_class']} reconstructable={a['reconstructable']}"
        )
        for pl in a.get("plates", []):
            print(
                f"  plate {pl['id']}: {pl.get('material', '?'):<12} {pl.get('caption', '(no caption)'):<32} parts={pl['part_labels']}"
            )
        for v in a["views"]:
            print(
                f"  view {v['id']}: {v['label']:<12} conf={v['confidence']:.2f} src={v['source']} counts={v['counts']}"
                + (
                    f" dims={v['dimension_texts'][:6]}"
                    if v.get("dimension_texts")
                    else ""
                )
            )
        for r in a["review"]:
            print(f"  review: {r}")
        print(f"outputs: {work_dir.resolve()}/sheet_analysis.json, sheet.png")
        if not args.no_unfold:
            _print_unfold(run_unfold(a, None, clients[1], args.output_dir))
        return 0
    try:
        artifacts = [
            args.output_dir / name
            for name in (
                "provenance.json",
                "report.md",
                "reconstruction.step",
                "parameters.json",
            )
        ]
        if any(path.exists() for path in artifacts) and not args.overwrite:
            raise ValueError(
                "Generated output already exists; use a new --output-dir or --overwrite"
            )
        if any(path.exists() and not path.is_file() for path in artifacts):
            raise ValueError("An output artifact path is not a regular file")

        # Result의 역할? 어떤 식으로 구현 했는지 설명하기
        kw = {"projection_default": args.projection}
        if args.drawing.suffix.lower() != ".dxf" or args.input_mode == "vision":
            kw["dpi"] = args.dpi
        drawing = load_drawing(
            args.drawing,
            units=args.units,
            dxf_mode=args.dxf_mode,
            input_mode=args.input_mode,
            vlm_clients=clients,
            work_dir=work_dir,
            **kw,
        )
        if not args.no_unfold:
            _print_unfold(
                run_unfold(
                    drawing.metadata.get("sheet_analysis", {}),
                    drawing,
                    clients[1],
                    args.output_dir,
                )
            )
        if not args.with_3d:
            print(f"3D reconstruction skipped: {THREE_D_OFF}")
            return 0
        tolerance = (
            args.tolerance
            if args.tolerance is not None
            else float(drawing.metadata.get("suggested_tolerance_mm", 0.01))
        )
        result = ReconstructionPipeline(tolerance, args.max_candidates).run(drawing)
        if not args.no_confirm and clients[1].enabled:
            from cutplan_agent.reader.vision_adapter import confirm_candidates

            confirm_candidates(result, clients[1], work_dir)

        # Exporter의 역할? 어떤 식으로 구현 했는지 설명하기
        exporter = ReconstructionExporter(tolerance)
        exporter.export_provenance(result, args.output_dir / "provenance.json")
        exporter.export_report(result, args.output_dir / "report.md")
        valid = {e.candidate_id for e in result.evaluations if e.valid}
        best = next((c for c in result.candidates if c.id in valid), None)
        if best is None:
            if args.overwrite:
                for name in ("reconstruction.step", "parameters.json"):
                    (args.output_dir / name).unlink(missing_ok=True)
            print(
                "No valid candidate. Inspect report.md and provenance.json.",
                file=sys.stderr,
            )
            return 2
        exporter.export_step(best, args.output_dir / "reconstruction.step")
        exporter.export_parameters(best, args.output_dir / "parameters.json")
        print(
            f"Candidate: {best.id}; vertices: {len(best.vertices)}; edges: {len(best.edges)}"
        )
        print(
            f"Review: {result.review_request['status']}; outputs: {args.output_dir.resolve()}"
        )
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        from cutplan_agent.reader.dxf_adapter import NotOrthographicSheet as _A
        from cutplan_agent.reader.vision_adapter import NotOrthographicSheet as _B

        if isinstance(exc, (_A, _B)):
            print(
                f"{exc}. Plate list written to {work_dir.resolve()}/sheet_analysis.json",
                file=sys.stderr,
            )
            return 3
        print(f"Reconstruction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
