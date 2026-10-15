# -*- coding: utf-8 -*-
"""
L3 계산·로직(Rule engine) — 결정적. LLM 은 파라미터만 넘긴다.

  unfold_part            PartSpec → 전개 블랭크 (툴킷 vlm/unfold.py 재사용: 원통·원뿔·절곡·평판 + 헤드 블랭크·패드 링)
  split_to_pieces        판 폭/길이·용접선 기준으로 조각 분할 + 커팅여유 → state.pieces
  nest_group / nest_all  (재질, 두께) 그룹별 shelf 배치, 멀티규격·맞춤 판재 → state.sheets
  write_cutting_plan_dxf 커팅플랜 DXF (기존 CP 도면 형식의 라벨)
  build_por              POR PLATE 행 (품명, 재질, t x W x L, 수량 SH, 중량 kg) → state.por + por.csv

KD25038 검증값: 쉘 ID2600 t10 → 코스 8168~8199 x 1700/2400, 헤드 Ø3240, 판 2438x9150 → 1,751 kg.
"""
from __future__ import annotations
import csv, math, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import (TOOLKIT, DENSITY_STEEL, KERF_MARGIN, DEFAULT_CUT, TRANSPORT_MAX, EDGE_MARGIN,
                      STD_WIDTHS, STD_LENGTHS)
from ..state import Piece, Placement, Sheet, get_state, logged

sys.path.insert(0, str(TOOLKIT / "vlm"))
try:
    from unfold import PartModel as TkPartModel, unfold as tk_unfold          # 툴킷 전개 엔진 (검증됨)
except Exception:                                                               # 툴킷이 없으면 아래 최소 구현
    TkPartModel = None

HEAD_BLANK_FACTOR = 1.25     # 2:1 ellip. 블랭크 ≈ 1.25 x ID (KD23002 Ø1296/1027, KD25038 Ø3240/2600 역산). TODO: part_tags HEAD 14건으로 보정
LENGTH_SNAP = 10.0           # 맞춤 판재 길이 반올림 (실제 POR: 9150, 10270, 8870)


# ----------------------------------------------------------------------------- 전개
def _cyl(ID: float, t: float, L: float) -> Dict[str, Any]:
    circ = math.pi * (ID + t)
    return {"type": "cylinder", "blank_w": round(circ, 1), "blank_h": round(L, 1), "area": circ * L,
            "formula": f"L = pi x (ID + t) = pi x ({ID} + {t}) = {circ:.1f}", "shape": "rect"}


def _cone(ID1: float, ID2: float, h: float, t: float) -> Dict[str, Any]:
    D1m, D2m = ID1 + t, (ID2 + t if ID2 > 0 else t)
    dR = (D1m - D2m) / 2.0
    s = math.hypot(h, dR)
    R1 = s * D1m / (D1m - D2m)
    R2 = R1 - s
    theta = math.pi * D1m / R1
    area = 0.5 * theta * (R1 ** 2 - R2 ** 2)
    return {"type": "cone_frustum", "R1": R1, "R2": R2, "theta_deg": math.degrees(theta), "slant": s, "area": area,
            "formula": f"s={s:.1f} R1={R1:.1f} R2={R2:.1f} theta={math.degrees(theta):.2f}deg", "shape": "sector",
            **_sector_bbox(R1, R2, 0.0, theta)}


def _sector_bbox(R1: float, R2: float, a0: float, a1: float) -> Dict[str, float]:
    """중심각 a0~a1 (rad) 의 환형 부채꼴 bbox (중심각을 -축 대칭으로 두고 계산)."""
    span = a1 - a0
    start = -span / 2.0
    pts = []
    n = max(48, int(math.degrees(span)))
    for i in range(n + 1):
        a = start + span * i / n
        pts.append((R1 * math.cos(a), R1 * math.sin(a)))
        pts.append((R2 * math.cos(a), R2 * math.sin(a)))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"blank_w": round(max(xs) - min(xs), 1), "blank_h": round(max(ys) - min(ys), 1)}


