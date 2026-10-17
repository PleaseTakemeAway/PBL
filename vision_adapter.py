"""Vision-first adapter: image -> text/geometry (vision_reader) -> view candidates -> reasoning VLM -> DrawingDocument.

Decision policy (same as the DXF adapter): deterministic code owns coordinates,
calibration and consistency checks; the OCR VLM owns reading; the reasoning VLM
owns labels, projection, part class and the final pick among 3D candidates. Every
model decision is validated against the deterministic evidence and logged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from pathlib import Path
import json
import re
from typing import Any

from dxf_adapter import ORIENTATIONS, VIEW_TYPES, ViewCandidate, _area, _contains, _expand, _inter, _relations, label_by_position
from models import DrawingDocument, ReconstructionResult
from vision_reader import PxBox, PxPrimitive, SheetImage, TextItem, binarize, crop, extract_geometry, find_regions, load_sheet, read_texts, save_debug, snap, stroke_width
from vlm import VLMClient, final_part_class, read_ocr_task, softmax_class_scores

_SCALE = re.compile(r"(\d+(?:\.\d+)?)\s*[/:]\s*(\d+(?:\.\d+)?)")
_THICK = re.compile(r"(\d+(?:\.\d+)?)\s*t\b|\bt\s*(\d+(?:\.\d+)?)\b", re.I)
_MAT = re.compile(r"\b(SPCC|SPHC|SS400|SS41|SA\d{3}[-\w]*|SUS\d{3}|A\d{3}|AL\d{4}|S\d{2}C|STKM\w*|SM\d{3}\w*)\b", re.I)
_DWG = re.compile(r"\b([A-Z0-9]{2,6}-[A-Z0-9]{3,8})\b")
_PAPER = re.compile(r"\b(A[0-4])\b|\(?\s*(\d{3})\s*[x×]\s*(\d{3})\s*\)?")
_PAPER_MM = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297)}


@dataclass
class TitleInfo:
    drawing_no: str | None = None
    part_name: str | None = None
    material: str | None = None
    thickness_mm: float | None = None
    scale: float | None = None
    scale_text: str | None = None
    units: str | None = None
    projection: str | None = None
    paper_mm: tuple[float, float] | None = None
    region: PxBox | None = None
    sources: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


class VisionView(ViewCandidate):
    """A view candidate living in image pixels; bbox_up is the y-up copy used by the position rules."""
    def __init__(self, vid: int, bbox_px: PxBox, height: int):
        super().__init__(vid, (bbox_px[0], height-bbox_px[3], bbox_px[2], height-bbox_px[1]), [])
        self.bbox_px = bbox_px
        self.prims: list[PxPrimitive] = []
        self.text_items: list[TextItem] = []
        self.px_per_mm: float | None = None
        self.overall_mm: dict[str, float] = {}

    def counts(self) -> dict:
        c = {"line": 0, "hidden": 0, "circle": 0, "dimensions": 0}
        for p in self.prims:
            if p.kind == "circle":
                c["circle"] += 1
            elif p.line_type == "hidden":
                c["hidden"] += 1
            else:
                c["line"] += 1
        c["dimensions"] = sum(1 for t in self.text_items if t.kind == "dimension")
        return c


# ----------------------------------------------------------------------------- title block
def parse_title(texts: list[TextItem], sheet: SheetImage, ocr: VLMClient, work_dir: Path,
                reason: VLMClient | None = None) -> TitleInfo:
    ti = TitleInfo()
    titles = [t for t in texts if t.kind == "title"]
    if titles:
        # cluster title keywords by proximity; the densest cluster is the title block ("NEW DRAWING", footers are elsewhere)
        reach = 0.12*hypot(sheet.width, sheet.height)
        groups: list[list[TextItem]] = []
        for t in titles:
            for g in groups:
                if any(hypot(t.center[0]-u.center[0], t.center[1]-u.center[1]) < reach for u in g):
                    g.append(t); break
            else:
                groups.append([t])
        strong = max(groups, key=lambda g: (sum(1 for t in g if re.search(r"SCALE|MATERIAL|DW'?G|TOLERANCE", t.text, re.I)), len(g)))
        r = None
        for t in strong:
            r = t.bbox if r is None else (min(r[0], t.bbox[0]), min(r[1], t.bbox[1]), max(r[2], t.bbox[2]), max(r[3], t.bbox[3]))
        ti.region = _expand(r, 0.02*hypot(sheet.width, sheet.height))
    # values sit to the right of their keywords: widen the search pool horizontally
    pool_box = (ti.region[0], ti.region[1], ti.region[2]+0.12*sheet.width, ti.region[3]) if ti.region else None
    pool = [t for t in texts if pool_box is None or _contains(pool_box, t.center)] or texts
    joined = " \n".join(t.text for t in pool)
    lab = next((t for t in pool if "SCALE" in t.text.upper()), None)
    m = _SCALE.search(lab.text) if lab else None
    if not m and lab:
        near = [t for t in pool if _SCALE.fullmatch(t.text.strip()) and hypot(t.center[0]-lab.center[0], t.center[1]-lab.center[1]) < 0.12*sheet.width]
        if near:
            m = _SCALE.fullmatch(min(near, key=lambda t: hypot(t.center[0]-lab.center[0], t.center[1]-lab.center[1])).text.strip())
    if m and float(m.group(2)) > 0:
        ti.scale, ti.scale_text, ti.sources["scale"] = float(m.group(1))/float(m.group(2)), f"{m.group(1)}/{m.group(2)}", "regex"
    mat = next((t for t in pool if _MAT.search(t.text)), None)
    if mat:
        ti.material, ti.sources["material"] = re.sub(r"MATERIAL", "", mat.text, flags=re.I).strip(" :"), "regex"
        tm = _THICK.search(mat.text)
        if tm:
            ti.thickness_mm, ti.sources["thickness_mm"] = float(tm.group(1) or tm.group(2)), "regex"
    big = sorted((t for t in pool if _DWG.fullmatch(t.text.strip())), key=lambda t: -(t.bbox[3]-t.bbox[1]))
    if big:
        ti.drawing_no, ti.sources["drawing_no"] = big[0].text.strip(), "regex"
    if re.search(r"\bmm\b", joined, re.I):
        ti.units, ti.sources["units"] = "mm", "regex"
    for t in texts:
        pm = _PAPER.search(t.text)
        if pm:
            if pm.group(1):
                ti.paper_mm = _PAPER_MM[pm.group(1)]
            else:
                a, b = sorted((float(pm.group(2)), float(pm.group(3))))
                ti.paper_mm = (a, b)
            ti.sources["paper_mm"] = "regex"
            break
    missing = [k for k in ("drawing_no", "part_name", "material", "thickness_mm", "scale", "units", "projection") if getattr(ti, k) is None]
    if missing and ocr.enabled and ti.region:
        img = crop(sheet, ti.region, work_dir/"title_block.png", max_side=1600)
        prompt = ("This is the title block of an engineering drawing. Read these title_block fields: drawing_no, part_name, material, thickness_mm (number), "
                       "scale (like \"1/4\"), units (\"mm\"|\"inch\"), projection (\"first\"|\"third\" from the cone symbol; small circle LEFT of the truncated cone = third angle). "
                       "Use null when not visible.")
        data = read_ocr_task(ocr, reason, [img], task="title_block", instructions=prompt)
        if isinstance(data, dict):
            for k in missing:
                v = data.get(k)
                if v in (None, "", "null"):
                    continue
                if k == "scale":
                    sm = _SCALE.fullmatch(str(v).strip())
                    if sm and float(sm.group(2)) > 0:
                        ti.scale, ti.scale_text = float(sm.group(1))/float(sm.group(2)), str(v).strip()
                    else:
                        continue
                elif k == "thickness_mm":
                    try:
                        ti.thickness_mm = float(v)
                    except (TypeError, ValueError):
                        continue
                elif k in ("projection", "units"):
                    if str(v).lower() not in ({"first", "third"} if k == "projection" else {"mm", "inch"}):
                        continue
                    setattr(ti, k, str(v).lower())
                else:
                    setattr(ti, k, str(v).strip())
                ti.sources[k] = f"vlm_reason:{reason.config.model}+vlm_ocr:{ocr.config.model}"
    return ti


# ----------------------------------------------------------------------------- reasoning VLM
def label_views_vlm(views: list[VisionView], sheet: SheetImage, title: TitleInfo, reason: VLMClient, work_dir: Path) -> dict:
    rec: dict = {"used": False}
    if not reason.enabled or not views:
        return rec
    img = save_debug(sheet, work_dir/"sheet_labeled.png", boxes=[(v.bbox_px, str(v.id)) for v in views])
    regions = []
    for v in views:
        b = v.bbox_px
        regions.append({"id": v.id, "bbox_norm": [round(b[0]/sheet.width, 3), round(b[1]/sheet.height, 3), round(b[2]/sheet.width, 3), round(b[3]/sheet.height, 3)],
                        "size_px": [round(b[2]-b[0]), round(b[3]-b[1])], "counts": v.counts(),
                        "dimension_texts": [t.text for t in v.text_items if t.kind == "dimension"][:14],
                        "labels": [t.text for t in v.text_items if t.kind in {"label", "caption"}][:8]})
    prompt = (
        "You are reading a scanned 2D mechanical engineering drawing. Red numbered boxes are candidate view regions. bbox_norm = [x0,y0,x1,y1] with origin top-left, y DOWN.\n"
        f"Title block: {json.dumps({k: v for k, v in title.as_dict().items() if k not in ('sources', 'region')}, ensure_ascii=False)}\n"
        f"Regions: {json.dumps(regions, ensure_ascii=False)}\n\n"
        "Fill the shared reasoning block with projection, part_class, part_class_scores, reconstructable_from_views and views.\n"
        "Each view needs id, type, confidence, reason, overall_width_mm and overall_height_mm. "
        "View type is front, top, bottom, right, left, back, section, detail, flat_pattern, isometric, table or other.\n"
        "Rules: exactly one front. part_class_scores must contain finite relative evidence scores (logits), not probabilities, for all six classes; higher means more likely. "
        "In third-angle projection the top view is ABOVE the front and the right view is to its RIGHT (first-angle is the opposite). "
        "overall_width/height are the outermost dimension numbers that span the whole region horizontally/vertically (read them from dimension_texts); null if none. "
        "reconstructable_from_views is false when a note says to follow 3D data or the part is a freeform pressing. Never invent region ids.")
    data = reason.ask(prompt, [img], system="You are a careful mechanical drafting checker.", task="view_labels")
    rec.update(used=True, image=str(img))
    if not isinstance(data, dict) or not isinstance(data.get("views"), list):
        rec["error"] = "invalid reply"
        return rec
    by_id = {v.id: v for v in views}
    best: dict[str, VisionView] = {}
    accepted, rejected = [], []
    for it in data["views"]:
        try:
            vid, typ, conf = int(it["id"]), str(it.get("type", "other")).lower(), float(it.get("confidence", 0))
        except (KeyError, TypeError, ValueError):
            rejected.append({"item": it, "why": "malformed"}); continue
        if vid not in by_id or typ not in VIEW_TYPES:
            rejected.append({"item": it, "why": "unknown id or type"}); continue
        v = by_id[vid]
        if typ in ORIENTATIONS and typ in best and best[typ].confidence >= conf:
            rejected.append({"item": it, "why": f"duplicate {typ}"}); typ = "other"
        v.label, v.confidence, v.label_source, v.reason = typ, max(0.0, min(conf, 1.0)), f"vlm_reason:{reason.config.model}", str(it.get("reason", ""))
        for k in ("overall_width_mm", "overall_height_mm"):
            if isinstance(it.get(k), (int, float)) and it[k] > 0:
                v.overall_mm[k] = float(it[k])
        if typ in ORIENTATIONS:
            if typ in best:
                best[typ].label = "other"
            best[typ] = v
        accepted.append(vid)
    reported_class = data.get("part_class") if data.get("part_class") in {"flat", "cylinder", "cone", "press_formed", "bent_sheet", "other"} else None
    probabilities = softmax_class_scores(data.get("part_class_scores"))
    resolved_class = final_part_class(reported_class, probabilities)
    rec.update(accepted=accepted, rejected=rejected,
               projection=data.get("projection") if data.get("projection") in {"first", "third"} else None,
               part_class=resolved_class,
               part_class_reported=reported_class,
               part_class_scores=data.get("part_class_scores") if probabilities else None,
               part_class_probabilities=probabilities,
               probability_source="llm_reported_scores_softmax" if probabilities else None,
               part_class_consistent=(reported_class == resolved_class) if reported_class and resolved_class else None,
               reconstructable=data.get("reconstructable_from_views") if isinstance(data.get("reconstructable_from_views"), bool) else None,
               notes=str(data.get("notes", ""))[:500])
    return rec


# ----------------------------------------------------------------------------- calibration
def _axis_extent_px(v: VisionView, axis: int) -> float | None:
    """Longest visible line along the axis: the drawn overall size in pixels."""
    best = 0.0
    for p in v.prims:
        if p.kind == "line" and p.line_type == "visible":
            d = abs(p.points[1][axis]-p.points[0][axis]); o = abs(p.points[1][1-axis]-p.points[0][1-axis])
            if o < 3 and d > best:
                best = d
    return best or None


def _overall_from_dims(v: VisionView, axis: int) -> float | None:
    """Fallback: largest linear dimension written horizontally (axis 0) / vertically (axis 1) near the view."""
    vals = []
    for t in v.text_items:
        if t.kind != "dimension" or t.feature or t.value is None:
            continue
        vertical = (t.bbox[3]-t.bbox[1]) > (t.bbox[2]-t.bbox[0]) or t.source.endswith("rot90")
        if (axis == 1) == vertical:
            vals.append(t.value)
    return max(vals) if vals else None


def calibrate(views: list[VisionView], title: TitleInfo, frame_bbox: PxBox | None, review: list[dict]) -> dict:
    info: dict[str, Any] = {"method": None}
    paper_ppm = None
    if title.paper_mm and frame_bbox and title.scale:
        fw, fh = frame_bbox[2]-frame_bbox[0], frame_bbox[3]-frame_bbox[1]
        long_mm, short_mm = max(title.paper_mm), min(title.paper_mm)
        px_per_paper_mm = (max(fw, fh)/long_mm+min(fw, fh)/short_mm)/2
        paper_ppm = px_per_paper_mm*title.scale          # 1 real mm = scale paper mm
        info.update(method="paper+scale", px_per_paper_mm=round(px_per_paper_mm, 4), px_per_mm=round(paper_ppm, 4))
    per_view, per_view_weight = {}, {}
    for v in views:
        if v.label not in ORIENTATIONS:
            continue
        ests = []   # (px_per_mm, weight = px length): short extents are stroke-dominated, so weight by length
        for axis, key in ((0, "overall_width_mm"), (1, "overall_height_mm")):
            mm = v.overall_mm.get(key) or _overall_from_dims(v, axis)
            px = _axis_extent_px(v, axis)
            if mm and px and mm > 0 and px > 40:
                ests.append((px/mm, px))
        if ests:
            per_view[v.id] = sum(e*w for e, w in ests)/sum(w for _, w in ests)
            per_view_weight[v.id] = sum(w for _, w in ests)
    dim_ppm = None
    if per_view:
        vals = sorted(per_view.values())
        med = vals[len(vals)//2]
        anchor = paper_ppm if paper_ppm else med          # paper+scale is a strong prior when the title block was read
        keep = {k: v for k, v in per_view.items() if abs(v-anchor)/anchor <= (0.2 if paper_ppm else 0.15)}
        if not keep and paper_ppm:
            review.append({"issue": f"no per-view scale agrees with paper/scale {paper_ppm:.3f} px/mm; using paper/scale"})
            per_view = {}
        for k in per_view:
            if k not in keep:
                review.append({"view": k, "issue": f"per-view scale {per_view[k]:.3f} px/mm rejected (median {med:.3f})"})
        if keep:
            dim_ppm = sum(keep[k]*per_view_weight[k] for k in keep)/sum(per_view_weight[k] for k in keep)
            info["per_view_kept"] = list(keep)
    if dim_ppm:
        ppm, info["method"] = dim_ppm, "dimensions"
        if paper_ppm and abs(paper_ppm-dim_ppm)/dim_ppm > 0.1:
            review.append({"issue": f"scale check: dimensions give {dim_ppm:.3f} px/mm, frame/paper gives {paper_ppm:.3f} (frame is usually smaller than the paper)"})
    elif paper_ppm:
        ppm = paper_ppm
        review.append({"issue": "calibrated from frame size and title-block scale only; the frame is normally inset from the paper edge, expect ~5% error"})
    else:
        ppm = None
        review.append({"issue": "no calibration (no paper size/scale and no overall dimensions); coordinates left in pixels"})
    info.update(px_per_mm=ppm, per_view=per_view)
    for v in views:
        v.px_per_mm = per_view.get(v.id, ppm)
    return info


# ----------------------------------------------------------------------------- document build
def _mirror(name: str) -> tuple[str, tuple[float, float]]:
    return {"left": ("right", (-1.0, 1.0)), "bottom": ("top", (1.0, -1.0)), "back": ("front", (-1.0, 1.0))}.get(name, (name, (1.0, 1.0)))


def build_document(path: Path, sheet: SheetImage, views: list[VisionView], title: TitleInfo, analysis: dict) -> DrawingDocument:
    review: list[dict] = list(analysis.get("review", []))
    ppm_global = analysis["calibration"].get("px_per_mm")
    out_views = []
    axes_of = {"front": ("x", "z"), "top": ("x", "y"), "right": ("y", "z")}
    for v in views:
        if v.label not in ORIENTATIONS:
            continue
        name, (sx, sy) = _mirror(v.label)
        ppm = v.px_per_mm or ppm_global or 1.0

        def to_mm(p):
            return ((p[0]-v.bbox_px[0])/ppm*sx, (v.bbox_px[3]-p[1])/ppm*sy)
        prims, anns = [], []
        for i, p in enumerate(v.prims):
            if p.kind == "line":
                a, b = to_mm(p.points[0]), to_mm(p.points[1])
                if hypot(a[0]-b[0], a[1]-b[1]) < 1e-6:
                    continue
                prims.append({"id": f"v{v.id}-l{i}", "kind": "line", "points": [a, b], "line_type": p.line_type, "attributes": {"ink_ratio": p.ink_ratio, "source": "cv"}})
            elif p.kind == "circle":
                prims.append({"id": f"v{v.id}-c{i}", "kind": "circle", "center": to_mm(p.center), "radius": p.radius/ppm, "line_type": "visible", "attributes": {"source": "cv"}})
        hax, vax = axes_of[name]
        for j, t in enumerate(v.text_items):
            ann = {"id": f"v{v.id}-t{j}", "kind": "text", "text": t.text, "position": to_mm(t.center), "ocr_source": t.source}
            if t.kind == "dimension" and t.value:
                ann["value"] = t.value
                if t.feature is None:
                    vertical = (t.bbox[3]-t.bbox[1]) > (t.bbox[2]-t.bbox[0]) or t.source.endswith("rot90")
                    ann["kind"], ann["axis"] = "dimension", (vax if vertical else hax)
                else:
                    ann["feature"], ann["count"] = t.feature, t.count
            anns.append(ann)
        if not prims:
            review.append({"view": v.id, "issue": "no geometry extracted"})
            continue
        if v.label != name:
            review.append({"view": v.id, "issue": f"{v.label} mirrored into {name}"})
        out_views.append({"id": f"view-{v.id}", "name": name, "primitives": prims, "annotations": anns})
    units = title.units or "mm"
    metadata: dict[str, Any] = {"units": units, "drawing_scale": 1.0, "title_block": title.as_dict(), "sheet_analysis": analysis,
                                "suggested_tolerance_mm": round(max(1.5, 1.2*analysis.get("stroke_px", 2.0))/(ppm_global or 1.0), 4)}
    if title.thickness_mm:
        metadata["sheet_thickness"] = title.thickness_mm
    dims: dict[str, float] = {}
    for ov in out_views:
        pts = [p for pr in ov["primitives"] for p in pr.get("points", [])]
        if not pts:
            continue
        ext = (max(p[0] for p in pts)-min(p[0] for p in pts), max(p[1] for p in pts)-min(p[1] for p in pts))
        for k, ax in enumerate(axes_of[ov["name"]]):
            vals = [a["value"] for a in ov["annotations"] if a.get("axis") == ax]
            if vals and abs(max(vals)-ext[k]) <= 0.04*max(ext[k], 1e-9):
                dims[ax] = max(dims.get(ax, 0.0), max(vals))
            elif vals:
                review.append({"view": ov["id"], "issue": f"largest {ax} dimension {max(vals)} vs drawn {ext[k]:.1f} mm"})
    if dims:
        metadata["dimensions"] = dims
    metadata["review"] = review
    return DrawingDocument.from_dict({"metadata": metadata, "views": out_views}, str(path))


# ----------------------------------------------------------------------------- entry
class NotOrthographicSheet(ValueError):
    def __init__(self, analysis: dict):
        super().__init__(f"{analysis['sheet_type']} sheet: {len(analysis.get('plates', []))} plates; orthographic reconstruction not applicable")
        self.analysis = analysis


def analyze_image(path: str | Path, ocr: VLMClient, reason: VLMClient, work_dir: str | Path, *, projection_default: str = "third", dpi: int = 200) -> dict:
    path, work_dir = Path(path), Path(work_dir)
    sheet = load_sheet(path, work_dir, dpi=dpi)
    texts, ocr_source = read_texts(sheet, ocr, work_dir, reason=reason)
    title = parse_title(texts, sheet, ocr, work_dir, reason=reason)
    boxes, seg = find_regions(sheet, texts, exclude=[title.region] if title.region else None)
    masks = seg.pop("masks")
    views = [VisionView(i+1, b, sheet.height) for i, b in enumerate(boxes)]
    diag = hypot(sheet.width, sheet.height)
    stroke = stroke_width(binarize(sheet))
    snap_tol = max(2.5, 1.6*stroke)
    for v, m in zip(views, masks):
        v.prims = snap(extract_geometry(sheet, v.bbox_px, texts, mask=m), tol=snap_tol)
        near = _expand(v.bbox_px, 0.03*diag)
        v.text_items = [t for t in texts if _contains(near, t.center) and t.kind in {"dimension", "label", "caption", "note"}]
    # a lone rule (table edge, leader) is not a view: too thin and fewer than 3 primitives
    dropped = [v for v in views if min(v.bbox_px[2]-v.bbox_px[0], v.bbox_px[3]-v.bbox_px[1]) < 3*stroke and len(v.prims) < 3]
    views = [v for v in views if v not in dropped]
    for i, v in enumerate(views):
        v.id = i+1
    captions = [t for t in texts if t.kind == "caption"]
    sheet_type = "nesting" if len(captions) >= 2 else ("orthographic" if views else "unknown")
    review: list[dict] = []
    decision: dict = {"used": False}
    projection = title.projection or projection_default
    plates: list[dict] = []
    if sheet_type == "nesting":
        for v in views:
            v.label, v.label_source, v.confidence = "plate", "nesting", 0.5
            below = [t for t in captions if v.bbox_px[0]-0.02*diag <= t.center[0] <= v.bbox_px[2]+0.02*diag and v.bbox_px[3]-0.01*diag <= t.center[1] <= v.bbox_px[3]+0.08*diag]
            rec = {"id": v.id, "bbox_px": v.bbox_px, "part_labels": sorted({t.text for t in v.text_items if t.kind == "label"})}
            if below:
                rec["caption"] = min(below, key=lambda t: t.center[1]).text
            plates.append(rec)
        review.append({"issue": "nesting / cutting-plan sheet: orthographic reconstruction not applicable; use `plates`"})
    else:
        label_by_position(views, projection)
        fallback = {v.id: v.label for v in views}
        decision = label_views_vlm(views, sheet, title, reason, work_dir)
        if decision.get("projection"):
            projection = decision["projection"]
            if title.projection is None:
                title.projection, title.sources["projection"] = projection, f"vlm_reason:{reason.config.model}"
        if not decision.get("used"):
            review.append({"issue": "view labels from relative position only (no reasoning VLM)"})
        if decision.get("reconstructable") is False:
            review.append({"issue": "model judged the shape not reconstructable from views alone", "notes": decision.get("notes")})
        review += [{"view": v.id, "issue": f"position fallback said {fallback[v.id]}, VLM said {v.label}"} for v in views if decision.get("used") and fallback[v.id] != v.label]
    calibration = calibrate(views, title, seg.get("frame_bbox"), review) if sheet_type != "nesting" else {"method": None}
    save_debug(sheet, work_dir/"sheet.png", boxes=[(v.bbox_px, f"{v.id}:{v.label}") for v in views], texts=texts, prims=[p for v in views for p in v.prims])
    analysis = {
        "source": str(path), "image": str(sheet.path), "image_size": [sheet.width, sheet.height], "ocr_source": ocr_source, "text_count": len(texts),
        "text_kinds": {k: sum(1 for t in texts if t.kind == k) for k in {t.kind for t in texts}},
        "segmentation": {**seg, "dropped_thin_regions": len(dropped)}, "stroke_px": round(stroke, 2), "snap_tol_px": round(snap_tol, 2), "sheet_type": sheet_type, "projection": projection, "part_class": decision.get("part_class"),
        "part_class_probabilities": decision.get("part_class_probabilities"), "part_class_probability_source": decision.get("probability_source"), "reconstructable": decision.get("reconstructable"),
        "calibration": calibration,
        "views": [{"id": v.id, "bbox_px": v.bbox_px, "label": v.label, "confidence": v.confidence, "source": v.label_source, "reason": v.reason, "counts": v.counts(),
                   "px_per_mm": v.px_per_mm, "overall_mm": v.overall_mm, "dimension_texts": [t.text for t in v.text_items if t.kind == "dimension"]} for v in views],
        "plates": plates, "title_block": title.as_dict(), "vlm_decision": decision, "vlm_trace": ocr.trace+reason.trace, "review": review,
        "renders": {"sheet": str(work_dir/"sheet.png")},
    }
    (work_dir/"sheet_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
    return {"sheet": sheet, "texts": texts, "views": views, "title": title, "analysis": analysis}


def load_image_document(path: str | Path, ocr: VLMClient, reason: VLMClient, work_dir: str | Path, **kw) -> DrawingDocument:
    a = analyze_image(path, ocr, reason, work_dir, **kw)
    if a["analysis"]["sheet_type"] == "nesting":
        raise NotOrthographicSheet(a["analysis"])
    return build_document(Path(path), a["sheet"], a["views"], a["title"], a["analysis"])


# ----------------------------------------------------------------------------- candidate confirmation
def confirm_candidates(result: ReconstructionResult, reason: VLMClient, work_dir: str | Path, *, top_k: int = 3) -> dict:
    """Show the reasoning VLM the original views next to the reprojection of each ranked candidate and ask it to pick.
    The validator ranking stays authoritative; a disagreement becomes a review item."""
    rec: dict = {"used": False}
    valid = [e for e in result.evaluations if e.valid]
    cands = [c for c in result.candidates if c.id in {e.candidate_id for e in valid}][:top_k]
    if not reason.enabled or len(cands) < 1:
        return rec
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from geometry import project
    work_dir = Path(work_dir)
    fig, axes = plt.subplots(len(cands)+1, len(result.views), figsize=(4*len(result.views), 3.2*(len(cands)+1)))
    axes = axes.reshape(len(cands)+1, len(result.views))
    for j, view in enumerate(result.views):
        ax = axes[0][j]
        for p in view.primitives:
            if p.kind == "line":
                ax.plot([p.points[0][0], p.points[1][0]], [p.points[0][1], p.points[1][1]], "k-" if p.line_type == "visible" else "k--", lw=1)
            elif p.kind == "circle":
                ax.add_patch(plt.Circle(p.center, p.radius, fill=False, lw=1))
        ax.set_title(f"original {view.name}"); ax.set_aspect("equal"); ax.axis("off")
        for i, c in enumerate(cands):
            ax = axes[i+1][j]
            for a, b in c.edges:
                pa, pb = project(c.vertices[a], view), project(c.vertices[b], view)
                ax.plot([pa[0], pb[0]], [pa[1], pb[1]], "b-", lw=1)
            ax.set_title(f"candidate {i+1} ({c.id}) {view.name}"); ax.set_aspect("equal"); ax.axis("off")
    img = work_dir/"candidates.png"
    fig.tight_layout(); fig.savefig(img, dpi=110); plt.close(fig)
    scores = {c.id: next(e.score for e in result.evaluations if e.candidate_id == c.id) for c in cands}
    prompt = (f"Top row: the original orthographic views. Rows below: {len(cands)} reconstructed 3D candidates reprojected into the same views (blue). "
              f"Validator scores: {json.dumps(scores)}. Pick the candidate whose reprojection matches the originals best, considering hidden (dashed) lines too. "
              "Fill the shared confirmation block: pick is the candidate number (1-based) or null if none matches, "
              "confidence is 0-1, reason is a string, and problems is a list of strings.")
    data = reason.ask(prompt, [img], task="candidate_confirmation")
    rec.update(used=True, image=str(img), candidates=[c.id for c in cands])
    rec["response"] = reason.trace[-1].get("response") if reason.trace else None
    if isinstance(data, dict) and isinstance(data.get("pick"), int) and 1 <= data["pick"] <= len(cands):
        rec.update(pick=cands[data["pick"]-1].id, confidence=data.get("confidence"), reason=str(data.get("reason", ""))[:400], problems=data.get("problems", []))
        if rec["pick"] != cands[0].id:
            result.review_request.setdefault("ambiguities", []).append({"kind": "candidate_choice", "issue": f"VLM preferred {rec['pick']} over validator top {cands[0].id}", "reason": rec["reason"]})
            result.review_request["status"] = "needs_review"
    else:
        rec["error"] = "no usable pick"
    result.metadata["candidate_confirmation"] = rec
    return rec
