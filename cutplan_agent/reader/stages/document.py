"""Stage 5 document: labelled views → document.json (front/top/right contract). No model.

For a DXF analysed by stages 1-4, the front/top/right views (left/bottom/back are
mirrored into them) become a DrawingDocument with dimensions as annotations, and the
title scale is checked against the drawn extents (dxf_adapter.build_document).
document.json is the same JSON contract that main.py accepts as input.

Other inputs are read here in one step: a JSON contract, a legacy layer-named DXF
(--dxf-mode layers), or an image/PDF (or a DXF with --input-mode vision). Image
reading is not yet split into stages; it writes its own sheet_analysis.json here.

PYTHONPATH=. python cutplan_agent/reader/stages/document.py --output-dir out/part
PYTHONPATH=. python cutplan_agent/reader/stages/document.py drawing.png --output-dir out/part [model options]
"""

from __future__ import annotations

from pathlib import Path

from cutplan_agent.reader.dxf_adapter import NotOrthographicSheet, build_document
from cutplan_agent.reader.stages import workdir
from cutplan_agent.reconstruct.models import DrawingDocument


def staged(source: str | Path | None, input_mode: str, dxf_mode: str) -> bool:
    """True when the drawing goes through stages 1-4 (a DXF read as entities)."""
    return source is None or (
        Path(source).suffix.lower() == ".dxf"
        and input_mode == "dxf"
        and dxf_mode == "auto"
    )


def from_stages(work_dir: Path) -> tuple[DrawingDocument, dict]:
    """Build the document from entities.json, views.json and sheet_analysis.json.

    View labels come from sheet_analysis.json, so a corrected label there is used
    when this stage runs again. Also returns the read record of entities.json.
    """
    entities, read = workdir.load_entities(work_dir)
    analysis = workdir.read_json(work_dir, "sheet_analysis.json")
    if analysis["sheet_type"] == "nesting":
        raise NotOrthographicSheet(analysis)
    views = workdir.labelled_views(work_dir, entities, analysis)
    title = workdir.title_from_dict(analysis["title_block"])
    drawing = build_document(Path(read["source"]), entities, views, title, analysis)
    return drawing, read


def run(
    work_dir: str | Path,
    *,
    source: str | Path | None = None,
    input_mode: str = "dxf",
    dxf_mode: str = "auto",
    units: str | None = None,
    dpi: int = 200,
    projection_default: str = "third",
    clients=None,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    work_dir = Path(work_dir)
    out = Path(output_dir) if output_dir else None
    if staged(source, input_mode, dxf_mode):
        drawing, read = from_stages(work_dir)
        workdir.prepare("document", work_dir, out, overwrite=overwrite)
        # what load_drawing adds to every document
        if units:
            drawing.metadata["units"] = units
        drawing.metadata["source_sha256"] = read["sha256"]
    else:
        from cutplan_agent.reader.drawing_io import load_drawing

        # the source is read here, so files of stages 1-4 from another run would mislead
        workdir.prepare("read", work_dir, out, overwrite=overwrite)
        kw = {"projection_default": projection_default}
        if Path(source).suffix.lower() != ".dxf" or input_mode == "vision":
            kw["dpi"] = dpi
        drawing = load_drawing(
            Path(source),
            units=units,
            dxf_mode=dxf_mode,
            input_mode=input_mode,
            vlm_clients=clients,
            work_dir=work_dir,
            **kw,
        )
    path = workdir.save_document(work_dir, drawing)
    return {
        "stage": "document",
        "source": drawing.source,
        "views": [v.name for v in drawing.views],
        "units": drawing.metadata.get("units"),
        "drawing_scale": drawing.metadata.get("drawing_scale"),
        "dimensions": drawing.metadata.get("dimensions"),
        "review": drawing.metadata.get("review", []),
        "outputs": [str(path)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = workdir.stage_parser(
        "Stage 5: turn labelled views into the front/top/right document"
    )
    parser.add_argument(
        "drawing",
        type=Path,
        nargs="?",
        help="Only for inputs not read by stages 1-4: JSON, image/PDF, layer DXF",
    )
    parser.add_argument(
        "--input-mode",
        choices=["vision", "dxf"],
        default="dxf",
        help="dxf (default): use stages 1-4; vision: read a DXF as an image",
    )
    parser.add_argument(
        "--dxf-mode",
        choices=["auto", "layers"],
        default="auto",
        help="layers: legacy FRONT/TOP/RIGHT layer names",
    )
    parser.add_argument(
        "--units", choices=["mm", "cm", "m", "inch"], help="Override input units"
    )
    parser.add_argument(
        "--dpi", type=int, default=200, help="Rasterization DPI for PDF/DXF inputs"
    )
    parser.add_argument(
        "--projection",
        choices=["first", "third"],
        default="third",
        help="Fallback projection for image inputs",
    )
    args = parser.parse_args(argv)
    if staged(args.drawing, args.input_mode, args.dxf_mode) and args.drawing:
        parser.error("a DXF read as entities comes from stages 1-4; omit the drawing")
    return workdir.cli(
        run,
        args,
        source=args.drawing,
        input_mode=args.input_mode,
        dxf_mode=args.dxf_mode,
        units=args.units,
        dpi=args.dpi,
        projection_default=args.projection,
        clients=workdir.clients_from_args(args),
    )


if __name__ == "__main__":
    raise SystemExit(main())