def _head_blank(ID: float, t: float, sf: float, head_type: str) -> Dict[str, Any]:
    k = HEAD_BLANK_FACTOR if "ellip" in head_type.lower() or "2:1" in head_type else (1.12 if "tori" in head_type.lower() else 1.57)
    D = k * ID + (sf - 50.0) * 2.0
    D = round(D / 10.0) * 10.0
    return {"type": "head", "blank_dia": D, "blank_w": D, "blank_h": D, "area": math.pi * D * D / 4.0, "shape": "circle",
            "formula": f"D_blank = {k} x ID + 2 x (SF-50) = {D:.0f}  (경험계수, 제작처 표준으로 확정 필요)"}


def _pad(OD: float, ID: float) -> Dict[str, Any]:
    return {"type": "pad_ring", "blank_w": OD, "blank_h": OD, "area": math.pi * (OD ** 2 - ID ** 2) / 4.0, "shape": "circle",
            "formula": f"ring OD {OD} / ID {ID}"}


@logged
def unfold_part(part_index: int) -> dict:
    """PartSpec 을 전개해 블랭크 치수·면적을 구한다 → state.flats[part_id]."""
    st = get_state()
    p = st.parts[part_index]
    t = p.thickness
    try:
        if p.part_type == "cylinder":
            courses = [c for c in (p.seams.get("courses") or []) if isinstance(c, (int, float)) and c > 0] or \
                      [c.get("length", 0) for c in (p.seams.get("courses") or []) if isinstance(c, dict) and c.get("length")]
            if not courses:
                courses = [p.length]
            if p.inner_dia <= 0 or not any(courses):
                return {"error": "inner_dia 또는 length/courses 가 비어 전개 불가", "part_id": p.part_id}
            flat = {"type": "cylinder", "courses": [_cyl(p.inner_dia, t, L) for L in courses],
                    "formula": _cyl(p.inner_dia, t, courses[0])["formula"]}
            flat["area"] = sum(c["area"] for c in flat["courses"])
        elif p.part_type == "cone_frustum":
            if p.large_inner_dia <= 0 or p.cone_height <= 0:
                return {"error": "large_inner_dia / cone_height 가 비어 전개 불가", "part_id": p.part_id}
            flat = _cone(p.large_inner_dia, p.small_inner_dia, p.cone_height, t)
        elif p.part_type == "head":
            if p.inner_dia <= 0:
                return {"error": "inner_dia 가 비어 블랭크 계산 불가", "part_id": p.part_id}
            flat = _head_blank(p.inner_dia, t, p.straight_flange, p.head_type)
        elif p.part_type == "pad_ring":
            if p.pad_od <= 0:
                return {"error": "pad_od 가 비어 있음 (resolve_missing_spec 또는 HITL)", "part_id": p.part_id}
            flat = _pad(p.pad_od, p.pad_id)
        elif p.part_type in ("bent_sheet", "flat") and TkPartModel is not None:
            m = TkPartModel(part_type=p.part_type, part_name=p.part_name, drawing_no="", material=p.material, thickness=t,
                            quantity=p.quantity, width=p.width, segments=p.segments, bend_angles=p.bend_angles,
                            bend_radii=p.bend_radii, outline=p.outline)
            fp = tk_unfold(m)
            if not fp.outline:
                return {"error": "; ".join(fp.warnings), "part_id": p.part_id}
            flat = {"type": p.part_type, "blank_w": round(fp.blank_w, 1), "blank_h": round(fp.blank_h, 1),
                    "area": _poly_area(fp.outline), "outline": fp.outline, "formula": fp.formula, "shape": "polygon",
                    "warnings": fp.warnings}
        else:
            return {"error": f"지원하지 않는 part_type: {p.part_type}", "part_id": p.part_id}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "part_id": p.part_id}
    flat["part_id"] = p.part_id
    st.flats[p.part_id] = flat
    return {k: v for k, v in flat.items() if k != "outline"}


