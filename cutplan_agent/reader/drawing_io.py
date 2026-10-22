"""Input routing: JSON contract, auto-analyzed DXF (default), or legacy layer-named DXF."""

import hashlib
import json
from pathlib import Path

from cutplan_agent.reconstruct.models import DrawingDocument

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".pdf"}


def load_drawing(
    path: str | Path,
    *,
    units: str | None = None,
    dxf_mode: str = "auto",
    input_mode: str = "auto",
    vlm_clients=None,
    work_dir: str | Path | None = None,
    **adapter_kw,
) -> DrawingDocument:
    """
    input_mode: "auto"   -> images/PDF through vision_adapter, DXF through dxf_adapter (API default)
                "vision" -> everything as pixels (OCR VLM / tesseract for text, OpenCV for geometry); a DXF is rasterized first (CLI default)
                "dxf"    -> DXF entities parsed directly (dxf_mode "auto" or legacy "layers")
    vlm_clients: (ocr_client, reason_client) from vlm.make_clients(); None disables models.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            document = DrawingDocument.from_dict(
                json.loads(path.read_text(encoding="utf-8")), str(path)
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"Invalid drawing JSON structure: {exc}") from exc
    elif suffix in IMAGE_SUFFIXES or (suffix == ".dxf" and input_mode == "vision"):
        from cutplan_agent.reader.vision_adapter import load_image_document
        from cutplan_agent.reader.vlm import make_clients

        ocr, reason = vlm_clients or make_clients(disabled=True)
        document = load_image_document(
            path,
            ocr,
            reason,
            work_dir or path.parent / f"{path.stem}_analysis",
            **adapter_kw,
        )
    elif suffix == ".dxf":
        if dxf_mode == "layers":
            from cutplan_agent.reader.drawing_io_legacy_layers import load_dxf_by_layers

            document = load_dxf_by_layers(path)
        else:
            from cutplan_agent.reader.dxf_adapter import load_dxf_document
            from cutplan_agent.reader.vlm import make_clients

            ocr, reason = vlm_clients or make_clients(disabled=True)
            document = load_dxf_document(
                path,
                ocr,
                reason,
                work_dir or path.with_suffix("").parent / f"{path.stem}_analysis",
                **adapter_kw,
            )
    else:
        raise ValueError("Supported inputs: .json, .dxf, .png/.jpg/.tif, .pdf")
    if units:
        document.metadata["units"] = units
    document.metadata["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return document
