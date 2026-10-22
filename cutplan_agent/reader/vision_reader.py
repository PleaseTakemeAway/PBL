"""Vision-first sheet reader: pixels in, text items + geometry primitives out.

The sheet is treated as an image whatever the source (PNG/JPG, PDF page, or a DXF
rasterized once). Reading is split by what each tool is good at:
  * text -> raw OCR VLM (tiled), then reasoning JSON; tesseract as fallback
  * line / arc / circle geometry      -> OpenCV (deterministic, pixel accurate)
Every item keeps pixel coordinates (origin top-left, y down); calibration to mm
happens later in vision_adapter.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from math import atan2, cos, degrees, hypot, sin
from pathlib import Path

import numpy as np

from cutplan_agent.reader.vlm import VLMClient, read_ocr_task

PxBox = tuple[float, float, float, float]  # x0, y0, x1, y1 in pixels


@dataclass
class TextItem:
    text: str
    bbox: PxBox
    kind: str = "other"  # dimension | label | note | title | table | caption | other
    confidence: float = 0.0
    source: str = "ocr"
    value: float | None = None  # numeric value for dimensions / captions
    feature: str | None = None  # diameter | radius | thickness | count
    count: int | None = None  # 2-Ø13 -> 2

    @property
    def center(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2)


@dataclass
class PxPrimitive:
    kind: str  # line | circle | arc
    points: list[tuple[float, float]] = field(default_factory=list)
    center: tuple[float, float] | None = None
    radius: float | None = None
    line_type: str = "visible"  # visible | hidden | center
    ink_ratio: float = 1.0
    source: str = "cv"


@dataclass
class SheetImage:
    path: Path
    width: int
    height: int
    gray: np.ndarray  # uint8 HxW
    source: str  # png | pdf | dxf-raster
    dpi: int | None = None


# ----------------------------------------------------------------------------- loading
def load_sheet(
    path: str | Path,
    work_dir: str | Path,
    *,
    dpi: int = 200,
    page: int = 1,
    min_side_px: int = 2000,
) -> SheetImage:
    import cv2

    path, work_dir = Path(path), Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        img_path, source = path, "image"
    elif suffix == ".pdf":
        if not shutil.which("pdftoppm"):
            raise RuntimeError("PDF input needs poppler's pdftoppm on PATH")
        out = work_dir / "page"
        subprocess.run(
            [
                "pdftoppm",
                "-r",
                str(dpi),
                "-f",
                str(page),
                "-l",
                str(page),
                "-png",
                str(path),
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        cands = sorted(work_dir.glob("page*.png"))
        if not cands:
            raise RuntimeError("pdftoppm produced no page image")
        img_path, source = cands[-1], "pdf"
    elif suffix == ".dxf":
        # rasterize only; no entity semantics are taken from the DXF in vision mode
        from cutplan_agent.reader.dxf_adapter import render
        from cutplan_agent.reader.dxf_reader import read_dxf

        ents, _ = read_dxf(path)
        img_path = render(
            [e for e in ents if e.kind != "other"],
            work_dir / "sheet_raster.png",
            width_in=24,
            dpi=dpi,
        )
        source = "dxf-raster"
    else:
        raise ValueError(f"Unsupported input {path.suffix}; use PNG/JPG/PDF or DXF")
    gray = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"Could not decode {img_path}")
    if (
        max(gray.shape) < min_side_px
    ):  # low-resolution scans: upscale so OCR and stroke analysis have pixels to work with
        f = min_side_px / max(gray.shape)
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        img_path = work_dir / "sheet_upscaled.png"
        cv2.imwrite(str(img_path), gray)
        source += "+upscaled"
    return SheetImage(img_path, gray.shape[1], gray.shape[0], gray, source, dpi)


def crop(
    sheet: SheetImage, box: PxBox, out: Path, pad: int = 8, max_side: int | None = None
) -> Path:
    import cv2

    x0, y0 = max(int(box[0]) - pad, 0), max(int(box[1]) - pad, 0)
    x1, y1 = min(int(box[2]) + pad, sheet.width), min(int(box[3]) + pad, sheet.height)
    img = sheet.gray[y0:y1, x0:x1]
    if max_side and max(img.shape) > max_side:
        f = max_side / max(img.shape)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    return out


def tiles(sheet: SheetImage, tile_px: int = 1400, overlap: float = 0.15) -> list[PxBox]:
    step = int(tile_px * (1 - overlap))
    xs = list(range(0, max(sheet.width - tile_px, 0) + 1, step)) or [0]
    ys = list(range(0, max(sheet.height - tile_px, 0) + 1, step)) or [0]
    if xs[-1] + tile_px < sheet.width:
        xs.append(sheet.width - tile_px)
    if ys[-1] + tile_px < sheet.height:
        ys.append(sheet.height - tile_px)
    return [
        (
            float(x),
            float(y),
            float(min(x + tile_px, sheet.width)),
            float(min(y + tile_px, sheet.height)),
        )
        for y in ys
        for x in xs
    ]


# ----------------------------------------------------------------------------- text classification
_DIM = re.compile(
    r"^\s*(?:(?P<cnt>\d+)\s*[-x×]\s*)?(?P<feat>[ØφΦ∅RrCt])?\s*(?P<val>\d+(?:[.,]\d+)?)\s*(?:±\s*\d+(?:\.\d+)?)?\s*(?:mm)?\s*$"
)
_CAPTION = re.compile(
    r"\bt\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)", re.I
)
_TITLE = re.compile(
    r"SCALE|DW'?G|DRAWING|MATERIAL|PART NAME|ISSUE|TOLERANCE|SHEET|WEIGHT|척도|도면|재질|품명",
    re.I,
)
_TABLE = re.compile(r"\bITEM\b|PART NO|\bQTY\b|REMARK|\bDATE\b|\bREV\b", re.I)


def classify_text(t: TextItem) -> TextItem:
    s = t.text.strip()
    if _CAPTION.search(s):
        t.kind = "caption"
        return t
    if _TITLE.search(s):
        t.kind = "title"
        return t
    if _TABLE.search(s):
        t.kind = "table"
        return t
    if s.upper().startswith("NOTE") or len(s) > 40:
        t.kind = "note"
        return t
    m = _DIM.match(s.replace(" ", ""))
    if m and m.group("val"):
        t.kind = "dimension"
        t.value = float(m.group("val").replace(",", "."))
        f = (m.group("feat") or "").upper()
        t.feature = {
            "Ø": "diameter",
            "Φ": "diameter",
            "∅": "diameter",
            "R": "radius",
            "C": "chamfer",
            "T": "thickness",
        }.get(f)
        t.count = int(m.group("cnt")) if m.group("cnt") else None
        return t
    t.kind = "label"
    return t


# ----------------------------------------------------------------------------- OCR: VLM or tesseract
_TEXT_STRUCTURE_PROMPT = (
    "This is a fragment of a mechanical engineering drawing. List EVERY piece of text you can read (dimension numbers, "
    "diameters like 2-Ø13, radii like R5, part names, notes, title-block fields). Fill text_extraction.items in the shared output contract. "
    "Each item has text (string), bbox [x0, y0, x1, y1] in pixel coordinates of THIS image (origin top-left), "
    "and kind (dimension, label, note, title, table, caption or other). "
    "Keep numbers exactly as printed; do not merge separate labels."
)


def ocr_vlm(
    sheet: SheetImage,
    ocr: VLMClient,
    work_dir: Path,
    *,
    tile_px: int = 1400,
    reason: VLMClient | None = None,
) -> list[TextItem]:
    items: list[TextItem] = []
    for i, box in enumerate(tiles(sheet, tile_px)):
        path = crop(sheet, box, work_dir / "tiles" / f"tile_{i:02d}.png", pad=0)
        dimensions = f"This tile is {box[2] - box[0]} pixels wide and {box[3] - box[1]} pixels high. "
        data = read_ocr_task(
            ocr,
            reason,
            [path],
            task="text_extraction",
            instructions=dimensions + _TEXT_STRUCTURE_PROMPT,
        )
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            continue
        for it in data["items"]:
            try:
                b = [float(v) for v in it["bbox"]]
                if len(b) != 4 or not str(it.get("text", "")).strip():
                    continue
                if not (
                    0 <= b[0] < b[2] <= box[2] - box[0]
                    and 0 <= b[1] < b[3] <= box[3] - box[1]
                ):
                    continue
                items.append(
                    TextItem(
                        str(it["text"]).strip(),
                        (b[0] + box[0], b[1] + box[1], b[2] + box[0], b[3] + box[1]),
                        str(it.get("kind", "other")),
                        0.8,
                        f"vlm_reason:{reason.config.model}+vlm_ocr:{ocr.config.model}",
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return dedupe(items)


def ocr_tesseract(
    sheet: SheetImage, work_dir: Path, *, upscale: float = 1.0
) -> list[TextItem]:
    """Deterministic fallback. Rotated (vertical) dimension text is read in a second pass on the rotated image."""
    import cv2

    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("tesseract fallback needs pytesseract") from exc
    items: list[TextItem] = []
    for rot in (0, 90):
        img = (
            sheet.gray if rot == 0 else cv2.rotate(sheet.gray, cv2.ROTATE_90_CLOCKWISE)
        )
        if upscale != 1.0:
            img = cv2.resize(
                img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC
            )
        data = pytesseract.image_to_data(
            img, config="--psm 11", output_type=pytesseract.Output.DICT
        )
        for j in range(len(data["text"])):
            txt, conf = str(data["text"][j]).strip(), float(data["conf"][j])
            if not txt or conf < 30:
                continue
            x, y, w, h = (
                data[k][j] / upscale for k in ("left", "top", "width", "height")
            )
            if (
                rot == 90
            ):  # map back: rotated 90 cw -> original x = y_r, original y = H - x_r
                x, y, w, h = y, sheet.height - (x + w), h, w
            items.append(
                TextItem(
                    txt,
                    (x, y, x + w, y + h),
                    "other",
                    conf / 100,
                    "tesseract" + ("" if rot == 0 else "_rot90"),
                )
            )
    return dedupe(merge_adjacent(items))


def merge_adjacent(items: list[TextItem], gap_ratio: float = 0.6) -> list[TextItem]:
    """Join tesseract words on the same line into phrases ('PART NAME', 'SPCC, 3.0t')."""
    items = sorted(items, key=lambda t: (t.source, round(t.bbox[1] / 4), t.bbox[0]))
    out: list[TextItem] = []
    for t in items:
        if out:
            p = out[-1]
            h = max(p.bbox[3] - p.bbox[1], 1)
            same_line = (
                abs(p.center[1] - t.center[1]) < 0.5 * h and p.source == t.source
            )
            if same_line and 0 <= t.bbox[0] - p.bbox[2] <= gap_ratio * h:
                p.text, p.bbox = (
                    p.text + " " + t.text,
                    (
                        p.bbox[0],
                        min(p.bbox[1], t.bbox[1]),
                        t.bbox[2],
                        max(p.bbox[3], t.bbox[3]),
                    ),
                )
                p.confidence = min(p.confidence, t.confidence)
                continue
        out.append(TextItem(t.text, t.bbox, t.kind, t.confidence, t.source))
    return out


def dedupe(items: list[TextItem], iou: float = 0.4) -> list[TextItem]:
    kept: list[TextItem] = []
    for t in sorted(items, key=lambda t: -t.confidence):
        if any(
            _iou(t.bbox, k.bbox) > iou
            and (t.text == k.text or t.text in k.text or k.text in t.text)
            for k in kept
        ):
            continue
        kept.append(t)
    return [classify_text(t) for t in kept]


def _iou(a: PxBox, b: PxBox) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def read_texts(
    sheet: SheetImage,
    ocr: VLMClient,
    work_dir: Path,
    *,
    reason: VLMClient | None = None,
) -> tuple[list[TextItem], str]:
    if ocr.enabled:
        items = ocr_vlm(sheet, ocr, work_dir, reason=reason)
        if items:
            return items, f"vlm_reason:{reason.config.model}+vlm_ocr:{ocr.config.model}"
    return ocr_tesseract(sheet, work_dir), "tesseract"


# ----------------------------------------------------------------------------- geometry (OpenCV)
def binarize(sheet: SheetImage) -> np.ndarray:
    import cv2

    blur = cv2.GaussianBlur(sheet.gray, (3, 3), 0)
    ink = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    return ink  # 255 = ink


def stroke_width(ink: np.ndarray) -> float:
    """Median stroke width in px from the distance transform (drives snapping and dedup tolerances)."""
    import cv2

    dt = cv2.distanceTransform((ink > 0).astype(np.uint8), cv2.DIST_L2, 3)
    vals = dt[(ink > 0) & (dt >= 0.5)]
    return float(2 * np.median(vals)) if vals.size else 2.0


def mask_texts(ink: np.ndarray, texts: list[TextItem], pad: int = 3) -> np.ndarray:
    out = ink.copy()
    for t in texts:
        x0, y0, x1, y1 = (int(round(v)) for v in t.bbox)
        out[max(y0 - pad, 0) : y1 + pad, max(x0 - pad, 0) : x1 + pad] = 0
    return out


def ink_ratio_along(ink: np.ndarray, p1, p2, halfwidth: int = 1) -> float:
    n = max(int(hypot(p2[0] - p1[0], p2[1] - p1[1])), 1)
    hits = 0
    for i in range(n + 1):
        x = int(round(p1[0] + (p2[0] - p1[0]) * i / n))
        y = int(round(p1[1] + (p2[1] - p1[1]) * i / n))
        y0, y1, x0, x1 = (
            max(y - halfwidth, 0),
            min(y + halfwidth + 1, ink.shape[0]),
            max(x - halfwidth, 0),
            min(x + halfwidth + 1, ink.shape[1]),
        )
        if ink[y0:y1, x0:x1].any():
            hits += 1
    return hits / (n + 1)


def _merge_collinear(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    dist_tol: float,
    angle_tol_deg: float = 2.0,
    gap_tol: float = 12.0,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out: list = []
    for p1, p2 in sorted(
        segs, key=lambda s: -hypot(s[1][0] - s[0][0], s[1][1] - s[0][1])
    ):
        ang = degrees(atan2(p2[1] - p1[1], p2[0] - p1[0])) % 180
        merged = False
        for i, (q1, q2) in enumerate(out):
            qang = degrees(atan2(q2[1] - q1[1], q2[0] - q1[0])) % 180
            if min(abs(ang - qang), 180 - abs(ang - qang)) > angle_tol_deg:
                continue
            # perpendicular distance of p1 from line q
            ux, uy = (q2[0] - q1[0]), (q2[1] - q1[1])
            L = hypot(ux, uy) or 1
            d = abs((p1[0] - q1[0]) * uy - (p1[1] - q1[1]) * ux) / L
            if d > dist_tol:
                continue
            # projections overlap or nearly touch?
            t = sorted(
                [
                    ((p[0] - q1[0]) * ux + (p[1] - q1[1]) * uy) / L
                    for p in (p1, p2, q1, q2)
                ]
            )
            span = [((p[0] - q1[0]) * ux + (p[1] - q1[1]) * uy) / L for p in (p1, p2)]
            if min(span) > L + gap_tol or max(span) < -gap_tol:
                continue
            a, b = t[0], t[-1]
            out[i] = (
                (q1[0] + ux / L * a, q1[1] + uy / L * a),
                (q1[0] + ux / L * b, q1[1] + uy / L * b),
            )
            merged = True
            break
        if not merged:
            out.append((p1, p2))
    return out


def axis_runs(
    ink: np.ndarray, min_len: int, stroke: float
) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
    """Axis-aligned segments from raw ink runs: (p1, p2, ink_ratio).

    Dashes are joined by merging runs on the SAME line whose gap is small (<= 4 strokes); no pixel
    bridging is done, so two close parallel lines never fabricate a run between them. Adjacent
    parallel runs (the width of one stroke) are merged into a single segment."""
    gap_tol = max(6, int(4 * stroke))
    out = []
    for axis in (
        0,
        1,
    ):  # 0: runs along columns (vertical lines), 1: along rows (horizontal lines)
        arr = (ink if axis == 0 else ink.T) > 0
        L, N = arr.shape
        runs: list[
            tuple[int, int, int, int]
        ] = []  # (line index, start, end, inked length)
        for n in range(N):
            c = arr[:, n]
            if not c.any():
                continue
            d = np.diff(np.concatenate([[0], c.astype(np.int8), [0]]))
            starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
            cur = None
            for a, b in zip(starts, ends):
                if b - a < max(
                    4, int(2 * stroke)
                ):  # a stroke cross-section or a speck: never a dash piece
                    if cur and cur[1] - cur[0] >= min_len:
                        runs.append((n, cur[0], cur[1], cur[2]))
                    cur = None
                    continue
                if cur and a - cur[1] <= gap_tol:
                    cur = (cur[0], int(b), cur[2] + int(b - a))
                else:
                    if cur and cur[1] - cur[0] >= min_len:
                        runs.append((n, cur[0], cur[1], cur[2]))
                    cur = (int(a), int(b), int(b - a))
            if cur and cur[1] - cur[0] >= min_len:
                runs.append((n, cur[0], cur[1], cur[2]))
        runs.sort()
        groups: list[list[tuple[int, int, int, int]]] = []
        for r in runs:
            for g in groups:
                last = g[-1]
                if r[0] - last[0] <= 1 and min(r[2], last[2]) - max(
                    r[1], last[1]
                ) > 0.8 * min(r[2] - r[1], last[2] - last[1]):
                    g.append(r)
                    break
            else:
                groups.append([r])
        for g in groups:
            if (
                len(g) > 2.5 * stroke + 1
            ):  # wider than a stroke: a band between two close lines, not a line
                continue
            n = sum(r[0] for r in g) / len(g)
            a = min(r[1] for r in g)
            b = max(r[2] for r in g)
            ratio = max(r[3] for r in g) / max(b - a, 1)
            if (
                ratio < 0.45
            ):  # dashed lines sit around 0.6-0.8; lower is two separate features
                continue
            if axis == 0:
                out.append(((n, float(a)), (n, float(b)), float(ratio)))
            else:
                out.append(((float(a), n), (float(b), n), float(ratio)))
    return out


def extract_geometry(
    sheet: SheetImage,
    region: PxBox,
    texts: list[TextItem],
    *,
    min_len_px: int = 8,
    mask: np.ndarray | None = None,
) -> list[PxPrimitive]:
    """Axis-aligned lines from ink runs, diagonals from Hough, circles from Hough; dashed runs become hidden lines."""
    import cv2

    ink_full = mask_texts(binarize(sheet), texts)
    stroke = stroke_width(ink_full)
    if mask is not None:
        ink_full = np.where(mask, ink_full, 0).astype(np.uint8)
    pad = int(2 * stroke) + 2
    x0, y0 = max(int(round(region[0])) - pad, 0), max(int(round(region[1])) - pad, 0)
    x1, y1 = (
        min(int(round(region[2])) + pad, sheet.width),
        min(int(round(region[3])) + pad, sheet.height),
    )
    ink = ink_full[y0:y1, x0:x1]
    prims: list[PxPrimitive] = []
    axis_segs = axis_runs(ink, max(min_len_px, int(2 * stroke)), stroke)
    for p1, p2, ratio in axis_segs:
        if ratio < 0.3:
            continue
        prims.append(
            PxPrimitive(
                "line",
                [(p1[0] + x0, p1[1] + y0), (p2[0] + x0, p2[1] + y0)],
                line_type="visible" if ratio > 0.85 else "hidden",
                ink_ratio=round(ratio, 2),
            )
        )
    # diagonals: erase axis-aligned ink first so Hough only sees what the run scan could not
    residual = ink.copy()
    for p1, p2, _ in axis_segs:
        cv2.line(
            residual,
            (int(p1[0]), int(p1[1])),
            (int(p2[0]), int(p2[1])),
            0,
            int(stroke) + 3,
        )
    lines = cv2.HoughLinesP(
        residual,
        1,
        np.pi / 360,
        threshold=max(10, min_len_px),
        minLineLength=max(12, 2 * min_len_px),
        maxLineGap=int(3 * stroke),
    )
    rows = np.asarray(lines).reshape(-1, 4) if lines is not None else np.zeros((0, 4))
    segs = [
        ((float(a), float(b)), (float(c), float(d)))
        for a, b, c, d in rows
        if abs(a - c) > 3 and abs(b - d) > 3
    ]
    for p1, p2 in _merge_collinear(
        segs, dist_tol=max(2.0, stroke), gap_tol=max(12.0, 4 * stroke)
    ):
        ratio = ink_ratio_along(ink, p1, p2)
        if ratio < 0.3:
            continue
        prims.append(
            PxPrimitive(
                "line",
                [(p1[0] + x0, p1[1] + y0), (p2[0] + x0, p2[1] + y0)],
                line_type="visible" if ratio > 0.85 else "hidden",
                ink_ratio=round(ratio, 2),
            )
        )
    circles = cv2.HoughCircles(
        cv2.GaussianBlur(sheet.gray[y0:y1, x0:x1], (5, 5), 1),
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=8,
        param1=120,
        param2=28,
        minRadius=4,
        maxRadius=max(8, min(y1 - y0, x1 - x0) // 3),
    )
    for cx, cy, r in np.asarray(circles).reshape(-1, 3) if circles is not None else []:
        pts = [
            (cx + r * cos(a), cy + r * sin(a))
            for a in np.linspace(0, 2 * np.pi, 36, endpoint=False)
        ]
        inked = sum(
            1
            for px, py in pts
            if 0 <= int(py) < ink.shape[0]
            and 0 <= int(px) < ink.shape[1]
            and ink[
                max(int(py) - 1, 0) : int(py) + 2, max(int(px) - 1, 0) : int(px) + 2
            ].any()
        )
        if inked / len(pts) >= 0.7:
            prims.append(
                PxPrimitive(
                    "circle", center=(float(cx) + x0, float(cy) + y0), radius=float(r)
                )
            )
    return prims


def snap(prims: list[PxPrimitive], tol: float) -> list[PxPrimitive]:
    """Cluster x and y coordinates so rectangles close and shared edges meet exactly."""

    def cluster(vals: list[float]) -> dict[float, float]:
        vals = sorted(vals)
        groups: list[list[float]] = []
        for v in vals:
            if groups and v - groups[-1][-1] <= tol:
                groups[-1].append(v)
            else:
                groups.append([v])
        return {v: sum(g) / len(g) for g in groups for v in g}

    xs = [p[0] for pr in prims for p in pr.points] + [
        pr.center[0] for pr in prims if pr.center
    ]
    ys = [p[1] for pr in prims for p in pr.points] + [
        pr.center[1] for pr in prims if pr.center
    ]
    mx, my = cluster(xs), cluster(ys)
    for pr in prims:
        pr.points = [(mx[p[0]], my[p[1]]) for p in pr.points]
        if pr.center:
            pr.center = (mx[pr.center[0]], my[pr.center[1]])
    # after snapping, duplicated strokes (one Hough line per stroke edge) coincide: merge them
    out: list[PxPrimitive] = []
    by_type: dict[str, list] = {}
    for pr in prims:
        if pr.kind != "line":
            out.append(pr)
            continue
        by_type.setdefault(pr.line_type, []).append((pr.points[0], pr.points[1]))
    for lt, segs in by_type.items():
        for p1, p2 in _merge_collinear(segs, dist_tol=tol, gap_tol=tol):
            if hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 2:
                out.append(PxPrimitive("line", [p1, p2], line_type=lt))
    return out


def _max_run(v: np.ndarray) -> int:
    d = np.diff(np.concatenate([[0], (v > 0).astype(np.int8), [0]]))
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    return int((ends - starts).max()) if len(starts) else 0


def find_frame(
    ink: np.ndarray, min_run: float = 0.6, density: float = 0.3
) -> tuple[PxBox | None, np.ndarray]:
    """Frame / border rules: rows and columns holding ONE continuous run >= min_run of the sheet (skew tolerant).
    Density alone is not enough: two aligned thin views can fill a row without being a rule."""
    import cv2

    H, W = ink.shape
    # a skewed rule drifts a few px across the sheet: dilate perpendicular to the rule so its run stays continuous
    dil_r = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 27)))
    dil_c = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (27, 5)))

    def is_rule(line: np.ndarray, L: int) -> bool:
        dens = line.sum() / 255.0 / L
        run = _max_run(line)
        return dens > density and (
            run >= min_run * L or (dens >= 0.8 and run >= 0.4 * L)
        )  # text masks may cut a rule

    rows = [r for r in range(H) if is_rule(dil_r[r, :], W)]
    cols = [c for c in range(W) if is_rule(dil_c[:, c], H)]
    out = ink.copy()
    for r in rows:
        out[max(r - 4, 0) : r + 5, :] = 0
    for c in cols:
        out[:, max(c - 4, 0) : c + 5] = 0
    if not rows and not cols:
        return None, out
    # a rule found only near one edge does not define the opposite edge: fall back to the sheet edge there
    top = float(min(rows)) if rows and min(rows) < 0.5 * H else 0.0
    bottom = float(max(rows)) if rows and max(rows) > 0.5 * H else float(H - 1)
    left = float(min(cols)) if cols and min(cols) < 0.5 * W else 0.0
    right = float(max(cols)) if cols and max(cols) > 0.5 * W else float(W - 1)
    return (left, top, right, bottom), out


def mask_dimension_texts(
    ink: np.ndarray, texts: list[TextItem], factor: float = 3.0
) -> np.ndarray:
    """Blank dimension texts extended along their reading direction so the dimension line beside them is cut too."""
    out = ink.copy()
    for t in texts:
        if t.kind != "dimension":
            continue
        x0, y0, x1, y1 = (int(round(v)) for v in t.bbox)
        h, w = y1 - y0, x1 - x0
        vertical = h > w or t.source.endswith("rot90")
        if vertical:
            ex = int(factor * w)
            out[max(y0 - ex, 0) : y1 + ex, max(x0 - 2, 0) : x1 + 2] = 0
        else:
            ex = int(factor * h)
            out[max(y0 - 2, 0) : y1 + 2, max(x0 - ex, 0) : x1 + ex] = 0
    return out


def corner_regions(
    texts: list[TextItem], frame: PxBox | None, W: int, H: int
) -> list[PxBox]:
    """Title block, BOM and revision tables: clusters of title/table keywords, extended to the frame edges they sit against."""
    keys = [t for t in texts if t.kind in {"title", "table"}]
    if not keys:
        return []
    reach = 0.08 * hypot(W, H)
    groups: list[list[TextItem]] = []
    for t in keys:
        for g in groups:
            if any(
                hypot(t.center[0] - u.center[0], t.center[1] - u.center[1]) < reach
                for u in g
            ):
                g.append(t)
                break
        else:
            groups.append([t])
    fx0, fy0, fx1, fy1 = frame if frame else (0.0, 0.0, float(W), float(H))
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        x0 = min(t.bbox[0] for t in g)
        y0 = min(t.bbox[1] for t in g)
        x1 = max(t.bbox[2] for t in g)
        y1 = max(t.bbox[3] for t in g)
        pad = 0.015 * hypot(W, H)
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        if fx1 - x1 < 0.25 * W:
            x1 = fx1  # hugs the right edge  -> extend to it
        if y1 > fy1 - 0.25 * H:
            y1 = fy1  # hugs the bottom edge
        if y0 < fy0 + 0.12 * H:
            y0 = fy0  # revision block at the top
        if x0 < fx0 + 0.12 * W:
            x0 = fx0
        out.append((x0, y0, x1, y1))
    return out


def _has_loop(mask: np.ndarray, min_area: float) -> bool:
    """A view outline encloses background; a dimension/leader assembly is a tree. Hole area must be meaningful."""
    import cv2

    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return False
    for i, h in enumerate(hier[0]):
        if (
            h[3] != -1 and cv2.contourArea(contours[i]) >= min_area
        ):  # has a parent -> it is a hole
            return True
    return False


def find_regions(
    sheet: SheetImage,
    texts: list[TextItem],
    *,
    gap_ratio: float = 0.003,
    min_side_ratio: float = 0.015,
    exclude: list[PxBox] | None = None,
) -> tuple[list[PxBox], dict]:
    """View candidates.

    1. ink minus texts, frame rules, corner tables, excluded boxes
    2. connected components after a SMALL dilation (joins broken strokes, not neighbouring views)
    3. a component is a view when it encloses a hole (closed outline); the rest are annotation
       assemblies (dimension lines, leaders) and are attached to the single nearest view
    """
    import cv2

    ink = mask_dimension_texts(mask_texts(binarize(sheet), texts), texts)
    H, W = ink.shape
    frame_bbox, ink = find_frame(ink)
    corners = corner_regions(texts, frame_bbox, W, H)
    for b in list(exclude or []) + corners:
        x0, y0, x1, y1 = (int(round(v)) for v in b)
        ink[max(y0, 0) : max(y1, 0), max(x0, 0) : max(x1, 0)] = 0
    gap = max(3, int(gap_ratio * hypot(W, H)))
    blob = cv2.dilate(
        ink, cv2.getStructuringElement(cv2.MORPH_RECT, (2 * gap + 1, 2 * gap + 1))
    )
    n, labels, stats, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
    inset = (
        (
            frame_bbox[0] + 0.012 * W,
            frame_bbox[1] + 0.012 * H,
            frame_bbox[2] - 0.012 * W,
            frame_bbox[3] - 0.012 * H,
        )
        if frame_bbox
        else (0, 0, W, H)
    )
    min_hole = (min_side_ratio * min(W, H)) ** 2 * 0.25
    views: list[PxBox] = []
    view_ids: list[int] = []
    annots: list[PxBox] = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        comp = (
            (labels[y : y + h, x : x + w] == i) & (ink[y : y + h, x : x + w] > 0)
        ).astype(np.uint8) * 255
        ys, xs = np.where(comp > 0)
        if not len(xs):
            continue
        box = (
            float(x + xs.min()),
            float(y + ys.min()),
            float(x + xs.max() + 1),
            float(y + ys.max() + 1),
        )
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if not (inset[0] <= cx <= inset[2] and inset[1] <= cy <= inset[3]):
            continue
        big = (box[2] - box[0]) >= min_side_ratio * W or (
            box[3] - box[1]
        ) >= min_side_ratio * H
        k = (
            2 * min(gap, 2) + 1
        )  # seal small scan breaks only; a thin view's interior must survive
        closed = cv2.morphologyEx(
            comp, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        )
        if big and _has_loop(closed, min_hole):
            views.append(box)
            view_ids.append(i)
        elif big or len(xs) > 40:
            annots.append(box)
    # nested view boxes (a hole outline inside an outline) collapse into the outer one
    order = sorted(
        range(len(views)),
        key=lambda k: -(views[k][2] - views[k][0]) * (views[k][3] - views[k][1]),
    )
    merged: list[PxBox] = []
    merged_ids: list[list[int]] = []
    for k in order:
        b = views[k]
        for i, m in enumerate(merged):
            if _iou(b, m) > 0.05 or (
                m[0] <= b[0] and m[1] <= b[1] and m[2] >= b[2] and m[3] >= b[3]
            ):
                merged[i] = (
                    min(m[0], b[0]),
                    min(m[1], b[1]),
                    max(m[2], b[2]),
                    max(m[3], b[3]),
                )
                merged_ids[i].append(view_ids[k])
                break
        else:
            merged.append(b)
            merged_ids.append([view_ids[k]])
    # annotations join exactly one nearest view (never bridge two)
    reach = 0.04 * hypot(W, H)
    attached = 0
    final = list(merged)
    for a in annots:
        best, bd = None, None
        for i, v in enumerate(final):
            dx = max(v[0] - a[2], a[0] - v[2], 0)
            dy = max(v[1] - a[3], a[1] - v[3], 0)
            d = hypot(dx, dy)
            if bd is None or d < bd:
                best, bd = i, d
        if best is not None and bd is not None and bd <= reach:
            v = final[best]
            final[best] = (
                min(v[0], a[0]),
                min(v[1], a[1]),
                max(v[2], a[2]),
                max(v[3], a[3]),
            )
            attached += 1
    pairs = sorted(
        zip(final, merged_ids), key=lambda t: -(t[0][2] - t[0][0]) * (t[0][3] - t[0][1])
    )
    final = [b for b, _ in pairs]
    # outline-only masks: pixels of the loop-bearing components (dimension/leader assemblies are left out)
    masks = [np.isin(labels, ids) & (ink > 0) for _, ids in pairs]
    return final, {
        "gap_px": gap,
        "frame_bbox": frame_bbox,
        "components": n - 1,
        "view_components": len(views),
        "annotation_components": len(annots),
        "attached": attached,
        "corner_regions": corners,
        "masks": masks,
    }


def save_debug(
    sheet: SheetImage,
    out: Path,
    boxes: list[tuple[PxBox, str]] | None = None,
    texts: list[TextItem] | None = None,
    prims: list[PxPrimitive] | None = None,
) -> Path:
    import cv2

    img = cv2.cvtColor(sheet.gray, cv2.COLOR_GRAY2BGR)
    for t in texts or []:
        c = {
            "dimension": (0, 160, 0),
            "title": (200, 0, 200),
            "table": (0, 120, 200),
            "caption": (0, 100, 255),
        }.get(t.kind, (120, 120, 120))
        cv2.rectangle(
            img,
            (int(t.bbox[0]), int(t.bbox[1])),
            (int(t.bbox[2]), int(t.bbox[3])),
            c,
            1,
        )
    for p in prims or []:
        col = (255, 0, 0) if p.line_type == "visible" else (0, 0, 255)
        if p.kind == "line":
            cv2.line(
                img,
                tuple(int(v) for v in p.points[0]),
                tuple(int(v) for v in p.points[1]),
                col,
                2,
            )
        elif p.kind == "circle":
            cv2.circle(
                img, tuple(int(v) for v in p.center), int(p.radius), (0, 180, 255), 2
            )
    for b, label in boxes or []:
        cv2.rectangle(
            img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (48, 90, 216), 3
        )
        cv2.putText(
            img,
            label,
            (int(b[0]) + 4, int(b[1]) + 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (48, 90, 216),
            2,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    return out