def _poly_area(pts: List[List[float]]) -> float:
    s = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


# ----------------------------------------------------------------------------- 분할
@logged
def split_to_pieces(part_index: int, max_w: float = 0, max_l: float = 0, long_seams: int = 0, label_prefix: str = "") -> dict:
    """전개 블랭크를 판 폭/길이와 용접선 수에 맞춰 조각으로 나눈다 → state.pieces.
    max_w/max_l 0 이면 운반 상한(3050 x 12000). long_seams 0 이면 길이 초과분만큼 자동."""
    st = get_state()
    p = st.parts[part_index]
    flat = st.flats.get(p.part_id)
    if not flat:
        return {"error": "먼저 unfold_part 를 호출하라", "part_id": p.part_id}
    W = max_w or TRANSPORT_MAX[1]
    L = max_l or TRANSPORT_MAX[0]
    pref = label_prefix or p.part_name.upper().replace(" ", "")[:8]
    new: List[Piece] = []
    base = dict(part_id=p.part_id, material=p.material, thickness=p.thickness, qty=p.quantity)

    def add(label, w, h, shape, area, note=""):
        new.append(Piece(piece_id=f"{p.part_id}:{label}", label=label, w=round(w, 1), h=round(h, 1), shape=shape,
                         area=area, note=note, **base))

    if flat["type"] == "cylinder":
        for ci, c in enumerate(flat["courses"], 1):
            circ, H = c["blank_w"], c["blank_h"]
            n_long = long_seams or max(1, math.ceil(circ / L))
            n_circ = max(1, math.ceil(H / W))
            for j in range(n_long):
                for k in range(n_circ):
                    lab = f"{pref}-{ci:02d}" + (chr(97 + j) if n_long > 1 else "") + (f"/{k+1}" if n_circ > 1 else "")
                    add(lab, circ / n_long, H / n_circ, "rect", circ / n_long * H / n_circ, f"코스{ci} 롱심{n_long} 원주분할{n_circ}")
    elif flat["type"] == "cone_frustum":
        R1, R2, th = flat["R1"], flat["R2"], math.radians(flat["theta_deg"])
        n = 1
        while True:
            bb = _sector_bbox(R1, R2, 0, th / n)
            if (bb["blank_w"] <= L and bb["blank_h"] <= W) or n >= 8:
                break
            n += 1
        for j in range(n):
            bb = _sector_bbox(R1, R2, 0, th / n)
            add(f"{pref}" + (chr(97 + j) if n > 1 else ""), bb["blank_w"], bb["blank_h"], "sector", flat["area"] / n, f"부채꼴 {n}분할")
    elif flat["type"] in ("head", "pad_ring"):
        D = flat["blank_w"]
        if D <= W or flat["type"] == "pad_ring":
            add(pref, D, D, "circle", flat["area"])
        else:                                   # 현(弦) 2분할: 큰 조각 높이 = W - 30, 작은 조각 = D - 큰 조각
            h1 = W - 30.0
            h2 = D - h1
            off = h1 - D / 2.0
            add(f"{pref}-a", D, h1, "segment", _segment_area(D / 2, h1), f"현 분할, 중심 오프셋 {off:.0f}")
            add(f"{pref}-b", 2 * math.sqrt((D / 2) ** 2 - off ** 2), h2, "segment", _segment_area(D / 2, h2), "작은 조각")
    else:
        add(pref, flat["blank_w"], flat["blank_h"], flat.get("shape", "rect"), flat.get("area", flat["blank_w"] * flat["blank_h"]))
    st.pieces.extend(new)
    return {"part_id": p.part_id, "pieces": [{"label": x.label, "w": x.w, "h": x.h, "shape": x.shape, "qty": x.qty, "note": x.note} for x in new]}


def _segment_area(r: float, h: float) -> float:
    """반지름 r 원에서 높이 h 인 활꼴 면적."""
    h = min(max(h, 0.0), 2 * r)
    return r * r * math.acos((r - h) / r) - (r - h) * math.sqrt(2 * r * h - h * h)


