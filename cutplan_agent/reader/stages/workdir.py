"""Files the stages hand to each other, and the command-line options they share.

Every stage reads what earlier stages left in the work directory and writes its own
files there, so any stage can run alone once its inputs exist. Final products go to
the output directory; the work directory defaults to <output-dir>/analysis.

A stage first removes its own outputs and those of every later stage, so a file in
the work directory never mixes results from two runs. Without `overwrite` it refuses
instead of removing anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cutplan_agent.reader.dxf_adapter import TitleBlock, ViewCandidate
from cutplan_agent.reader.dxf_reader import RawEntity
from cutplan_agent.reconstruct.models import DrawingDocument

ORDER = ("read", "title", "segment", "label", "document", "unfold", "reconstruct")
WORK_FILES = {
    "read": ("entities.json",),
    "title": ("title.json", "title_block.png"),
    "segment": ("views.json",),
    "label": ("sheet_analysis.json", "sheet_labeled.png", "sheet.png"),
    "document": ("document.json",),
    "unfold": ("unfold.json",),
    "reconstruct": ("reconstruct.json", "candidates.png"),
}
PRODUCT_FILES = {
    "unfold": ("flat_pattern.json", "flat_pattern.dxf", "flat_pattern.png"),
    "reconstruct": (
        "provenance.json",
        "report.md",
        "reconstruction.step",
        "parameters.json",
    ),
}


def prepare(
    stage: str,
    work_dir: Path,
    output_dir: Path | None = None,
    *,
    overwrite: bool = False,
) -> None:
    """Clear the outputs of `stage` and later stages; refuse without overwrite.

    Final products are cleared only when `output_dir` is given: library callers such
    as analyze_dxf pass none, so files next to an input drawing are never touched.
    """
    later = ORDER[ORDER.index(stage) :]
    paths = [work_dir / name for s in later for name in WORK_FILES[s]]
    if output_dir is not None:
        paths += [output_dir / name for s in later for name in PRODUCT_FILES.get(s, ())]
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise ValueError(
            f"{stage} stage outputs already exist ({', '.join(str(p) for p in existing)}); "
            "use --overwrite or a new --output-dir"
        )
    for path in existing:
        path.unlink()
    work_dir.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=list) + "\n",
        encoding="utf-8",
    )
    return path


def read_json(work_dir: Path, name: str) -> Any:
    path = work_dir / name
    if not path.is_file():
        stage = next(s for s in ORDER if name in WORK_FILES[s])
        raise FileNotFoundError(f"{path} not found; run the {stage} stage first")
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- objects
def _tuple(value):
    return tuple(value) if isinstance(value, list) else value


def entity_from_dict(value: dict) -> RawEntity:
    """JSON turns tuples into lists; restore them so the entity equals what read_dxf made."""
    return RawEntity(
        **{
            **value,
            "points": [tuple(p) for p in value["points"]],
            "center": _tuple(value["center"]),
            "attributes": {k: _tuple(v) for k, v in value["attributes"].items()},
        }
    )


def load_entities(work_dir: Path) -> tuple[list[RawEntity], dict]:
    """Entities and the read record (source path, sha256, reader, units)."""
    data = read_json(work_dir, "entities.json")
    entities = [entity_from_dict(e) for e in data["entities"]]
    return entities, {k: v for k, v in data.items() if k != "entities"}


def entities_to_list(entities: list[RawEntity]) -> list[dict]:
    return [asdict(e) for e in entities]


def views_to_list(views: list[ViewCandidate], entities: list[RawEntity]) -> list[dict]:
    """Views refer to entities by their index in entities.json."""
    index = {id(e): i for i, e in enumerate(entities)}
    return [
        {
            "id": v.id,
            "bbox": v.bbox,
            "label": v.label,
            "confidence": v.confidence,
            "label_source": v.label_source,
            "reason": v.reason,
            "counts": v.counts(),
            "entities": [index[id(e)] for e in v.entities],
            "dimensions": [index[id(e)] for e in v.dimensions],
            "texts": [index[id(e)] for e in v.texts],
        }
        for v in views
    ]


def views_from_list(
    items: list[dict], entities: list[RawEntity]
) -> list[ViewCandidate]:
    return [
        ViewCandidate(
            item["id"],
            tuple(item["bbox"]),
            [entities[i] for i in item["entities"]],
            dimensions=[entities[i] for i in item["dimensions"]],
            texts=[entities[i] for i in item["texts"]],
            label=item["label"],
            confidence=item["confidence"],
            label_source=item["label_source"],
            reason=item["reason"],
        )
        for item in items
    ]


def labelled_views(
    work_dir: Path, entities: list[RawEntity], analysis: dict
) -> list[ViewCandidate]:
    """Views of views.json carrying the labels that sheet_analysis.json decided."""
    views = views_from_list(read_json(work_dir, "views.json")["views"], entities)
    labels = {v["id"]: v for v in analysis["views"]}
    for v in views:
        a = labels[v.id]
        v.label, v.confidence, v.label_source, v.reason = (
            a["label"],
            a["confidence"],
            a["source"],
            a["reason"],
        )
    return views


def title_from_dict(value: dict) -> TitleBlock:
    return TitleBlock(**{**value, "region": _tuple(value["region"])})


def save_document(work_dir: Path, drawing: DrawingDocument) -> Path:
    return write_json(
        work_dir / "document.json",
        {
            "source": drawing.source,
            "document": {
                "metadata": drawing.metadata,
                "views": [asdict(v) for v in drawing.views],
            },
        },
    )


def load_document(work_dir: Path) -> DrawingDocument:
    data = read_json(work_dir, "document.json")
    return DrawingDocument.from_dict(data["document"], data["source"])


# ----------------------------------------------------------------------------- model trace
def trace_marks(clients) -> list[int]:
    return [len(client.trace) for client in clients]


def trace_since(clients, marks: list[int]) -> list[dict]:
    """Model calls a stage made: OCR calls first, then reasoning calls."""
    return [record for c, m in zip(clients, marks) for record in c.trace[m:]]


# ----------------------------------------------------------------------------- command line
def add_model_args(parser: argparse.ArgumentParser) -> None:
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


def clients_from_args(args: argparse.Namespace):
    from cutplan_agent.reader.vlm import make_clients

    return make_clients(
        disabled=args.no_vlm,
        ocr_model=args.ocr_model,
        reason_model=args.reason_model,
        ocr_base_url=args.ocr_base_url,
        reason_base_url=args.reason_base_url,
        reason_provider=args.reason_provider,
    )


def stage_parser(description: str) -> argparse.ArgumentParser:
    """Options every stage takes. Stages that call no model ignore the model options,
    so the same options can be passed to every stage."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Final products of one drawing (default: output)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Stage files and images (default: <output-dir>/analysis)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace this stage's outputs and remove those of later stages",
    )
    add_model_args(parser)
    return parser


def dirs(args: argparse.Namespace) -> tuple[Path, Path]:
    return args.work_dir or args.output_dir / "analysis", args.output_dir


def cli(run, args: argparse.Namespace, **kw) -> int:
    """Run a stage from its command line and print its JSON summary.

    Exit codes follow main.py: 1 failure, 3 nesting sheet (no orthographic views).
    """
    work_dir, output_dir = dirs(args)
    try:
        summary = run(work_dir, output_dir=output_dir, overwrite=args.overwrite, **kw)
    except (ValueError, RuntimeError, OSError) as exc:
        from cutplan_agent.reader.dxf_adapter import NotOrthographicSheet as _A
        from cutplan_agent.reader.vision_adapter import NotOrthographicSheet as _B

        if isinstance(exc, (_A, _B)):
            print(
                f"{exc}. Plate list is in {work_dir}/sheet_analysis.json",
                file=sys.stderr,
            )
            return 3
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=list))
    return 0
