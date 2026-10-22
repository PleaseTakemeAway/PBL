# -*- coding: utf-8 -*-
"""
L4 검증·HITL — 저신뢰·모호 항목은 사람이 확정. verifier 는 Phase 2 RL 의 reward 원형.

  verify_part_spec        필수 필드·상식 범위 (ID vs OD, 후육, 콘 지름 순서)
  verify_weight_vs_bom    전개 면적 x t x 밀도 vs BOM 중량 (정답 없이 쓰는 self-check)
  verify_nesting          겹침·여유 위반·미배치·운반 상한
  compare_with_gt         dataset/gt/sheets.csv (사람 커팅플랜) 와 판 수·중량 비교 (개발용)
  ask_human               HITL 지점 H1~H4. eval_mode/policy=auto 면 기본값으로 자동 응답하고 기록
  confidence_report       저신뢰 항목 목록 (HITL 배치 결정 근거, RQ2)
"""

from __future__ import annotations

import csv
import sys
from typing import Dict, List, Optional

from cutplan_agent.config import (
    DATASET,
    DEFAULT_CUT,
    DENSITY_STEEL,
    KERF_MARGIN,
    TRANSPORT_MAX,
)
from cutplan_agent.state import HitlEvent, get_state, logged


@logged
def verify_part_spec(part_index: int) -> dict:
    st = get_state()
    p = st.parts[part_index]
    issues: List[str] = []
    req = {
        "cylinder": ["inner_dia", "length|courses"],
        "cone_frustum": ["large_inner_dia", "cone_height"],
        "head": ["inner_dia"],
        "pad_ring": ["pad_od", "pad_id"],
        "bent_sheet": ["width", "segments"],
        "flat": ["outline"],
    }
    for f in req.get(p.part_type, []):
        if f == "length|courses":
            if p.length <= 0 and not p.seams.get("courses"):
                issues.append("length 와 courses 가 모두 비어 있음")
        else:
            v = getattr(p, f)
            if (isinstance(v, (int, float)) and v <= 0) or (
                isinstance(v, list) and not v
            ):
                issues.append(f"{f} 비어 있음")
    if p.thickness <= 0:
        issues.append("thickness 0")
    if (
        p.part_type == "cylinder"
        and p.inner_dia > 0
        and p.thickness > 0
        and p.inner_dia / p.thickness < 20
    ):
        issues.append(
            f"ID/t={p.inner_dia / p.thickness:.1f} 후육 — OD 를 ID 로 넣었는지 확인"
        )
    if p.part_type == "cone_frustum" and p.small_inner_dia >= p.large_inner_dia > 0:
        issues.append("작은 지름이 큰 지름 이상")
    if p.part_type == "pad_ring" and p.pad_id >= p.pad_od > 0:
        issues.append("패드 ID >= OD")
    ok = not issues
    st.verify.setdefault("part_spec", {})[p.part_id] = {
        "ok": ok,
        "issues": issues,
        "confidence": p.confidence,
    }
    return {
        "part_id": p.part_id,
        "ok": ok,
        "issues": issues,
        "confidence": p.confidence,
    }


@logged
def verify_weight_vs_bom(
    part_index: int, bom_weight_kg: Optional[float] = None, tol: float = 0.08
) -> dict:
    """전개 면적으로 계산한 중량과 BOM 중량을 비교한다 (정답 없이 쓰는 self-verification)."""
    st = get_state()
    p = st.parts[part_index]
    flat = st.flats.get(p.part_id)
    if not flat:
        return {"error": "전개 결과 없음 (unfold_part 먼저)"}
    if bom_weight_kg is None:
        cand = [
            b.weight_kg
            for b in st.bom
            if b.weight_kg and b.part_name.upper() == p.part_name.upper()
        ]
        bom_weight_kg = cand[0] if cand else None
    calc = flat["area"] * p.thickness * DENSITY_STEEL
    if not bom_weight_kg:
        return {
            "part_id": p.part_id,
            "calc_kg": round(calc, 1),
            "bom_kg": None,
            "ok": None,
            "note": "BOM 중량 없음",
        }
    err = abs(calc - bom_weight_kg) / bom_weight_kg
    ok = err <= tol
    st.verify.setdefault("weight", {})[p.part_id] = {
        "calc": calc,
        "bom": bom_weight_kg,
        "err": err,
        "ok": ok,
    }
    return {
        "part_id": p.part_id,
        "calc_kg": round(calc, 1),
        "bom_kg": bom_weight_kg,
        "rel_err": round(err, 3),
        "ok": ok,
    }


@logged
def verify_nesting(cut: str = "gas") -> dict:
    """겹침, 커팅여유 위반, 운반 상한, 미배치를 검사한다."""
    st = get_state()
    kerf = KERF_MARGIN.get(cut, KERF_MARGIN[DEFAULT_CUT])
    overlaps, gaps, oversize = [], [], []
    placed_ids = set()
    for sh in st.sheets:
        if sh.l > TRANSPORT_MAX[0] + 1e-6 or sh.w > TRANSPORT_MAX[1] + 1e-6:
            oversize.append(sh.sheet_id)
        P = sh.placements
        for i in range(len(P)):
            placed_ids.add(P[i].piece_id.split("#")[0])
            a = P[i]
            for j in range(i + 1, len(P)):
                b = P[j]
                dx = max(b.x - (a.x + a.w), a.x - (b.x + b.w))
                dy = max(b.y - (a.y + a.h), a.y - (b.y + b.h))
                if dx < 0 and dy < 0:
                    overlaps.append((sh.sheet_id, a.piece_id, b.piece_id))
                elif max(dx, dy) < kerf - 0.5:  # 좌표 반올림(0.1mm) 여유
                    gaps.append(
                        (sh.sheet_id, a.piece_id, b.piece_id, round(max(dx, dy), 1))
                    )
    expected = sum(p.qty for p in st.pieces)
    n_placed = sum(len(s.placements) for s in st.sheets)
    unplaced = [p.piece_id for p in st.pieces if p.piece_id not in placed_ids]
    res = {
        "ok": not overlaps and not gaps and not oversize and n_placed == expected,
        "placed": f"{n_placed}/{expected}",
        "overlaps": overlaps[:10],
        "gap_violations": gaps[:10],
        "oversize_sheets": oversize,
        "unplaced": unplaced[:10],
    }
    st.verify["nesting"] = res
    return res