# ----------------------------------------------------------------------------- 네스팅 (shelf, bbox 기반)
def _expand(pieces: List[Piece]) -> List[Tuple[str, float, float, bool, float]]:
    items = []
    for p in pieces:
        for k in range(p.qty):
            items.append((f"{p.piece_id}#{k+1}", p.w, p.h, p.rot_ok, p.area or p.w * p.h))
    items.sort(key=lambda x: (-max(x[1], x[2]), -x[1] * x[2]))
    return items


def _shelf_pack(items, W: float, L: float, kerf: float, edge: float):
    """길이 L 방향으로 선반(shelf)을 채우고 폭 W 방향으로 선반을 쌓는다. 반환 (배치, 남은 것, 사용 길이)."""
    shelves: List[Dict[str, float]] = []
    placed: List[Placement] = []
    left = []
    y_cur = edge
    used_x = 0.0
    for pid, w, h, rot_ok, area in items:
        orients = [(w, h)] + ([(h, w)] if rot_ok and abs(w - h) > 1e-6 else [])
        done = False
        for sh in shelves:                                    # 기존 선반
            for (pw, ph) in sorted(orients, key=lambda o: o[1]):
                x = sh["x"]
                if ph <= sh["h"] + 1e-6 and x + pw <= L - edge + 1e-6:
                    placed.append(Placement(piece_id=pid, x=round(x, 1), y=round(sh["y"], 1), w=pw, h=ph, rot=0 if (pw, ph) == (w, h) else 90))
                    sh["x"] = x + pw + kerf
                    used_x = max(used_x, x + pw)
                    done = True; break
            if done:
                break
        if done:
            continue
        for (pw, ph) in sorted(orients, key=lambda o: o[1]):   # 새 선반
            if y_cur + ph <= W - edge + 1e-6 and edge + pw <= L - edge + 1e-6:
                shelves.append({"y": y_cur, "h": ph, "x": edge + pw + kerf})
                placed.append(Placement(piece_id=pid, x=edge, y=round(y_cur, 1), w=pw, h=ph, rot=0 if (pw, ph) == (w, h) else 90))
                used_x = max(used_x, edge + pw)
                y_cur = y_cur + ph + kerf
                done = True; break
        if not done:
            left.append((pid, w, h, rot_ok, area))
    return placed, left, used_x


NEST_OBJECTIVE = "pieces"     # pieces | util | net | net_util. KD25038 smoke 비교: pieces 가 gross 최소(5,657kg vs 실제 5,486) → 기본값


def _sheet_key(objective: str, n_placed: int, util: float, net: float):
    return {"pieces": (n_placed, util), "util": (util, n_placed), "net": (net, util),
            "net_util": (net * util, n_placed)}.get(objective, (net * util, n_placed))


def _pack_group(items, widths: List[float], cut: str, allow_custom: bool, objective: str = "") -> List[Dict[str, Any]]:
    """그룹 전체를 판 단위로 greedy 배치. 판마다 (폭 후보 x 길이) 중 objective 가 최대인 것을 고른다."""
    objective = objective or NEST_OBJECTIVE
    kerf = KERF_MARGIN.get(cut, KERF_MARGIN[DEFAULT_CUT])
    sheets: List[Dict[str, Any]] = []
    remaining = list(items)
    guard = 0
    while remaining and guard < 200:
        guard += 1
        best = None
        for W in widths:
            if W > TRANSPORT_MAX[1]:
                continue
            # 길이 후보: 맞춤이어도 짧은 길이부터 시도해야 폭 방향 선반이 채워진다 (길이 한도만 주면 가늘고 긴 판이 나온다)
            lengths = sorted({l for l in STD_LENGTHS if l <= TRANSPORT_MAX[0]} | {TRANSPORT_MAX[0]})
            if len(remaining) > 400:                      # 큰 그룹은 후보를 줄여 시간 절약
                lengths = [l for l in lengths if l in (4000.0, 8000.0, TRANSPORT_MAX[0])] or lengths[-1:]
            for L in lengths:
                placed, left, used_x = _shelf_pack(remaining, W, L, kerf, EDGE_MARGIN)
                if not placed:
                    continue
                Lf = (math.ceil((used_x + EDGE_MARGIN) / LENGTH_SNAP) * LENGTH_SNAP) if allow_custom else L
                net = sum(a for (pid, w, h, r, a) in remaining if pid in {q.piece_id for q in placed})
                util = net / (W * Lf)
                key = _sheet_key(objective, len(placed), util, net)
                if best is None or key > best[0]:
                    best = (key, W, Lf, placed, left, net)
        if best is None:
            sheets.append({"error": "배치 불가 조각", "left": [x[0] for x in remaining]})
            break
        _, W, Lf, placed, left, net = best
        sheets.append({"w": W, "l": Lf, "placements": placed, "net_area": net, "custom": allow_custom})
        remaining = left
    return sheets


