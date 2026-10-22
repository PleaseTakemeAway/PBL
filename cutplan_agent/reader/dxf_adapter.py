"""Adapter: raw DXF sheet -> structured DrawingDocument.

Pipeline (each stage records provenance and degrades to a deterministic fallback):
  1. read every entity, layer-agnostic (dxf_reader)          deterministic
  2. title block: regex over TEXT, gaps filled by raw OCR + reasoning JSON
  3. view candidates: spatial clustering of part geometry   deterministic
  4. view labels / projection / part class: reasoning VLM, validated,
     with a relative-position fallback
  5. convert to the front/top/right contract (arcs tessellated,
     left/bottom/back views mirrored), dimensions attached as annotations
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from math import acos, ceil, hypot
from pathlib import Path
from typing import Any

from cutplan_agent.reader.dxf_reader import RawEntity, arc_points, read_dxf
from cutplan_agent.reader.knowledge import STAGE_TOPICS
from cutplan_agent.reader.vlm import (
    VLMClient,
    final_part_class,
    read_ocr_task,
    softmax_class_scores,
)
from cutplan_agent.reconstruct.models import DrawingDocument

BBox = tuple[float, float, float, float]
TITLE_KEYS = (
    "SCALE",
    "DW'G",
    "DWG",
    "DRAWING NO",
    "MATERIAL",
    "PART NAME",
    "ISSUE",
    "TOLERANCE",
    "SHEET",
    "WEIGHT",
    "척도",
    "도면번호",
    "재질",
    "품명",
)
TABLE_KEYS = ("ITEM", "PART NO", "QTY", "REMARK", "DATE", "ISSUE", "NOTE", "REV")
DIM_LAYER_HINT = re.compile(
    r"DIM|TEXT|TXT|TITLE|FRAME|BORDER|NOTE|HATCH|CENTER|AXIS", re.I
)


# ----------------------------------------------------------------------------- helpers
def _union(a: BBox | None, b: BBox | None) -> BBox | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _expand(b: BBox, d: float) -> BBox:
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def _inter(a: BBox, b: BBox) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _contains(b: BBox, p: tuple[float, float]) -> bool:
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def _area(b: BBox) -> float:
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def join(self, a, b):
        self.p[self.find(a)] = self.find(b)


# ----------------------------------------------------------------------------- rendering
def render(
    entities: list[RawEntity],
    out: Path,
    bbox: BBox | None = None,
    boxes: list[tuple[BBox, str]] | None = None,
    width_in: float = 16.0,
    dpi: int = 120,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Arc as MArc
    from matplotlib.patches import Rectangle

    if bbox is None:
        bbox = None
        for e in entities:
            bbox = _union(bbox, e.bbox())
        if bbox is None:
            bbox = (0, 0, 1, 1)
        bbox = _expand(bbox, 0.02 * max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
    w, h = max(bbox[2] - bbox[0], 1e-6), max(bbox[3] - bbox[1], 1e-6)
    fig = plt.figure(figsize=(width_in, width_in * h / w), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    ax.set_aspect("equal")
    ax.axis("off")
    pt_per_unit = width_in * 72 / w
    for e in entities:
        eb = e.bbox()
        if eb is None or not _inter(eb, bbox):
            continue
        col = "k" if e.kind in {"line", "arc", "circle"} else "#555"
        lw = 0.9 if e.kind in {"line", "arc", "circle"} else 0.4
        if e.kind in {"line", "dimension_geom"} and len(e.points) == 2:
            ax.plot(
                [e.points[0][0], e.points[1][0]],
                [e.points[0][1], e.points[1][1]],
                color=col,
                lw=lw,
            )
        elif e.kind == "circle":
            ax.add_patch(MArc(e.center, 2 * e.radius, 2 * e.radius, lw=lw, color=col))
        elif e.kind in {"arc", "dimension_geom"} and e.center is not None:
            a1, a2 = e.start_angle, e.end_angle
            if a2 < a1:
                a2 += 360
            ax.add_patch(
                MArc(
                    e.center,
                    2 * e.radius,
                    2 * e.radius,
                    theta1=a1,
                    theta2=a2,
                    lw=lw,
                    color=col,
                )
            )
        elif e.kind in {"text", "dimension"} and e.center is not None and e.text:
            ax.text(
                e.center[0],
                e.center[1],
                e.text,
                fontsize=max((e.height or 2.5) / 0.72 * pt_per_unit, 2),
                color=col,
                rotation=e.attributes.get("rotation", 0),
                va="bottom",
                ha="left",
            )
    for b, label in boxes or []:
        ax.add_patch(
            Rectangle(
                (b[0], b[1]), b[2] - b[0], b[3] - b[1], fill=False, ec="#D85A30", lw=2
            )
        )
        ax.text(
            b[0],
            b[3],
            f" {label}",
            color="#D85A30",
            fontsize=16,
            fontweight="bold",
            va="bottom",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#D85A30"),
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, facecolor="white")
    plt.close(fig)
    return out


# ----------------------------------------------------------------------------- title block
_SCALE_RE = re.compile(
    r"SCALE\s*[:=]?\s*(\d+(?:\.\d+)?)\s*[/:]\s*(\d+(?:\.\d+)?)", re.I
)
_SCALE_LONE_RE = re.compile(r"^\s*(\d+)\s*[/:]\s*(\d+)\s*$")
_THICK_RE = re.compile(r"(?:,|\s)\s*(\d+(?:\.\d+)?)\s*t\b", re.I)
_THICK_RE2 = re.compile(r"\bt\s*(\d+(?:\.\d+)?)\b", re.I)
_DWG_RE = re.compile(r"\b([A-Z0-9]{2,6}-[A-Z0-9]{3,8})\b")
_MATERIAL_HINT = re.compile(
    r"\b(SPCC|SPHC|SS400|SS41|SA\d{3}|SUS\d{3}|A\d{3}|AL\d{4}|S\d{2}C|STKM|SM\d{3})",
    re.I,
)


@dataclass
class TitleBlock:
    drawing_no: str | None = None
    part_name: str | None = None
    material: str | None = None
    thickness_mm: float | None = None
    scale: float | None = None  # paper/real, 1:4 -> 0.25
    scale_text: str | None = None
    units: str | None = None
    projection: str | None = None  # first | third
    weight_kg: float | None = None
    sources: dict[str, str] = field(default_factory=dict)
    region: BBox | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _texts_in(entities, box: BBox | None):
    return [
        e
        for e in entities
        if e.kind == "text"
        and e.center is not None
        and (box is None or _contains(box, e.center))
    ]


def parse_title_block(
    entities: list[RawEntity],
    region: BBox | None,
    ocr: VLMClient,
    work_dir: Path | None,
    reason: VLMClient | None = None,
) -> TitleBlock:
    tb = TitleBlock(region=region)
    texts = _texts_in(entities, region) if region else _texts_in(entities, None)
    joined = "\n".join(t.text for t in texts if t.text)
    m = _SCALE_RE.search(joined)
    if not m:  # "SCALE" and "1/4" may be separate TEXT entities: take the lone ratio nearest a SCALE label
        label = next((t for t in texts if t.text and "SCALE" in t.text.upper()), None)
        if label:
            cands = [t for t in texts if t.text and _SCALE_LONE_RE.match(t.text)]
            if cands:
                t = min(
                    cands,
                    key=lambda t: hypot(
                        t.center[0] - label.center[0], t.center[1] - label.center[1]
                    ),
                )
                m = _SCALE_LONE_RE.match(t.text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a > 0 and b > 0:
            tb.scale, tb.scale_text, tb.sources["scale"] = (
                a / b,
                f"{m.group(1)}/{m.group(2)}",
                "regex",
            )
    mat = next(
        (t.text for t in texts if t.text and _MATERIAL_HINT.search(t.text)), None
    )
    if mat:
        tb.material, tb.sources["material"] = (
            mat.replace("MATERIAL", "").strip(" :"),
            "regex",
        )
        tm = _THICK_RE.search(mat) or _THICK_RE2.search(mat)
        if tm:
            tb.thickness_mm, tb.sources["thickness_mm"] = float(tm.group(1)), "regex"
    for t in texts:
        if (
            t.text
            and _DWG_RE.fullmatch(t.text.strip())
            and (t.height or 0) >= max((x.height or 0) for x in texts) * 0.6
        ):
            tb.drawing_no, tb.sources["drawing_no"] = t.text.strip(), "regex"
            break
    if re.search(r"\bDIM\b.*\bmm\b|\bmm\b", joined, re.I):
        tb.units, tb.sources["units"] = "mm", "regex"
    elif re.search(r"\binch|\bin\.\b", joined, re.I):
        tb.units, tb.sources["units"] = "inch", "regex"
    # OCR transcribes; the reasoning model structures missing fields and symbols.
    missing = [
        k
        for k in (
            "drawing_no",
            "part_name",
            "material",
            "thickness_mm",
            "scale",
            "units",
            "projection",
        )
        if getattr(tb, k) is None
    ]
    if missing and ocr.enabled and work_dir is not None:
        crop = render(
            [e for e in entities if e.kind != "other"],
            work_dir / "title_block.png",
            bbox=region,
            width_in=10,
        )
        prompt = (
            "This image is the title block of a mechanical engineering drawing. Read these title_block fields: "
            'drawing_no, part_name, material, thickness_mm (number), scale (string like "1/4"), units ("mm" or "inch"), '
            'projection ("first" or "third", from the projection symbol: a cone with the small circle on the LEFT of the truncated cone means third-angle), '
            "weight_kg (number). Use null when a value is not visible. Do not guess."
        )
        data = read_ocr_task(
            ocr, reason, [crop], task="title_block", instructions=prompt
        )
        if isinstance(data, dict):
            for k in missing:
                v = data.get(k)
                if v in (None, "", "null"):
                    continue
                if k == "scale":
                    sm = _SCALE_LONE_RE.match(str(v)) or re.match(
                        r"^\s*(\d+(?:\.\d+)?)\s*[/:]\s*(\d+(?:\.\d+)?)\s*$", str(v)
                    )
                    if sm:
                        tb.scale, tb.scale_text = (
                            float(sm.group(1)) / float(sm.group(2)),
                            str(v).strip(),
                        )
                elif k == "thickness_mm":
                    try:
                        tb.thickness_mm = float(v)
                    except (TypeError, ValueError):
                        continue
                elif k == "projection":
                    if str(v).lower() in {"first", "third"}:
                        tb.projection = str(v).lower()
                    else:
                        continue
                elif k == "units":
                    if str(v).lower() in {"mm", "inch"}:
                        tb.units = str(v).lower()
                    else:
                        continue
                else:
                    setattr(tb, k, str(v).strip())
                tb.sources[k] = (
                    f"vlm_reason:{reason.config.model}+vlm_ocr:{ocr.config.model}"
                )
            if isinstance(data.get("weight_kg"), (int, float)):
                tb.weight_kg = float(data["weight_kg"])
                tb.sources["weight_kg"] = (
                    f"vlm_reason:{reason.config.model}+vlm_ocr:{ocr.config.model}"
                )
    return tb


# ----------------------------------------------------------------------------- frames / regions / sheet type
_NEST_CAPTION = re.compile(
    r"\bt\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:-\s*(\d+)\s*(?:SH'?T|SHEET|EA|PCS?))?",
    re.I,
)
_NEST_WORDS = re.compile(r"SH'T|SHEET|NESTING|CUTTING\s*PLAN|\bCP-\d|NEST", re.I)


def detect_frames(
    entities: list[RawEntity],
    sheet: BBox,
    min_area_ratio: float = 0.2,
    tol_ratio: float = 0.002,
) -> tuple[list[BBox], set[str]]:
    """Axis-aligned rectangles built from long lines that cover >= min_area_ratio of the sheet: drawing borders, sheet frames."""
    W, H = sheet[2] - sheet[0], sheet[3] - sheet[1]
    tol = tol_ratio * hypot(W, H)
    horiz, vert = [], []
    for e in entities:
        if e.kind != "line" or len(e.points) != 2:
            continue
        (x1, y1), (x2, y2) = e.points
        if abs(y1 - y2) <= tol and abs(x1 - x2) >= 0.15 * W:
            horiz.append((min(x1, x2), max(x1, x2), (y1 + y2) / 2, e.handle))
        elif abs(x1 - x2) <= tol and abs(y1 - y2) >= 0.15 * H:
            vert.append((min(y1, y2), max(y1, y2), (x1 + x2) / 2, e.handle))
    frames, used = [], set()
    for i, top in enumerate(horiz):
        for bot in horiz[i + 1 :]:
            if (
                abs(top[0] - bot[0]) > tol
                or abs(top[1] - bot[1]) > tol
                or abs(top[2] - bot[2]) < 0.1 * H
            ):
                continue
            x0, x1 = top[0], top[1]
            y0, y1 = min(top[2], bot[2]), max(top[2], bot[2])
            left = [
                v
                for v in vert
                if abs(v[2] - x0) <= tol and v[0] <= y0 + tol and v[1] >= y1 - tol
            ]
            right = [
                v
                for v in vert
                if abs(v[2] - x1) <= tol and v[0] <= y0 + tol and v[1] >= y1 - tol
            ]
            if left and right and (x1 - x0) * (y1 - y0) >= min_area_ratio * W * H:
                frames.append((x0, y0, x1, y1))
                used |= {top[3], bot[3], left[0][3], right[0][3]}
    return frames, used


def find_title_regions(entities: list[RawEntity], sheet: BBox) -> list[BBox]:
    """One region per title block: title-keyword texts clustered by proximity (multi-sheet files have several)."""
    hits = [
        e
        for e in entities
        if e.kind == "text" and e.text and any(k in e.text.upper() for k in TITLE_KEYS)
    ]
    if not hits:
        return []
    diag = hypot(sheet[2] - sheet[0], sheet[3] - sheet[1])
    pad = 0.02 * diag
    boxes = [_expand(e.bbox(), 0.06 * diag) for e in hits]
    uf = _UF(len(hits))
    for i in range(len(hits)):
        for j in range(i + 1, len(hits)):
            if _inter(boxes[i], boxes[j]):
                uf.join(i, j)
    groups: dict[int, BBox | None] = {}
    for i, e in enumerate(hits):
        groups[uf.find(i)] = _union(groups.get(uf.find(i)), e.bbox())
    return [_expand(b, pad) for b in groups.values() if b]


def find_title_region(entities: list[RawEntity], sheet: BBox) -> BBox | None:
    regions = find_title_regions(entities, sheet)
    if not regions:
        return None
    # the block with the most keyword hits is the one to parse
    return max(
        regions,
        key=lambda r: sum(
            1
            for e in _texts_in(entities, r)
            if e.text and any(k in e.text.upper() for k in TITLE_KEYS)
        ),
    )


def classify_sheet(
    entities: list[RawEntity], views: "list[ViewCandidate]"
) -> tuple[str, dict]:
    """orthographic | nesting | unknown, decided from caption patterns and view-alignment structure."""
    texts = [e.text for e in entities if e.kind == "text" and e.text]
    captions = [t for t in texts if _NEST_CAPTION.search(t)]
    words = [t for t in texts if _NEST_WORDS.search(t)]
    aligned = 0
    if views:
        best = max(views, key=lambda v: len(_relations(v, views)))
        aligned = len(
            {
                "v" if r in ("above", "below") else "h"
                for r in _relations(best, views).values()
            }
        )
    ev = {
        "plate_captions": len(captions),
        "nesting_words": len(words),
        "clusters": len(views),
        "aligned_axes_at_best_front": aligned,
    }
    if len(captions) >= 2 or (captions and words):
        return "nesting", ev
    if views and aligned >= 1 and len(views) <= 8 and not captions:
        return "orthographic", ev
    return "unknown", ev


# ----------------------------------------------------------------------------- view candidates
@dataclass
class ViewCandidate:
    id: int
    bbox: BBox
    entities: list[RawEntity]
    dimensions: list[RawEntity] = field(default_factory=list)
    texts: list[RawEntity] = field(default_factory=list)
    label: str = "unlabeled"
    confidence: float = 0.0
    label_source: str = "none"
    reason: str = ""

    def counts(self) -> dict:
        c = {"line": 0, "arc": 0, "circle": 0}
        for e in self.entities:
            c[e.kind] = c.get(e.kind, 0) + 1
        c["dimensions"] = len(self.dimensions)
        return c


def _sheet_bbox(entities) -> BBox:
    b = None
    for e in entities:
        b = _union(b, e.bbox())
    return b or (0, 0, 1, 1)


def segment_views(
    entities: list[RawEntity],
    excluded: list[BBox],
    gap_ratio: float = 0.008,
    frame_handles: set[str] | None = None,
    frames: list[BBox] | None = None,
) -> tuple[list[ViewCandidate], dict]:
    sheet = _sheet_bbox(entities)
    frame_handles = frame_handles or set()
    frames = frames or []
    diag = hypot(sheet[2] - sheet[0], sheet[3] - sheet[1])

    def frame_of(b: BBox) -> BBox:
        c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        inside = [f for f in frames if _contains(f, c)]
        return min(inside, key=_area) if inside else sheet

    def gap_for(b: BBox) -> float:
        f = frame_of(b)
        return gap_ratio * hypot(f[2] - f[0], f[3] - f[1])

    gap = gap_ratio * diag
    geo = []
    dropped = {"frame": 0, "excluded_region": 0, "hint_layer": 0}
    for e in entities:
        if e.kind not in {"line", "arc", "circle"}:
            continue
        b = e.bbox()
        if b is None:
            continue
        if (
            e.handle in frame_handles
            or (b[2] - b[0]) > 0.8 * (sheet[2] - sheet[0])
            or (b[3] - b[1]) > 0.8 * (sheet[3] - sheet[1])
        ):
            dropped["frame"] += 1
            continue  # border / frame lines
        if DIM_LAYER_HINT.search(e.layer or ""):
            dropped["hint_layer"] += 1
            continue
        if any(_inter(b, x) for x in excluded):
            dropped["excluded_region"] += 1
            continue
        geo.append(e)
    boxes = [_expand(e.bbox(), gap_for(e.bbox())) for e in geo]
    uf = _UF(len(geo))
    # sweep on x to keep it near-linear for typical sheets
    order = sorted(range(len(geo)), key=lambda i: boxes[i][0])
    active: list[int] = []
    for i in order:
        active = [j for j in active if boxes[j][2] >= boxes[i][0]]
        for j in active:
            if _inter(boxes[i], boxes[j]):
                uf.join(i, j)
        active.append(i)
    groups: dict[int, list[int]] = {}
    for i in range(len(geo)):
        groups.setdefault(uf.find(i), []).append(i)
    cands = []
    for members in groups.values():
        b = None
        for i in members:
            b = _union(b, geo[i].bbox())
        cands.append((b, [geo[i] for i in members]))
    # merge overlapping cluster boxes (e.g. a hole circle floating inside an outline)
    merged = True
    while merged:
        merged = False
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                if _inter(_expand(cands[i][0], gap_for(cands[i][0])), cands[j][0]):
                    cands[i] = (
                        _union(cands[i][0], cands[j][0]),
                        cands[i][1] + cands[j][1],
                    )
                    cands.pop(j)
                    merged = True
                    break
            if merged:
                break
    cands = [
        c
        for c in cands
        if len(c[1]) >= 3
        and hypot(c[0][2] - c[0][0], c[0][3] - c[0][1])
        > 0.01
        * hypot(
            frame_of(c[0])[2] - frame_of(c[0])[0], frame_of(c[0])[3] - frame_of(c[0])[1]
        )
    ]
    # clusters hugging two or more edges of their frame are title blocks / header boxes, not views
    tables, kept = [], []
    for b, ents in cands:
        f = frame_of(b)
        tol = 0.01 * hypot(f[2] - f[0], f[3] - f[1])
        touching = sum(
            1
            for d in (
                abs(b[0] - f[0]),
                abs(b[1] - f[1]),
                abs(b[2] - f[2]),
                abs(b[3] - f[3]),
            )
            if d <= tol
        )
        (tables if touching >= 2 and f is not sheet else kept).append((b, ents))
    cands = sorted(kept, key=lambda c: -_area(c[0]))
    views = [ViewCandidate(i + 1, b, ents) for i, (b, ents) in enumerate(cands)]
    # attach dimensions / texts to the nearest candidate whose expanded box contains them
    for e in entities:
        if e.kind not in {"dimension", "text"} or e.center is None:
            continue
        p = (
            e.attributes.get("def_point", e.center)
            if e.kind == "dimension"
            else e.center
        )
        hits = [v for v in views if _contains(_expand(v.bbox, 4 * gap), p)]
        if not hits:
            continue
        v = min(
            hits,
            key=lambda v: hypot(
                (v.bbox[0] + v.bbox[2]) / 2 - p[0], (v.bbox[1] + v.bbox[3]) / 2 - p[1]
            ),
        )
        (v.dimensions if e.kind == "dimension" else v.texts).append(e)
    return views, {
        "sheet_bbox": sheet,
        "gap_ratio": gap_ratio,
        "dropped": dropped,
        "geometry_entities": len(geo),
        "table_clusters": [b for b, _ in tables],
    }


# ----------------------------------------------------------------------------- labelling
ORIENTATIONS = {"front", "top", "bottom", "right", "left", "back"}
VIEW_TYPES = ORIENTATIONS | {
    "section",
    "detail",
    "flat_pattern",
    "isometric",
    "table",
    "other",
}


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _relations(center: ViewCandidate, others: list[ViewCandidate]) -> dict[int, str]:
    """above/below/right/left of `center` for clusters sharing >50% of a projection axis range."""
    fx, fy = (center.bbox[0], center.bbox[2]), (center.bbox[1], center.bbox[3])
    rel = {}
    for v in others:
        if v is center:
            continue
        vx, vy = (v.bbox[0], v.bbox[2]), (v.bbox[1], v.bbox[3])
        ox, oy = (
            _overlap(fx, vx) / max(vx[1] - vx[0], 1e-9),
            _overlap(fy, vy) / max(vy[1] - vy[0], 1e-9),
        )
        if ox > 0.5 and v.bbox[1] >= center.bbox[3] - 1e-9:
            rel[v.id] = "above"
        elif ox > 0.5 and v.bbox[3] <= center.bbox[1] + 1e-9:
            rel[v.id] = "below"
        elif oy > 0.5 and v.bbox[0] >= center.bbox[2] - 1e-9:
            rel[v.id] = "right"
        elif oy > 0.5 and v.bbox[2] <= center.bbox[0] + 1e-9:
            rel[v.id] = "left"
    return rel


def label_by_position(views: list[ViewCandidate], projection: str) -> None:
    """Fallback: the front view is the cluster with aligned neighbours on both axes (not the largest one)."""
    if not views:
        return
    for v in views:
        v.label, v.confidence, v.label_source, v.reason = (
            "other",
            0.1,
            "position",
            "no aligned neighbour",
        )
    scored = []
    for v in views:
        rel = _relations(v, views)
        axes = {("above" if r in ("above", "below") else "side") for r in rel.values()}
        scored.append((len(axes), len(rel), _area(v.bbox), v))
    scored.sort(key=lambda t: (-t[0], -t[1], -t[2]))
    front = scored[0][3]
    front.label, front.confidence, front.reason = (
        "front",
        0.4 if scored[0][0] == 2 else 0.25,
        f"{scored[0][1]} aligned neighbours",
    )
    mapping = (
        {"above": "top", "below": "bottom", "right": "right", "left": "left"}
        if projection == "third"
        else {"above": "bottom", "below": "top", "right": "left", "left": "right"}
    )
    taken = set()
    for vid, r in sorted(
        _relations(front, views).items(),
        key=lambda kv: -_area(next(v for v in views if v.id == kv[0]).bbox),
    ):
        lab = mapping[r]
        v = next(v for v in views if v.id == vid)
        if lab in taken:
            v.reason = f"{r} of front; duplicate orientation"
            continue
        taken.add(lab)
        v.label, v.confidence, v.reason = lab, 0.3, f"{r} of front ({projection}-angle)"


def label_with_vlm(
    views: list[ViewCandidate],
    entities: list[RawEntity],
    title: TitleBlock,
    reason: VLMClient,
    work_dir: Path,
) -> dict:
    """Ask the reasoning VLM for view types, projection and part class. Returns the validated decision record."""
    record = {"used": False}
    if not reason.enabled or not views:
        return record
    boxes = [(v.bbox, str(v.id)) for v in views]
    sheet_png = render(
        [e for e in entities if e.kind != "other"],
        work_dir / "sheet_labeled.png",
        boxes=boxes,
        width_in=18,
    )
    sheet = _sheet_bbox(entities)
    W, H = sheet[2] - sheet[0], sheet[3] - sheet[1]
    regions = []
    for v in views:
        b = v.bbox
        regions.append(
            {
                "id": v.id,
                "bbox_norm": [
                    round((b[0] - sheet[0]) / W, 3),
                    round((b[1] - sheet[1]) / H, 3),
                    round((b[2] - sheet[0]) / W, 3),
                    round((b[3] - sheet[1]) / H, 3),
                ],
                "size_units": [round(b[2] - b[0], 1), round(b[3] - b[1], 1)],
                "counts": v.counts(),
                "dimension_texts": [
                    d.text
                    or (f"{d.measurement:.1f}" if d.measurement is not None else "")
                    for d in v.dimensions
                ][:12],
                "nearby_texts": [t.text for t in v.texts if t.text][:8],
            }
        )
    prompt = (
        "You are reading a 2D mechanical engineering drawing sheet. Red numbered boxes mark candidate view regions found by clustering. "
        "bbox_norm is [xmin,ymin,xmax,ymax] with origin at the bottom-left of the sheet (y grows upward).\n"
        f"Title block (may be partial): {json.dumps({k: v for k, v in title.as_dict().items() if k not in ('sources', 'region')}, ensure_ascii=False)}\n"
        f"Regions: {json.dumps(regions, ensure_ascii=False)}\n\n"
        "Skill part_type names map to part_class as: cylinder=cylinder, cone_frustum=cone, bent_sheet=bent_sheet, flat=flat, head (formed/dished)=press_formed, unknown=other. Decide part_class with the skill classification rules before reading any dimension.\n"
        "Decide, using the projection symbol if visible and the relative placement of the regions:\n"
        '1. projection: "first" or "third".\n'
        "2. part_class: one of flat, cylinder, cone, press_formed, bent_sheet, other (press_formed = drawn/stamped curved cover; bent_sheet = straight brake bends).\n"
        "   Also return part_class_scores with one finite relative evidence score (logit) for EVERY class: flat, cylinder, cone, press_formed, bent_sheet, other. "
        "Higher means more likely; these are scores, not probabilities.\n"
        "3. reconstructable_from_views: true only if the orthographic views alone define the shape (false when a note says to follow 3D data, or the part is a freeform pressing).\n"
        "4. For EVERY region id give type in {front, top, bottom, right, left, back, section, detail, flat_pattern, isometric, table, other}, "
        "a confidence 0-1 and a one-sentence reason. Exactly one region may be front; a BOM/revision/notes block is table. "
        "In third-angle projection the top view sits ABOVE the front view and the right view sits to its RIGHT; first-angle is the opposite.\n"
        "Put these decisions in the reasoning block of the shared output contract. "
        "For each view, include overall_width_mm and overall_height_mm only when readable from overall dimensions; otherwise use null."
    )
    data = reason.ask(
        prompt,
        [sheet_png],
        system="You are a careful mechanical drafting checker. Never invent regions that are not listed.",
        task="view_labels",
        skills=STAGE_TOPICS["part_class"],
    )
    record.update(used=True, raw=data, image=str(sheet_png))
    if not isinstance(data, dict) or not isinstance(data.get("views"), list):
        record["error"] = "invalid reply"
        return record
    by_id = {v.id: v for v in views}
    accepted, rejected = [], []
    best: dict[str, ViewCandidate] = {}
    for item in data["views"]:
        try:
            vid, typ, conf = (
                int(item["id"]),
                str(item.get("type", "other")).lower(),
                float(item.get("confidence", 0)),
            )
        except (KeyError, TypeError, ValueError):
            rejected.append({"item": item, "why": "malformed"})
            continue
        if vid not in by_id or typ not in VIEW_TYPES:
            rejected.append({"item": item, "why": "unknown id or type"})
            continue
        v = by_id[vid]
        if typ in ORIENTATIONS and typ in best and best[typ].confidence >= conf:
            rejected.append({"item": item, "why": f"duplicate {typ}, lower confidence"})
            typ = "other"
        v.label, v.confidence, v.label_source, v.reason = (
            typ,
            max(0.0, min(conf, 1.0)),
            f"vlm_reason:{reason.config.model}",
            str(item.get("reason", "")),
        )
        if typ in ORIENTATIONS:
            if typ in best:
                best[typ].label = "other"
            best[typ] = v
        accepted.append(vid)
    reported_class = (
        data.get("part_class")
        if data.get("part_class")
        in {"flat", "cylinder", "cone", "press_formed", "bent_sheet", "other"}
        else None
    )
    probabilities = softmax_class_scores(data.get("part_class_scores"))
    resolved_class = final_part_class(reported_class, probabilities)
    record.update(
        accepted=accepted,
        rejected=rejected,
        projection=data.get("projection")
        if data.get("projection") in {"first", "third"}
        else None,
        part_class=resolved_class,
        part_class_reported=reported_class,
        part_class_scores=data.get("part_class_scores") if probabilities else None,
        part_class_probabilities=probabilities,
        probability_source="llm_reported_scores_softmax" if probabilities else None,
        part_class_consistent=(reported_class == resolved_class)
        if reported_class and resolved_class
        else None,
        reconstructable=data.get("reconstructable_from_views")
        if isinstance(data.get("reconstructable_from_views"), bool)
        else None,
        notes=str(data.get("notes", ""))[:500],
    )
    return record


# ----------------------------------------------------------------------------- document build
def _tessellate_arc(
    e: RawEntity, chord_tol: float
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    a1, a2 = e.start_angle, e.end_angle
    if a2 < a1:
        a2 += 360
    sweep = a2 - a1
    r = max(e.radius, 1e-9)
    step = (
        2 * acos(max(-1.0, min(1.0, 1 - chord_tol / r))) * 180 / 3.141592653589793
        if chord_tol < r
        else 90
    )
    n = max(2, min(64, ceil(sweep / max(step, 1e-3))))
    pts = arc_points(e.center, e.radius, a1, a2, n)
    return list(zip(pts, pts[1:]))


def _line_type(lt: str) -> str:
    s = (lt or "").upper()
    if "CENTER" in s or "DASHDOT" in s:
        return "center"
    if "HIDDEN" in s or "DASH" in s:
        return "hidden"
    return "visible"


def _mirror(name: str) -> tuple[str, tuple[float, float]]:
    """Map left/bottom/back to the front/top/right contract with axis sign flips."""
    return {
        "left": ("right", (-1.0, 1.0)),
        "bottom": ("top", (1.0, -1.0)),
        "back": ("front", (-1.0, 1.0)),
    }.get(name, (name, (1.0, 1.0)))


def _dim_axis(d: RawEntity, geoms: list[RawEntity]) -> str | None:
    """Horizontal/vertical from measured points, then exploded geometry."""
    p2, p3 = d.attributes.get("defpoint2"), d.attributes.get("defpoint3")
    if p2 is not None and p3 is not None:
        dx, dy = abs(p3[0] - p2[0]), abs(p3[1] - p2[1])
        if max(dx, dy) > 1e-9:
            return "h" if dx >= dy else "v"
    best, orient = 0.0, None
    for g in geoms:
        if len(g.points) == 2:
            dx, dy = (
                abs(g.points[1][0] - g.points[0][0]),
                abs(g.points[1][1] - g.points[0][1]),
            )
            if max(dx, dy) > best:
                best, orient = max(dx, dy), ("h" if dx >= dy else "v")
    return orient


def build_document(
    path: Path,
    entities: list[RawEntity],
    views: list[ViewCandidate],
    title: TitleBlock,
    analysis: dict,
    *,
    chord_tol: float = 0.25,
) -> DrawingDocument:
    # group exploded dimension geometry with its DIMENSION entity (reader emits them consecutively)
    dim_geoms: dict[str, list[RawEntity]] = {}
    current = None
    for e in entities:
        if e.kind == "dimension":
            current = e.handle
            dim_geoms[current] = []
        elif e.kind == "dimension_geom" and current:
            dim_geoms[current].append(e)
        else:
            current = None
    review: list[dict] = list(analysis.get("review", []))
    out_views = []
    for v in views:
        if v.label not in ORIENTATIONS:
            continue
        name, (sx, sy) = _mirror(v.label)
        prims, anns = [], []
        for e in v.entities:
            attrs = {
                "layer": e.layer,
                "linetype": e.linetype,
                "source_kind": e.kind,
                **e.attributes,
            }
            if e.kind == "line":
                prims.append(
                    {
                        "id": e.handle,
                        "kind": "line",
                        "points": [
                            (e.points[0][0] * sx, e.points[0][1] * sy),
                            (e.points[1][0] * sx, e.points[1][1] * sy),
                        ],
                        "line_type": _line_type(e.linetype),
                        "attributes": attrs,
                    }
                )
            elif e.kind == "circle":
                prims.append(
                    {
                        "id": e.handle,
                        "kind": "circle",
                        "center": (e.center[0] * sx, e.center[1] * sy),
                        "radius": e.radius,
                        "line_type": _line_type(e.linetype),
                        "attributes": attrs,
                    }
                )
            elif e.kind == "arc":
                for i, (a, b) in enumerate(_tessellate_arc(e, chord_tol)):
                    prims.append(
                        {
                            "id": f"{e.handle}~{i}",
                            "kind": "line",
                            "points": [(a[0] * sx, a[1] * sy), (b[0] * sx, b[1] * sy)],
                            "line_type": _line_type(e.linetype),
                            "attributes": {
                                **attrs,
                                "arc_center": (e.center[0] * sx, e.center[1] * sy),
                                "arc_radius": e.radius,
                            },
                        }
                    )
        hax, vax = (
            "xyz"[{"front": (0, 2), "top": (0, 1), "right": (1, 2)}[name][0]],
            "xyz"[{"front": (0, 2), "top": (0, 1), "right": (1, 2)}[name][1]],
        )
        for d in v.dimensions:
            value = d.measurement
            txt = d.text or ""
            if value is None and txt:
                m = re.search(r"(\d+(?:\.\d+)?)", txt.replace("Ø", "").replace("R", ""))
                value = float(m.group(1)) if m else None
            orient = _dim_axis(d, dim_geoms.get(d.handle, []))
            ann = {
                "id": d.handle,
                "kind": "dimension" if value else "text",
                "text": txt,
                "position": (d.center[0] * sx, d.center[1] * sy),
                "dim_type": d.dim_type,
            }
            if value:
                ann["value"] = value
                if d.dim_type in (0, 1) and orient:  # linear dimensions only
                    ann["axis"] = hax if orient == "h" else vax
                elif txt.startswith(("Ø", "R")) or d.dim_type in (3, 4):
                    ann["kind"], ann["feature"] = (
                        "text",
                        "radius" if txt.startswith("R") else "diameter",
                    )
            anns.append(ann)
        for t in v.texts:
            anns.append(
                {
                    "id": t.handle,
                    "kind": "text",
                    "text": t.text,
                    "position": (t.center[0] * sx, t.center[1] * sy),
                }
            )
        if v.label != name:
            review.append(
                {"view": v.id, "issue": f"{v.label} view mirrored into {name} contract"}
            )
        out_views.append(
            {
                "id": f"view-{v.id}",
                "name": name,
                "primitives": prims,
                "annotations": anns,
            }
        )
    units = title.units or analysis.get("file_units") or "mm"
    if title.units is None and analysis.get("file_units") is None:
        review.append(
            {"issue": "units not found in title block or $INSUNITS; assumed mm"}
        )
    # CAD drawings commonly keep part geometry in real model-space millimeters
    # even when the title block says 1:2. Other files actually scale geometry on
    # the sheet. Compare stored nominal dimensions with raw extents to distinguish
    # these conventions before DrawingInterpreter applies a coordinate factor.
    reported_scale = title.scale or 1.0
    scale_observations: list[tuple[float, float]] = []
    for ov in out_views:
        axes = {"front": ("x", "z"), "top": ("x", "y"), "right": ("y", "z")}[ov["name"]]
        pts = [p for pr in ov["primitives"] for p in pr.get("points", [])] + [
            pr["center"] for pr in ov["primitives"] if pr["kind"] == "circle"
        ]
        if not pts:
            continue
        ext = (
            max(p[0] for p in pts) - min(p[0] for p in pts),
            max(p[1] for p in pts) - min(p[1] for p in pts),
        )
        for k, ax in enumerate(axes):
            vals = [a["value"] for a in ov["annotations"] if a.get("axis") == ax]
            if vals and ext[k] > 0:
                scale_observations.append((ext[k], max(vals)))
    effective_scale = reported_scale
    geometry_scale_mode = "paper_space"
    if reported_scale != 1.0 and scale_observations:
        model_error = sum(
            abs(ext - nominal) / max(abs(nominal), 1e-9)
            for ext, nominal in scale_observations
        )
        paper_error = sum(
            abs(ext / reported_scale - nominal) / max(abs(nominal), 1e-9)
            for ext, nominal in scale_observations
        )
        if model_error < paper_error:
            effective_scale = 1.0
            geometry_scale_mode = "model_space"
            review.append(
                {
                    "issue": f"DXF coordinates match nominal dimensions; title scale {title.scale_text or reported_scale} treated as paper presentation only"
                }
            )
    metadata: dict[str, Any] = {
        "units": units,
        "drawing_scale": effective_scale,
        "reported_drawing_scale": reported_scale,
        "geometry_scale_mode": geometry_scale_mode,
        "title_block": title.as_dict(),
        "sheet_analysis": analysis,
    }
    if title.scale is None:
        review.append({"issue": "scale not found; assumed 1:1"})
    if title.thickness_mm:
        metadata["sheet_thickness"] = title.thickness_mm / (
            25.4 if units == "inch" else 1.0
        )
    # overall dimensions: only when the largest linear dimension per axis agrees with the drawn extent (self-consistency check)
    dims: dict[str, float] = {}
    for ov in out_views:
        axes = {"front": ("x", "z"), "top": ("x", "y"), "right": ("y", "z")}[ov["name"]]
        pts = [p for pr in ov["primitives"] for p in pr.get("points", [])] + [
            pr["center"] for pr in ov["primitives"] if pr["kind"] == "circle"
        ]
        if not pts:
            continue
        ext = (
            max(p[0] for p in pts) - min(p[0] for p in pts),
            max(p[1] for p in pts) - min(p[1] for p in pts),
        )
        for k, ax in enumerate(axes):
            vals = [a["value"] for a in ov["annotations"] if a.get("axis") == ax]
            if vals:
                drawn = ext[k] / effective_scale
                if abs(max(vals) - drawn) <= 0.03 * max(drawn, 1e-9):
                    dims[ax] = max(dims.get(ax, 0), max(vals))
                else:
                    review.append(
                        {
                            "view": ov["id"],
                            "issue": f"largest {ax} dimension {max(vals)} disagrees with drawn extent {drawn:.1f}",
                        }
                    )
    if dims:
        metadata["dimensions"] = dims
    metadata["review"] = review
    return DrawingDocument.from_dict(
        {"metadata": metadata, "views": out_views}, str(path)
    )


# ----------------------------------------------------------------------------- entry points
def _largest_rectangle(entities: list[RawEntity], box: BBox) -> BBox | None:
    """Largest axis-aligned rectangle closed by four lines of the cluster: the plate outline (ignores revision clouds)."""
    rects, _ = detect_frames(entities, box, min_area_ratio=0.1, tol_ratio=0.005)
    return max(rects, key=_area) if rects else None


def _nesting_plates(
    views: list[ViewCandidate], entities: list[RawEntity], sheet: BBox
) -> list[dict]:
    """For a cutting plan: each cluster is a plate; caption 't16 x 970 x 4220 - 1 SH'T' + material line sit just below the outline."""
    diag = hypot(sheet[2] - sheet[0], sheet[3] - sheet[1])
    texts = [e for e in entities if e.kind == "text" and e.text and e.center]
    plates = []
    for v in views:
        v.label, v.label_source, v.confidence, v.reason = (
            "plate",
            "nesting",
            0.5,
            "cluster on a nesting sheet",
        )
        outline = _largest_rectangle(v.entities, v.bbox) or v.bbox
        rec = {
            "id": v.id,
            "bbox": v.bbox,
            "outline": outline,
            "size_drawn": [
                round(outline[2] - outline[0], 1),
                round(outline[3] - outline[1], 1),
            ],
            "counts": v.counts(),
            "part_labels": sorted(
                {
                    t.text.strip()
                    for t in v.texts
                    if t.text
                    and not _NEST_CAPTION.search(t.text)
                    and not _MATERIAL_HINT.fullmatch(t.text.strip())
                }
            ),
        }
        zone = (
            v.bbox[0] - 0.02 * diag,
            outline[1] - 0.08 * diag,
            v.bbox[2] + 0.02 * diag,
            outline[1] + 0.005 * diag,
        )
        below = [t for t in texts if _contains(zone, t.center)]
        cap = next(
            (
                t
                for t in sorted(below, key=lambda t: -t.center[1])
                if _NEST_CAPTION.search(t.text)
            ),
            None,
        )
        if cap:
            m = _NEST_CAPTION.search(cap.text)
            rec.update(
                caption=cap.text.strip(),
                thickness=float(m.group(1)),
                width=float(m.group(2)),
                length=float(m.group(3)),
                quantity=int(m.group(4)) if m.group(4) else None,
            )
            near = sorted(
                (
                    t
                    for t in texts
                    if t is not cap
                    and abs(t.center[0] - cap.center[0]) < 0.03 * diag
                    and 0 < t.center[1] - cap.center[1] < 0.03 * diag
                ),
                key=lambda t: t.center[1] - cap.center[1],
            )
            mat = next((t for t in near if _MATERIAL_HINT.search(t.text)), None)
            if mat:
                rec["material"] = mat.text.strip()
            drawn = sorted(rec["size_drawn"])
            nominal = sorted([rec["width"], rec["length"]])
            rec["caption_matches_outline"] = all(
                abs(d - n) <= 0.05 * max(n, 1) for d, n in zip(drawn, nominal)
            )
        plates.append(rec)
    return plates