@logged
def compare_with_gt(job: str = "") -> dict:
    """dataset/KDM/<year>/<job>/gt/sheets.csv (사람 커팅플랜) 와 비교. 개발·평가용 — 운영에서는 쓰지 않는다."""
    st = get_state()
    job = job or st.job
    year = "20" + job[2:4]
    p = DATASET / "KDM" / year / job / "gt" / "sheets.csv"
    if not p.exists():
        return {"error": f"GT 없음: {p}"}
    gt = list(csv.DictReader(open(p, encoding="utf-8-sig")))

    def agg(rows, mat_k, t_k, w_k, h_k, q_k):
        out: Dict[str, Dict[str, float]] = {}
        for r in rows:
            key = f"{r[mat_k]}|t{float(r[t_k]):g}"
            q = int(float(r[q_k] or 1))
            d = out.setdefault(key, {"sheets": 0, "area_m2": 0.0, "kg": 0.0})
            d["sheets"] += q
            d["area_m2"] += float(r[w_k]) * float(r[h_k]) * q / 1e6
            d["kg"] += float(r[t_k]) * float(r[w_k]) * float(r[h_k]) * q * DENSITY_STEEL
        return out

    g = agg(gt, "material", "thickness", "sheet_w", "sheet_h", "sheet_qty")
    ours = agg(
        [
            {
                "material": s.material,
                "thickness": s.thickness,
                "sheet_w": s.w,
                "sheet_h": s.l,
                "sheet_qty": s.qty,
            }
            for s in st.sheets
        ],
        "material",
        "thickness",
        "sheet_w",
        "sheet_h",
        "sheet_qty",
    )
    keys = sorted(set(g) | set(ours))
    rows = [
        {
            "group": k,
            "gt_sheets": g.get(k, {}).get("sheets", 0),
            "our_sheets": ours.get(k, {}).get("sheets", 0),
            "gt_kg": round(g.get(k, {}).get("kg", 0), 0),
            "our_kg": round(ours.get(k, {}).get("kg", 0), 0),
        }
        for k in keys
    ]
    tot_gt = sum(r["gt_kg"] for r in rows)
    tot_us = sum(r["our_kg"] for r in rows)
    res = {
        "job": job,
        "groups": rows,
        "gt_total_kg": tot_gt,
        "our_total_kg": tot_us,
        "kg_ratio": round(tot_us / tot_gt, 3) if tot_gt else None,
    }
    st.verify["gt"] = res
    return res


@logged
def ask_human(
    point: str, question: str, options: Optional[List[str]] = None, default: str = ""
) -> dict:
    """HITL. point: H1(전개 직전) H2(자재목록 후) H3(네스팅 후) H4(구매의뢰 전).
    policy 가 'auto' 이거나 eval_mode 면 default(없으면 첫 option)로 자동 응답하고 기록만 남긴다."""
    st = get_state()
    options = options or []
    ev = HitlEvent(
        point=point, question=question, options=options, step=len(st.hitl) + 1
    )
    policy = st.hitl_policy.get(point, "ask")
    if st.eval_mode or policy == "auto":
        ev.answer, ev.auto = (default or (options[0] if options else "")), True
    elif policy == "ask" and sys.stdin.isatty():
        print(f"\n[HITL {point}] {question}")
        for i, o in enumerate(options, 1):
            print(f"  {i}. {o}")
        a = input(f"답 (기본 '{default}'): ").strip()
        if a.isdigit() and 1 <= int(a) <= len(options):
            a = options[int(a) - 1]
        ev.answer = a or default
    else:
        ev.answer = None  # 비대화형: pending 으로 남김
    st.hitl.append(ev)
    return {
        "point": point,
        "answer": ev.answer,
        "auto": ev.auto,
        "status": "answered" if ev.answer is not None else "pending",
    }


@logged
def confidence_report() -> dict:
    """저신뢰 항목 요약. 어느 H 지점에 사람을 둘지 결정하는 근거."""
    st = get_state()
    low_bom = [
        {"item": b.item_no, "name": b.part_name, "why": b.notes}
        for b in st.bom
        if b.is_plate and (b.thickness is None or b.confidence != "high")
    ]
    low_parts = [
        {
            "part_id": p.part_id,
            "type": p.part_type,
            "confidence": p.confidence,
            "notes": p.notes[-2:],
        }
        for p in st.parts
        if p.confidence in ("estimated", "unreadable", "medium")
    ]
    unresolved = [k for k, v in st.verify.get("part_spec", {}).items() if not v["ok"]]
    return {
        "low_confidence_bom": low_bom,
        "low_confidence_parts": low_parts,
        "failed_spec_checks": unresolved,
        "hitl_pending": [e.model_dump() for e in st.hitl if e.answer is None],
        "suggest": (
            "H1 전개 직전에 사람 확인"
            if low_parts or unresolved
            else "H4 최종 검증만으로 충분"
        ),
    }
