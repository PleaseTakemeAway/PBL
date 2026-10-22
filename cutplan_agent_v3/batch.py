"""Batch prediction and per-drawing reconstruction for folders of DXF files."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from copy import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from drawing_io import load_drawing
from pipeline import ReconstructionPipeline
from step6 import ReconstructionExporter
from unfold import evaluate_against_label, run_unfold
from vlm import PART_CLASSES, VLMClient


def discover_dxf(inputs: Iterable[str | Path], *, recursive: bool = True) -> list[Path]:
    """Return unique DXF files from explicit files and directories in stable order."""
    found: dict[Path, Path] = {}
    for value in inputs:
        path = Path(value)
        if path.is_file():
            if path.suffix.lower() != ".dxf":
                raise ValueError(f"Batch mode accepts DXF files only: {path}")
            found.setdefault(path.resolve(), path)
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for candidate in iterator:
                if candidate.is_file() and candidate.suffix.lower() == ".dxf":
                    found.setdefault(candidate.resolve(), candidate)
        else:
            raise ValueError(f"Input does not exist: {path}")
    paths = sorted(found.values(), key=lambda item: str(item.resolve()).lower())
    if not paths:
        raise ValueError("No DXF files were found in the supplied inputs")
    return paths


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _fresh_clients(clients: tuple[VLMClient, VLMClient]) -> tuple[VLMClient, VLMClient]:
    """Keep each drawing's trace separate while reusing the same configuration."""
    clones = []
    for client in clients:
        clone = copy(client)
        clone.trace = []
        clones.append(clone)
    return clones[0], clones[1]


def _prediction(analysis: dict[str, Any]) -> dict[str, Any]:
    title = analysis.get("title_block", {})
    decision = analysis.get("vlm_decision", {})
    return {
        "sheet_type": analysis.get("sheet_type"),
        "part_class": analysis.get("part_class"),
        "final_part_class": analysis.get("part_class"),
        "part_class_reported": decision.get("part_class_reported"),
        "part_class_scores": decision.get("part_class_scores"),
        "part_class_probabilities": analysis.get("part_class_probabilities"),
        "part_class_probability_source": analysis.get("part_class_probability_source"),
        "part_class_consistent": decision.get("part_class_consistent"),
        "part_class_reason": decision.get("notes"),
        "reconstructable_from_views": analysis.get("reconstructable"),
        "projection": analysis.get("projection"),
        "units": analysis.get("file_units") or title.get("units"),
        "drawing_no": title.get("drawing_no"),
        "material": title.get("material"),
        "thickness_mm": title.get("thickness_mm"),
        "views": [
            {
                key: view.get(key)
                for key in (
                    "id",
                    "label",
                    "confidence",
                    "source",
                    "reason",
                    "bbox",
                    "bbox_px",
                )
                if key in view
            }
            for view in analysis.get("views", [])
        ],
        "review": analysis.get("review", []),
        "vlm_trace": analysis.get("vlm_trace", []),
    }


def _ground_truth(path: Path) -> str | None:
    """Read a sibling label only for post-prediction evaluation."""
    label_path = path.parent / "label.json"
    if not label_path.is_file():
        return None
    try:
        value = json.loads(label_path.read_text(encoding="utf-8")).get("class")
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
        return None
    return value if value in PART_CLASSES else None