def analyze_dxf(
    path: str | Path,
    ocr: VLMClient,
    reason: VLMClient,
    work_dir: str | Path,
    *,
    projection_default: str = "third",
    gap_ratio: float = 0.008,
) -> dict:
    path, work_dir = Path(path), Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    entities, info = read_dxf(path)
    sheet = _sheet_bbox(entities)
    frames, frame_handles = detect_frames(entities, sheet)
    title_regions = find_title_regions(entities, sheet)
    title_region = find_title_region(entities, sheet)
    title = parse_title_block(entities, title_region, ocr, work_dir, reason=reason)
    tables: list[BBox] = []
    for e in entities:
        if e.kind == "text" and e.text and any(k in e.text.upper() for k in TABLE_KEYS):
            tables.append(
                _expand(
                    e.bbox(), 0.01 * hypot(sheet[2] - sheet[0], sheet[3] - sheet[1])
                )
            )
    excluded = title_regions + tables
    views, seg = segment_views(entities, excluded, gap_ratio, frame_handles, frames)
    sheet_type, evidence = classify_sheet(entities, views)
    review: list[dict] = []
    projection = title.projection or projection_default
    decision: dict = {"used": False}
    plates: list[dict] = []
    if sheet_type == "nesting":
        plates = _nesting_plates(views, entities, sheet)
        review.append(
            {
                "issue": "nesting / cutting-plan sheet: orthographic reconstruction not applicable; use `plates`"
            }
        )
        for pl in plates:
            if "caption" not in pl:
                review.append({"view": pl["id"], "issue": "plate without size caption"})
            elif not pl.get("caption_matches_outline"):
                review.append(
                    {
                        "view": pl["id"],
                        "issue": f"caption {pl['caption']} does not match drawn outline {pl['size_drawn']}",
                    }
                )
    else:
        label_by_position(views, projection)
        fallback = {v.id: v.label for v in views}
        decision = label_with_vlm(views, entities, title, reason, work_dir)
        if decision.get("projection"):
            projection = decision["projection"]
            if title.projection is None:
                title.projection, title.sources["projection"] = (
                    projection,
                    f"vlm_reason:{reason.config.model}",
                )
        disagreements = [
            {"view": v.id, "position": fallback[v.id], "vlm": v.label}
            for v in views
            if decision.get("used") and fallback[v.id] != v.label
        ]
        if not decision.get("used"):
            review.append(
                {
                    "issue": "view labels come from relative position only (no reasoning VLM); confirm front/top/right"
                }
            )
        if decision.get("reconstructable") is False:
            review.append(
                {
                    "issue": "model judged the shape not reconstructable from orthographic views alone",
                    "notes": decision.get("notes"),
                }
            )
        review += [
            {
                "view": d["view"],
                "issue": f"position fallback said {d['position']}, VLM said {d['vlm']}",
            }
            for d in disagreements
        ]
        if sheet_type == "unknown":
            review.append(
                {
                    "issue": "sheet type unclear (neither clean orthographic layout nor nesting captions)",
                    "evidence": evidence,
                }
            )
    render(
        [e for e in entities if e.kind != "other"],
        work_dir / "sheet.png",
        boxes=[(v.bbox, f"{v.id}:{v.label}") for v in views],
        width_in=18,
    )
    analysis = {
        "source": str(path),
        "reader": info["reader"],
        "file_units": info["units"],
        "entity_counts": _count(entities),
        "sheet_bbox": sheet,
        "frames": frames,
        "title_regions": title_regions,
        "title_region": title_region,
        "excluded_regions": excluded,
        "segmentation": seg,
        "sheet_type": sheet_type,
        "sheet_type_evidence": evidence,
        "projection": projection,
        "part_class": decision.get("part_class"),
        "part_class_probabilities": decision.get("part_class_probabilities"),
        "part_class_probability_source": decision.get("probability_source"),
        "reconstructable": decision.get("reconstructable"),
        "title_block": title.as_dict(),
        "views": [
            {
                "id": v.id,
                "bbox": v.bbox,
                "label": v.label,
                "confidence": v.confidence,
                "source": v.label_source,
                "reason": v.reason,
                "counts": v.counts(),
            }
            for v in views
        ],
        "plates": plates,
        "vlm_decision": {k: v for k, v in decision.items() if k != "raw"},
        "vlm_trace": ocr.trace + reason.trace,
        "review": review,
        "renders": {"sheet": str(work_dir / "sheet.png")},
    }
    (work_dir / "sheet_analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, default=list),
        encoding="utf-8",
    )
    return {"entities": entities, "views": views, "title": title, "analysis": analysis}


def _count(entities) -> dict:
    c: dict[str, int] = {}
    for e in entities:
        k = e.attributes.get("dxftype", e.kind) if e.kind == "other" else e.kind
        c[k] = c.get(k, 0) + 1
    return c


class NotOrthographicSheet(ValueError):
    """Raised when the sheet is a nesting / cutting plan; `analysis` carries the plate list."""

    def __init__(self, analysis: dict):
        super().__init__(
            f"{analysis['sheet_type']} sheet: {len(analysis.get('plates', []))} plates found; orthographic reconstruction not applicable"
        )
        self.analysis = analysis


def load_dxf_document(
    path: str | Path, ocr: VLMClient, reason: VLMClient, work_dir: str | Path, **kw
) -> DrawingDocument:
    a = analyze_dxf(path, ocr, reason, work_dir, **kw)
    if a["analysis"]["sheet_type"] == "nesting":
        raise NotOrthographicSheet(a["analysis"])
    return build_document(
        Path(path), a["entities"], a["views"], a["title"], a["analysis"]
    )