@logged
def nest_group(material: str, thickness: float, cut: str = "gas", widths: Optional[List[float]] = None,
               allow_custom: bool = True, objective: str = "") -> dict:
    """(재질, 두께) 그룹의 조각을 판에 배치한다. widths 는 판 폭 후보(기본 표준폭). allow_custom 이면 길이를 맞춤(10 단위).
    objective: net_util(기본) | util | net | pieces — 판마다 어떤 후보를 고를지."""
    st = get_state()
    grp = [p for p in st.pieces if p.material == material and abs(p.thickness - thickness) < 1e-6]
    if not grp:
        return {"error": f"그룹 ({material}, t{thickness}) 에 조각이 없다"}
    items = _expand(grp)
    if widths is None:
        # 표준폭 + 그룹의 가장 큰 조각에 맞춘 맞춤폭 후보 (사람 CP 는 1000, 850, 1070 같은 주문폭을 쓴다)
        kerf = KERF_MARGIN.get(cut, KERF_MARGIN[DEFAULT_CUT])
        _, bw, bh, _, _ = items[0]
        short, long_ = min(bw, bh), max(bw, bh)
        cand = {math.ceil((short * k + kerf * (k - 1)) / 10.0) * 10.0 for k in (1, 2, 3)} | {math.ceil(long_ / 10.0) * 10.0}
        widths = sorted(set(STD_WIDTHS) | {w for w in cand if 300 <= w <= TRANSPORT_MAX[1]})
    packed = _pack_group(items, widths, cut, allow_custom, objective)
    out = []
    for s in packed:
        if "error" in s:
            out.append(s); continue
        sid = len(st.sheets) + 1
        gross = thickness * s["w"] * s["l"] * DENSITY_STEEL
        sh = Sheet(sheet_id=sid, material=material, thickness=thickness, w=s["w"], l=s["l"], custom=s["custom"],
                   placements=s["placements"], utilization=round(s["net_area"] / (s["w"] * s["l"]), 3),
                   gross_kg=round(gross, 1), net_kg=round(s["net_area"] * thickness * DENSITY_STEEL, 1))
        st.sheets.append(sh)
        out.append({"sheet_id": sid, "size": f"t{thickness:g} x {s['w']:.0f} x {s['l']:.0f}", "n_pieces": len(s["placements"]),
                    "utilization": sh.utilization, "gross_kg": sh.gross_kg,
                    "pieces": [pl.piece_id.split(":")[-1] for pl in s["placements"]]})
    return {"material": material, "thickness": thickness, "n_items": len(items), "sheets": out}


@logged
def nest_all(cut: str = "gas", allow_custom: bool = True, objective: str = "") -> dict:
    """모든 (재질, 두께) 그룹을 네스팅한다 (기존 sheets 는 지운다)."""
    st = get_state()
    st.sheets = []
    groups = sorted({(p.material, p.thickness) for p in st.pieces})
    res = [nest_group(m, t, cut, None, allow_custom, objective) for (m, t) in groups]
    return {"groups": len(groups), "n_sheets": len(st.sheets),
            "total_gross_kg": round(sum(s.gross_kg for s in st.sheets), 1),
            "overall_utilization": round(sum(s.net_kg for s in st.sheets) / max(sum(s.gross_kg for s in st.sheets), 1e-9), 3),
            "detail": res}