def _label(path: Path) -> dict:
    try:
        value = json.loads((path.parent / "label.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _flat_pattern_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for record in records:
        fp = record.get("flat_pattern") or {}
        evaluation = fp.get("evaluation") or {}
        items.append(
            {
                "id": record["id"],
                "ground_truth_label": record.get("ground_truth_label"),
                "part_class": fp.get("part_class"),
                "part_type": fp.get("part_type"),
                "status": fp.get("status"),
                "params": fp.get("params"),
                "sources": fp.get("sources"),
                "blank": fp.get("blank"),
                "error": fp.get("error") or fp.get("reason"),
                "evaluation": evaluation or None,
                "artifacts": fp.get("artifacts"),
            }
        )
    statuses = Counter(item["status"] for item in items if item["status"])
    evaluated = [
        item
        for item in items
        if item["evaluation"] and item["evaluation"].get("within_1pct") is not None
    ]
    return {
        "total": len(items),
        "status_counts": dict(sorted(statuses.items())),
        "evaluated": len(evaluated),
        "within_1pct": sum(item["evaluation"]["within_1pct"] for item in evaluated),
        "items": items,
    }


def _flat_pattern_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Flat pattern (전개도) results",
        "",
        f"developed {summary['status_counts'].get('developed', 0)}/{summary['total']}; "
        f"label match within 1 %: {summary['within_1pct']}/{summary['evaluated']}",
        "",
        "| id | GT class | class → part_type | status | blank | max rel. error vs label |",
        "|---|---|---|---|---|---:|",
    ]
    for item in summary["items"]:
        blank = item["blank"] or {}
        shown = ", ".join(
            f"{k}={blank[k]:.1f}"
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
        error = (item["evaluation"] or {}).get("max_rel_error")
        lines.append(
            f"| {item['id']} | {item['ground_truth_label'] or ''} | {item['part_class'] or ''} → {item['part_type'] or ''} | "
            f"{item['status'] or ''}{' (' + item['error'] + ')' if item['error'] else ''} | {shown} | "
            f"{f'{100 * error:.2f}%' if error is not None else 'N/A'} |"
        )
    return "\n".join(lines) + "\n"


def _accuracy(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    total = correct = 0
    for label in PART_CLASSES:
        selected = [
            record for record in records if record.get("ground_truth_label") == label
        ]
        hits = sum(record.get("prediction_correct") is True for record in selected)
        count = len(selected)
        total += count
        correct += hits
        rows.append(
            {
                "label": label,
                "count": count,
                "correct": hits,
                "accuracy": hits / count if count else None,
                "accuracy_pct": round(100 * hits / count, 2) if count else None,
            }
        )
    return {
        "labeled_count": total,
        "correct": correct,
        "accuracy": correct / total if total else None,
        "accuracy_pct": round(100 * correct / total, 2) if total else None,
        "by_label": rows,
    }


def _accuracy_markdown(report: dict[str, Any]) -> str:
    lines = ["# Part-class prediction accuracy", ""]
    if not report["labeled_count"]:
        return "\n".join(
            lines + ["No sibling `label.json` ground truth was found.", ""]
        )
    lines += [
        f"Overall: {report['correct']}/{report['labeled_count']} ({report['accuracy_pct']:.2f}%)",
        "",
        "| label | 개수 | 실제 맞춘 횟수 | accuracy |",
        "|---|---:|---:|---:|",
    ]
    for row in report["by_label"]:
        value = (
            f"{row['accuracy_pct']:.2f}%" if row["accuracy_pct"] is not None else "N/A"
        )
        lines.append(
            f"| {row['label']} | {row['count']} | {row['correct']} | {value} |"
        )
    return "\n".join(lines) + "\n"


def _candidate_record(candidate, evaluation, item_dir: Path) -> dict[str, Any]:
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


def _item_id(path: Path, used: set[str]) -> str:
    base = re.sub(r"[^0-9A-Za-z._-]+", "_", path.stem).strip("._") or "drawing"
    value, index = base, 2
    while value.lower() in used:
        value = f"{base}_{index}"
        index += 1
    used.add(value.lower())
    return value


def run_batch(
    inputs: Iterable[str | Path],
    clients: tuple[VLMClient, VLMClient],
    output_dir: str | Path,
    *,
    recursive: bool = True,
    analyze_only: bool = False,
    overwrite: bool = False,
    units: str | None = None,
    tolerance: float | None = None,
    max_candidates: int = 10,
    input_mode: str = "dxf",
    dxf_mode: str = "auto",
    dpi: int = 200,
    projection_default: str = "third",
    confirm: bool = True,
    unfold: bool = True,
) -> dict[str, Any]:
    """Predict every discovered DXF, reconstruct each drawing, then aggregate results."""
    inputs = list(inputs)
    output_dir = Path(output_dir)
    aggregate_paths = [
        output_dir / "predictions.json",
        output_dir / "reconstruction.json",
        output_dir / "accuracy.md",
        output_dir / "flat_patterns.json",
        output_dir / "flat_patterns.md",
    ]
    if not overwrite and any(path.exists() for path in aggregate_paths):
        raise ValueError(
            f"Batch output already exists in {output_dir}; use --overwrite or a new output directory"
        )

    paths = discover_dxf(inputs, recursive=recursive)
    records: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for path in paths:
        sample_id = _item_id(path, used_ids)
        item_dir = output_dir / sample_id
        work_dir = item_dir / "analysis"
        record: dict[str, Any] = {
            "id": sample_id,
            "source": str(path.resolve()),
            "status": "failed",
            "prediction": None,
            "flat_pattern": None,
            "reconstruction": None,
        }
        ocr, reason = _fresh_clients(clients)
        try:
            generated = [
                item_dir / name
                for name in (
                    "provenance.json",
                    "report.md",
                    "reconstruction.step",
                    "parameters.json",
                )
            ]
            if not overwrite and any(artifact.exists() for artifact in generated):
                raise ValueError(
                    f"Generated output already exists for {sample_id}; use --overwrite or a new output directory"
                )
            if overwrite:
                # A prediction-only or failed rerun must not leave a stale model.
                (item_dir / "reconstruction.step").unlink(missing_ok=True)
                (item_dir / "parameters.json").unlink(missing_ok=True)
                for name in (
                    "flat_pattern.json",
                    "flat_pattern.dxf",
                    "flat_pattern.png",
                ):
                    (item_dir / name).unlink(missing_ok=True)
            adapter_kw: dict[str, Any] = {"projection_default": projection_default}
            if input_mode == "vision":
                adapter_kw["dpi"] = dpi
            if analyze_only:
                if input_mode == "dxf":
                    from dxf_adapter import analyze_dxf

                    analysis = analyze_dxf(path, ocr, reason, work_dir, **adapter_kw)[
                        "analysis"
                    ]
                else:
                    from vision_adapter import analyze_image

                    analysis = analyze_image(path, ocr, reason, work_dir, **adapter_kw)[
                        "analysis"
                    ]
                record["prediction"] = _prediction(analysis)
                record["status"] = "predicted"
                if unfold:
                    record["flat_pattern"] = run_unfold(
                        analysis, None, reason, item_dir
                    )
                continue
            drawing = load_drawing(
                path,
                units=units,
                dxf_mode=dxf_mode,
                input_mode=input_mode,
                vlm_clients=(ocr, reason),
                work_dir=work_dir,
                **adapter_kw,
            )
            analysis = drawing.metadata.get("sheet_analysis", {})
            record["prediction"] = _prediction(analysis)
            # class → dimensions → development, independent of the 3D wireframe search below
            if unfold:
                record["flat_pattern"] = run_unfold(analysis, drawing, reason, item_dir)
            if analysis.get("reconstructable") is False:
                record["status"] = "prediction_only"
                record["reconstruction"] = {
                    "attempted": False,
                    "reason": "prediction says the shape is not reconstructable from orthographic views alone",
                }
            else:
                effective_tolerance = (
                    tolerance
                    if tolerance is not None
                    else float(drawing.metadata.get("suggested_tolerance_mm", 0.01))
                )
                result = ReconstructionPipeline(
                    effective_tolerance, max_candidates
                ).run(drawing)
                if confirm and reason.enabled:
                    from vision_adapter import confirm_candidates

                    confirm_candidates(result, reason, work_dir)
                exporter = ReconstructionExporter(effective_tolerance)
                exporter.export_provenance(result, item_dir / "provenance.json")
                exporter.export_report(result, item_dir / "report.md")
                valid_ids = {
                    evaluation.candidate_id
                    for evaluation in result.evaluations
                    if evaluation.valid
                }
                best = next(
                    (
                        candidate
                        for candidate in result.candidates
                        if candidate.id in valid_ids
                    ),
                    None,
                )
                if best is None:
                    if overwrite:
                        (item_dir / "reconstruction.step").unlink(missing_ok=True)
                        (item_dir / "parameters.json").unlink(missing_ok=True)
                    record["status"] = "no_valid_candidate"
                    record["reconstruction"] = {
                        "attempted": True,
                        "valid": False,
                        "candidate_count": len(result.candidates),
                        "review_status": result.review_request.get("status"),
                        "artifacts": {
                            "provenance": str(item_dir / "provenance.json"),
                            "report": str(item_dir / "report.md"),
                        },
                    }
                else:
                    evaluation = next(
                        item
                        for item in result.evaluations
                        if item.candidate_id == best.id
                    )
                    exporter.export_step(best, item_dir / "reconstruction.step")
                    exporter.export_parameters(best, item_dir / "parameters.json")
                    record["status"] = "reconstructed"
                    record["reconstruction"] = {
                        "attempted": True,
                        **_candidate_record(best, evaluation, item_dir),
                    }
        except Exception as exc:
            from dxf_adapter import NotOrthographicSheet as DxfNotOrthographic
            from vision_adapter import NotOrthographicSheet as VisionNotOrthographic

            if isinstance(exc, (DxfNotOrthographic, VisionNotOrthographic)):
                record["status"] = "prediction_only"
                record["prediction"] = _prediction(exc.analysis)
                record["reconstruction"] = {"attempted": False, "reason": str(exc)}
            else:
                record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            # Ground truth is loaded only after inference/reconstruction has ended.
            label = _ground_truth(path)
            predicted = (
                record["prediction"].get("final_part_class")
                if record.get("prediction")
                else None
            )
            record["ground_truth_label"] = label
            record["prediction_correct"] = (
                (predicted == label) if label is not None else None
            )
            if record.get("flat_pattern"):
                record["flat_pattern"]["evaluation"] = evaluate_against_label(
                    record["flat_pattern"], _label(path)
                )
            _write_json(item_dir / "prediction.json", record)
            records.append(record)

    statuses = Counter(record["status"] for record in records)
    classes = Counter(
        record["prediction"]["part_class"]
        for record in records
        if record.get("prediction") and record["prediction"].get("part_class")
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    accuracy = _accuracy(records)
    predictions = {
        "schema_version": 1,
        "generated_at": generated_at,
        "inputs": [str(Path(value).resolve()) for value in inputs],
        "total": len(records),
        "status_counts": dict(sorted(statuses.items())),
        "part_class_counts": dict(sorted(classes.items())),
        "accuracy": accuracy,
        "predictions": records,
    }
    reconstruction_items = [
        {
            "id": record["id"],
            "source": record["source"],
            "status": record["status"],
            "part_class": record["prediction"].get("part_class")
            if record.get("prediction")
            else None,
            "reconstruction": record.get("reconstruction"),
            **({"error": record["error"]} if "error" in record else {}),
        }
        for record in records
    ]
    reconstruction = {
        "schema_version": 1,
        "generated_at": generated_at,
        "mode": "independent_per_drawing",
        "note": "Unrelated DXF coordinate systems are not merged into one STEP; this file indexes each independent reconstruction.",
        "summary": {
            "total": len(records),
            "predicted": statuses.get("predicted", 0),
            "reconstructed": statuses.get("reconstructed", 0),
            "prediction_only": statuses.get("prediction_only", 0),
            "no_valid_candidate": statuses.get("no_valid_candidate", 0),
            "failed": statuses.get("failed", 0),
        },
        "items": reconstruction_items,
    }
    _write_json(aggregate_paths[0], predictions)
    _write_json(aggregate_paths[1], reconstruction)
    aggregate_paths[2].parent.mkdir(parents=True, exist_ok=True)
    aggregate_paths[2].write_text(_accuracy_markdown(accuracy), encoding="utf-8")
    flat_patterns = _flat_pattern_summary(records)
    if unfold:
        _write_json(aggregate_paths[3], flat_patterns)
        aggregate_paths[4].write_text(
            _flat_pattern_markdown(flat_patterns), encoding="utf-8"
        )
    return {
        "predictions": predictions,
        "reconstruction": reconstruction,
        "accuracy": accuracy,
        "flat_patterns": flat_patterns,
        "paths": {
            "predictions": str(aggregate_paths[0]),
            "reconstruction": str(aggregate_paths[1]),
            "accuracy": str(aggregate_paths[2]),
            **({"flat_patterns": str(aggregate_paths[3])} if unfold else {}),
        },
    }