# ----------------------------------------------------------------------------- 출력
@logged
def write_cutting_plan_dxf(path: str = "") -> dict:
    """state.sheets 를 커팅플랜 DXF 로 쓴다. 판 외곽 + 조각 bbox(원형은 원) + 라벨 'SA516-70 t10 x 2438 x 9150 - 1 SH'T'."""
    import ezdxf
    from ezdxf import units
    st = get_state()
    out = Path(path) if path else st.run_dir() / f"{st.job}_CP.dxf"
    doc = ezdxf.new("R2010", setup=True); doc.units = units.MM
    msp = doc.modelspace()
    for name, color in (("SHEET", 7), ("PART", 5), ("LABEL", 3), ("INFO", 1)):
        doc.layers.add(name, color=color)
    shapes = {p.piece_id: p for p in st.pieces}
    y0 = 0.0
    for sh in st.sheets:
        msp.add_lwpolyline([(0, y0), (sh.l, y0), (sh.l, y0 + sh.w), (0, y0 + sh.w)], close=True, dxfattribs={"layer": "SHEET"})
        for pl in sh.placements:
            base = shapes.get(pl.piece_id.split("#")[0])
            x, y = pl.x, y0 + pl.y
            if base and base.shape == "circle":
                msp.add_circle((x + pl.w / 2, y + pl.h / 2), pl.w / 2, dxfattribs={"layer": "PART"})
            else:
                msp.add_lwpolyline([(x, y), (x + pl.w, y), (x + pl.w, y + pl.h), (x, y + pl.h)], close=True, dxfattribs={"layer": "PART"})
            lab = (base.label if base else pl.piece_id)[:14]
            msp.add_text(lab, height=max(12.0, min(min(pl.w, pl.h) * 0.10, pl.w / max(len(lab), 1) * 1.3, 120.0)),
                         dxfattribs={"layer": "LABEL"}).set_placement((x + pl.w / 2, y + pl.h / 2), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        msp.add_text(f"{sh.material} t{sh.thickness:g} x {sh.w:.0f} x {sh.l:.0f} - {sh.qty} SH'T   util {sh.utilization:.0%}  {sh.gross_kg:.0f} kg",
                     height=60, dxfattribs={"layer": "INFO"}).set_placement((0, y0 - 90))
        y0 += sh.w + 400
    doc.saveas(str(out))
    return {"path": str(out), "n_sheets": len(st.sheets)}


@logged
def build_por() -> dict:
    """커팅플랜 판재를 POR PLATE 행으로 집계한다 (같은 재질·규격은 수량 합산) → state.por, runs/<job>/por.csv"""
    st = get_state()
    agg: Dict[Tuple[str, float, float, float], int] = {}
    for sh in st.sheets:
        key = (sh.material, sh.thickness, sh.w, sh.l)
        agg[key] = agg.get(key, 0) + sh.qty
    rows = []
    for i, ((mat, t, w, l), q) in enumerate(sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[0][2] * kv[0][3])), 1):
        kind = "STAINLESS PLATE" if mat.upper().startswith(("SA240", "A240", "SUS", "304", "316")) else "CARBON PLATE"
        kg = round(t * w * l * DENSITY_STEEL * q, 1)
        rows.append({"no": i, "part_name": kind, "spec": f"{t:g}t * {w:.0f} * {l:.0f}", "material": mat, "qty": q, "unit": "SH",
                     "weight_kg": kg, "remark": "재고확인" if w * l <= 1_000_000 else ""})
    st.por = rows
    p = st.run_dir() / "por.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["no"])
        wr.writeheader(); wr.writerows(rows)
    return {"rows": rows, "total_kg": round(sum(r["weight_kg"] for r in rows), 1), "csv": str(p)}
