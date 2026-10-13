# -*- coding: utf-8 -*-
"""
test_data 전체 실험 하네스. 도메인별로 task 를 나눈다.

  KDM (압력용기, 38 WO)
    E1_kdm_oracle   정답 커팅플랜의 조각(parts.csv bbox) → 우리 분할·네스팅 엔진 → 사람 커팅플랜과 비교.   API 불필요
    E3_kdm_vlm      입력 도면 → VLM(L1·L2) → 전개도 → 네스팅 → 비교.                                    API 필요
  HCE (판금, 1 WO)
    E2_hce_oracle   고객 전개 DXF 5종(21개) → 네스팅 → TruTops TAF(2438x1219 1장) 와 비교.               API 불필요
    E4_hce_vlm      스캔 PDF → VLM 절곡 파라미터 → 전개 → 고객 DXF 와 IoU → 네스팅.                       API 필요

출력 (runs/experiments/<exp>/<WO>/):
    unfold_catalog.dxf / .png     전개도(조각) 모음  — 중간 산출물
    cutting_plan.dxf / .png       우리 커팅플랜
    metrics.json                  판 수·gross 중량·활용률 비율 (커팅플랜 기준 metric)
    runs/experiments/summary.csv, REPORT.md

사용:  py -m cutplan_agent.eval.run_experiments [--only E1,E2] [--wo KD23002,...] [--skip-big]
"""
from __future__ import annotations
import argparse, csv, json, math, os, statistics, sys, time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cutplan_agent.config import DENSITY_STEEL, RUNS_DIR
from cutplan_agent.state import JobState, Piece, Trajectory, set_context
from cutplan_agent.skills import l3_rules as L3, l4_verify as L4
from cutplan_agent.skills.l1_perception import _render_dxf

TEST = Path(r"D:\노바투스2026\test_data")
EXP = RUNS_DIR / "experiments"
KERF_CUT = "plasma"          # 조각 간격 10mm (사람 CP 의 간격에 가까움). 가스 20 은 더 보수적
BIG_LIMIT = 1500             # 조각 수가 이보다 많으면 --skip-big 때 건너뜀


def have_credentials() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    cfg = Path(os.environ.get("APPDATA", "")) / "Anthropic" / "credentials"
    return cfg.exists() and any(cfg.glob("*.json"))


# ----------------------------------------------------------------------------- 공통
def read_csv(p: Path) -> List[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if p.exists() else []


def gt_sheets(wo_dir: Path, only_ok=True) -> List[dict]:
    rows = read_csv(wo_dir / "output_cutting_plan" / "sheets.csv")
    return [r for r in rows if (r.get("quality") == "ok" or not only_ok)]


def unfold_catalog(dxf_files: List[Path], out_dxf: Path, max_parts: int = 600, row_w: float = 24000.0) -> Tuple[int, int]:
    """전개도 DXF 들을 한 장에 격자 배치한 카탈로그 DXF (PNG 는 호출측에서 렌더)."""
    import ezdxf
    from ezdxf import bbox, units
    doc = ezdxf.new("R2010"); doc.units = units.MM
    msp = doc.modelspace()
    doc.layers.add("BLANK", color=7); doc.layers.add("INFO", color=5)
    x = y = 0.0; row_h = 0.0; n = 0
    gap = 150.0
    for f in dxf_files[:max_parts]:
        try:
            src = ezdxf.readfile(str(f))
        except Exception:
            continue
        ents = [e for e in src.modelspace() if e.dxftype() in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE")]
        if not ents:
            continue
        ex = bbox.extents(ents, fast=True)
        w, h = ex.size.x, ex.size.y
        if x + w > row_w and x > 0:
            x = 0.0; y += row_h + gap; row_h = 0.0
        for e in ents:
            c = e.copy(); c.translate(x - ex.extmin.x, y - ex.extmin.y, 0); c.dxf.layer = "BLANK"; msp.add_entity(c)
        msp.add_text(f.stem.split("_P")[-1][:18], height=max(min(min(w, h) * 0.08, 60.0), 15.0), dxfattribs={"layer": "INFO"}).set_placement((x, y - 70))
        x += w + gap; row_h = max(row_h, h); n += 1
    doc.saveas(str(out_dxf))
    return n, len(dxf_files)


def nest_pieces(job: str, pieces: List[dict], widths_by_group: Dict[Tuple[str, float], List[float]], transport: Tuple[float, float],
                out_dir: Path) -> dict:
    """pieces: [{label, material, t, w, h, qty}] → 우리 엔진으로 네스팅, DXF/PNG 저장, 결과 dict."""
    st = JobState(job=job, eval_mode=True); set_context(st, Trajectory(job))
    for i, p in enumerate(pieces):
        st.pieces.append(Piece(piece_id=f"{job}:{i}", part_id=f"{job}:{i}", label=str(p["label"])[:24], material=p["material"],
                               thickness=float(p["t"]), w=float(p["w"]), h=float(p["h"]), qty=int(p["qty"]), area=float(p["w"]) * float(p["h"])))
    old_tm, old_edge, old_tm4 = L3.TRANSPORT_MAX, L3.EDGE_MARGIN, L4.TRANSPORT_MAX
    L3.TRANSPORT_MAX = L4.TRANSPORT_MAX = transport      # 사람이 쓴 최대 판 크기까지 허용 (검증기도 같은 기준)
    L3.EDGE_MARGIN = 0.0            # 사람 CP 는 판을 부품 치수에 맞춰 주문하므로(폭 전체를 쓰는 쉘 판) 가장자리 여유 0 이 공정한 조건
    try:
        st.sheets = []
        groups = sorted({(p.material, p.thickness) for p in st.pieces})
        for (m, t) in groups:
            L3.nest_group(m, t, cut=KERF_CUT, widths=widths_by_group.get((m, t)), allow_custom=True)
        ver = L4.verify_nesting(KERF_CUT)
    finally:
        L3.TRANSPORT_MAX, L3.EDGE_MARGIN, L4.TRANSPORT_MAX = old_tm, old_edge, old_tm4
    out_dir.mkdir(parents=True, exist_ok=True)
    cp_dxf = out_dir / "cutting_plan.dxf"
    L3.write_cutting_plan_dxf(str(cp_dxf))
    try:
        _render_dxf(cp_dxf, out_dir / "cutting_plan.png", 2400)
    except Exception as e:
        print("   render fail:", e)
    gross = sum(s.gross_kg for s in st.sheets); net = sum(s.net_kg for s in st.sheets)
    by_group = {}
    for s in st.sheets:
        g = by_group.setdefault(f"{s.material}|t{s.thickness:g}", {"sheets": 0, "gross_kg": 0.0, "sizes": []})
        g["sheets"] += s.qty; g["gross_kg"] += s.gross_kg; g["sizes"].append(f"{s.w:.0f}x{s.l:.0f}")
    return {"n_sheets": len(st.sheets), "gross_kg": round(gross, 1), "net_kg": round(net, 1),
            "utilization": round(net / gross, 3) if gross else 0, "feasible": ver["ok"], "placed": ver["placed"],
            "by_group": by_group}


# ----------------------------------------------------------------------------- E1 KDM oracle
GT_UTIL_MIN, GT_UTIL_MAX = 0.15, 0.98     # bbox 활용률이 이 범위 밖인 정답 판재는 부품 누락/중복으로 보고 제외


def clean_sheet_parts(rows: List[dict], mat: str, t: float, q: int, sid: str) -> List[dict]:
    """parts.csv 의 노이즈 제거: 풍선 원, 15mm 미만, 완전 중복 행, 다른 부품 bbox 안에 완전히 들어가는 행(링의 안쪽 원 등)."""
    cand = []
    seen = set()
    for p in rows:
        pw, ph = float(p["part_w"]), float(p["part_h"])
        x, y = float(p.get("rel_x") or 0), float(p.get("rel_y") or 0)
        balloon = int(float(p.get("n_ents") or 0)) == 1 and abs(pw - ph) < 1.0 and pw <= 100 and int(float(p.get("holes") or 0)) == 0
        if pw < 15 or ph < 15 or balloon:
            continue
        key = (round(x, 1), round(y, 1), round(pw, 1), round(ph, 1))
        if key in seen:
            continue
        seen.add(key)
        cand.append({"label": (p["part_label"] or p["tag_name"] or sid)[:14], "material": mat, "t": t, "w": pw, "h": ph, "qty": q,
                     "_x": x, "_y": y})
    out = []
    for i, a in enumerate(cand):
        inside = any(j != i and b["w"] * b["h"] > a["w"] * a["h"] + 1 and
                     b["_x"] - 1 <= a["_x"] and b["_y"] - 1 <= a["_y"] and
                     a["_x"] + a["w"] <= b["_x"] + b["w"] + 1 and a["_y"] + a["h"] <= b["_y"] + b["h"] + 1
                     for j, b in enumerate(cand))
        if not inside:
            out.append({k: v for k, v in a.items() if not k.startswith("_")})
    return out


def e1_kdm(wo: str, skip_big: bool) -> dict:
    d = TEST / wo
    out = EXP / "E1_kdm_oracle" / wo
    sheets = {r["sheet_id"]: r for r in gt_sheets(d)}
    parts = [p for p in read_csv(d / "output_cutting_plan" / "parts.csv") if p["sheet_id"] in sheets]
    if not parts:
        return {"wo": wo, "exp": "E1", "status": "skip", "reason": "ok 판재 없음"}
    if skip_big and len(parts) > BIG_LIMIT:
        return {"wo": wo, "exp": "E1", "status": "skip", "reason": f"조각 {len(parts)} > {BIG_LIMIT} (--skip-big)"}
    t0 = time.time()
    pieces, widths, Lmax, Wmax = [], {}, 0.0, 0.0
    gt_gross = gt_area = gt_part_area = 0.0; gt_n = 0; excluded_sheets = 0
    for sid, s in sheets.items():
        mat = s["material"] or "재질없음"; t = float(s["thickness"]); q = int(float(s["sheet_qty"] or 1))
        W, H = float(s["sheet_w"]), float(s["sheet_h"])            # sheet_w = 폭, sheet_h = 길이 (라벨 "t x W x L")
        if W > H:
            W, H = H, W
        sheet_pieces = clean_sheet_parts([x for x in parts if x["sheet_id"] == sid], mat, t, q, sid)
        util = sum(x["w"] * x["h"] for x in sheet_pieces) / (W * H) if sheet_pieces else 0
        if not sheet_pieces or util < GT_UTIL_MIN or util > GT_UTIL_MAX:
            # 풍선만 잡힌 판재, 부품이 빠진 판재(활용률 너무 낮음), 중복·중첩으로 면적이 넘치는 판재는 정답이 깨진 것 → 양쪽 비교에서 제외
            excluded_sheets += q
            continue
        widths.setdefault((mat, t), set()).add(W)
        Lmax, Wmax = max(Lmax, H), max(Wmax, W)
        gt_n += q; gt_gross += t * W * H * q * DENSITY_STEEL; gt_area += W * H * q
        pieces += sheet_pieces
        gt_part_area += sum(x["w"] * x["h"] * q for x in sheet_pieces)
    if not pieces:
        return {"wo": wo, "exp": "E1", "status": "skip", "reason": "유효 조각 없음 (풍선만 검출)"}
    widths_by_group = {k: sorted(v) for k, v in widths.items()}
    transport = (max(Lmax, 12000.0), max(Wmax, 3050.0))
    res = nest_pieces(wo, pieces, widths_by_group, transport, out)
    # 전개도 카탈로그 (output_unfold 의 match=ok 조각)
    idx = read_csv(d / "output_unfold" / "index.csv")
    ok_files = [d / "output_unfold" / r["file"] for r in idx if r["match"] == "ok" and r["file"]]
    n_cat, n_all = unfold_catalog(ok_files, out / "unfold_catalog.dxf")
    try:
        _render_dxf(out / "unfold_catalog.dxf", out / "unfold_catalog.png", 2400)
    except Exception as e:
        print("   catalog render fail:", e)
    m = {"wo": wo, "exp": "E1", "status": "ok", "domain": "KDM", "n_pieces": sum(p["qty"] for p in pieces), "n_groups": len(widths_by_group),
         "gt_sheets": gt_n, "gt_gross_kg": round(gt_gross), "gt_util": round(gt_part_area / gt_area, 3) if gt_area else 0,
         "our_sheets": res["n_sheets"], "our_gross_kg": round(res["gross_kg"]), "our_util": res["utilization"],
         "sheets_ratio": round(res["n_sheets"] / gt_n, 3) if gt_n else None, "kg_ratio": round(res["gross_kg"] / gt_gross, 3) if gt_gross else None,
         "feasible": res["feasible"], "placed": res["placed"], "unfold_catalog_parts": n_cat, "unfold_ok_files": n_all,
         "excluded_sheets": excluded_sheets, "sec": round(time.time() - t0, 1), "by_group": res["by_group"]}
    (out / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf8")
    return m


# ----------------------------------------------------------------------------- E2 HCE oracle
def e2_hce() -> dict:
    wo = "HCE_76K3-40022"; d = TEST / wo; out = EXP / "E2_hce_oracle" / wo
    t0 = time.time()
    parts = read_csv(d / "output_cutting_plan" / "parts.csv")
    sheet = read_csv(d / "output_cutting_plan" / "sheets.csv")[0]
    t = float(sheet["thickness"]); W, H = float(sheet["sheet_w"]), float(sheet["sheet_h"])
    if W > H:
        W, H = H, W
    pieces = [{"label": p["part_label"], "material": sheet["material"], "t": t, "w": float(p["part_w"]), "h": float(p["part_h"]), "qty": 1} for p in parts]
    gt_part_area = sum(p["w"] * p["h"] for p in pieces)
    res = nest_pieces(wo, pieces, {(sheet["material"], t): [W]}, (max(H, 12000.0), 3050.0), out)
    # 전개도: 고객 제공 DXF 5종 → 개별 PNG + 카탈로그
    files = sorted(p for p in (d / "output_unfold").glob("*.dxf"))
    for f in files:
        try:
            _render_dxf(f, out / (f.stem.replace("／", "_") + ".png"), 1200)
        except Exception as e:
            print("   part render fail:", f.name, e)
    n_cat, _ = unfold_catalog(files, out / "unfold_catalog.dxf", row_w=2000)
    _render_dxf(out / "unfold_catalog.dxf", out / "unfold_catalog.png", 2000)
    m = {"wo": wo, "exp": "E2", "status": "ok", "domain": "HCE", "n_pieces": len(pieces), "n_groups": 1,
         "gt_sheets": 1, "gt_gross_kg": round(t * W * H * DENSITY_STEEL, 1), "gt_util": round(gt_part_area / (W * H), 3),
         "our_sheets": res["n_sheets"], "our_gross_kg": round(res["gross_kg"], 1), "our_util": res["utilization"],
         "sheets_ratio": res["n_sheets"], "kg_ratio": round(res["gross_kg"] / (t * W * H * DENSITY_STEEL), 3),
         "feasible": res["feasible"], "placed": res["placed"], "unfold_catalog_parts": n_cat, "unfold_ok_files": len(files),
         "sec": round(time.time() - t0, 1), "by_group": res["by_group"]}
    (out / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf8")
    return m


# ----------------------------------------------------------------------------- E3/E4 VLM (API)
def e34_vlm(wo: str, domain: str) -> dict:
    exp = "E3_kdm_vlm" if domain == "KDM" else "E4_hce_vlm"
    if not have_credentials():
        return {"wo": wo, "exp": exp[:2], "status": "blocked", "domain": domain,
                "reason": "ANTHROPIC_API_KEY / 프로필 없음 — 도면→VLM→전개도 경로 실행 불가"}
    from cutplan_agent.agent.orchestrator import run, job_inputs
    inputs = job_inputs(wo) if domain == "KDM" else [str(TEST / wo / "input_drawings" / "76K3-40022.pdf")]
    st = run(wo, inputs, eval_mode=True, max_steps=80)
    gt = st.verify.get("gt", {})
    return {"wo": wo, "exp": exp[:2], "status": "ok", "domain": domain, "parts": len(st.parts), "pieces": len(st.pieces),
            "our_sheets": len(st.sheets), "kg_ratio": gt.get("kg_ratio")}


# ----------------------------------------------------------------------------- 보고서
def collect_results(current: List[dict]) -> List[dict]:
    """이번 실행 결과 + 디스크의 모든 metrics.json 을 합친다 (워크오더별 최신값). skip/blocked 는 이번 실행 것만."""
    merged: Dict[Tuple[str, str], dict] = {}
    for mj in EXP.glob("E*/*/metrics.json"):
        try:
            m = json.loads(mj.read_text(encoding="utf8"))
            merged[(m["exp"], m["wo"])] = m
        except Exception:
            pass
    for r in current:
        if r.get("status") == "ok":
            merged[(r["exp"], r["wo"])] = r
    out = list(merged.values())
    done = {(r["exp"], r["wo"]) for r in out}
    out += [r for r in current if r.get("status") != "ok" and (r.get("exp"), r.get("wo")) not in done]
    return out


def write_report(results: List[dict], creds: bool):
    results = collect_results(results)
    EXP.mkdir(parents=True, exist_ok=True)
    fields = ["exp", "domain", "wo", "status", "reason", "n_pieces", "n_groups", "gt_sheets", "our_sheets", "sheets_ratio",
              "gt_gross_kg", "our_gross_kg", "kg_ratio", "gt_util", "our_util", "feasible", "placed", "unfold_catalog_parts", "sec"]
    with open(EXP / "summary.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(results)
    e1 = [r for r in results if r.get("exp") == "E1" and r.get("status") == "ok"]
    e2 = [r for r in results if r.get("exp") == "E2" and r.get("status") == "ok"]
    skipped = [r for r in results if r.get("status") in ("skip", "blocked")]

    def stat(key):
        v = [r[key] for r in e1 if r.get(key) is not None]
        return (statistics.median(v), statistics.mean(v), min(v), max(v)) if v else (0, 0, 0, 0)
    L = ["# 실험 보고 — test_data 전체 (" + time.strftime("%Y-%m-%d %H:%M") + ")", "",
         "## 과제 정의 (도메인별)", "",
         "| 도메인 | task | 입력 | 중간 산출(전개도) | 출력(커팅플랜) | metric |", "|---|---|---|---|---|---|",
         "| KDM 압력용기 | 도면 → 판재 부품 전개 → 네스팅 → POR | input_drawings (GA, body, nozzle …) | 쉘·콘·헤드·패드 전개 DXF+PNG | 판별 배치 DXF+PNG | 판 수 비율, gross kg 비율, 활용률, 겹침 0 |",
         "| HCE 판금 | 스캔 도면 → 절곡 전개 → 네스팅 | 76K3-40022.pdf 10p | 굽힘 전개 DXF+PNG (고객 DXF 와 IoU) | 2438x1219 1장 배치 | 판 수, 활용률 vs TruTops |", "",
         "## 무엇을 검증했고 무엇을 못 했나", "",
         "| 구성요소 | 실험 | 상태 | 근거 |", "|---|---|---|---|",
         f"| 네스팅·분할 엔진 (L3) | E1 (KDM {len(e1)} WO), E2 (HCE) | **검증함** | 정답 조각을 넣고 사람 커팅플랜과 판 수·중량 비교 |",
         "| 전개 공식 (원통 π(ID+t)) | 툴킷 역산 (KDM 태그 44건) | **검증함** (이전 세션) | 5mm 격자 잔차 중앙값 0.02mm |",
         "| 커팅플랜 DXF/PNG·POR 중량 | E1/E2 출력 + KD25038 smoke | **검증함** | 10x2438x9150 → 1,751kg 실제 POR 일치 |",
         f"| 도면 판독 (L1 VLM/OCR) | E3/E4 | {'실행됨' if creds else '**검증 불가 — API 키 없음**'} | 하네스 준비됨 (`run_eval.py`, `orchestrator.py`) |",
         f"| BOM→부품 유형·3D 파라미터 (L2) | E3/E4 | {'실행됨' if creds else '**검증 불가 — API 키 없음**'} | |",
         "| 분할선(용접선) 인식 (RQ1) | E3 | 검증 불가 | VLM 필요 + 정답 분할 라벨 없음 (parts.csv 는 결과 조각만) |",
         "| 헤드 블랭크 계수 1.25 | — | 부분 (2건 역산) | part_tags HEAD 14건 보정 필요 |",
         "| 패드 치수 추정 (2×노즐 OD) | — | 검증 불가 | 강도계산서(CAL) 대조 필요 |",
         "| 조각 분할 수 ↔ 판폭 공동 최적화 | — | 미구현 | KD25038: 폭 2438 이면 콘 4조각, 3048 이면 2조각 |", "",
         "## E1 KDM — 정답 조각 → 우리 네스팅 vs 사람 커팅플랜 (quality=ok 판재만)", ""]
    if e1:
        ms, mm, mn, mx = stat("kg_ratio"); ss, sm, sn, sx = stat("sheets_ratio")
        wins = sum(1 for r in e1 if r["kg_ratio"] is not None and r["kg_ratio"] <= 1.0)
        feas = sum(1 for r in e1 if r["feasible"])
        L += [f"- 워크오더 {len(e1)}개, 조각 {sum(r['n_pieces'] for r in e1):,}개, 재질·두께 그룹 {sum(r['n_groups'] for r in e1)}개",
              f"- gross 중량 비율(우리/사람): 중앙값 **{ms:.3f}**, 평균 {mm:.3f}, 최소 {mn:.3f}, 최대 {mx:.3f}. 사람 이하 {wins}/{len(e1)}",
              f"- 판 수 비율: 중앙값 **{ss:.3f}**, 평균 {sm:.3f}, 범위 {sn:.2f}~{sx:.2f}",
              f"- 활용률(bbox 기준) 사람 평균 {statistics.mean(r['gt_util'] for r in e1):.1%} vs 우리 {statistics.mean(r['our_util'] for r in e1):.1%}",
              f"- 겹침·여유 위반 없음: {feas}/{len(e1)}", "",
              "사람 커팅플랜의 bbox 활용률 구간별 (사람이 빽빽하게 짠 판일수록 bbox 선반 배치가 불리하다):", "",
              "| 사람 활용률 구간 | WO 수 | kg 비율 중앙값 | 판 수 비율 중앙값 |", "|---|---|---|---|"]
        for lo, hi, name in ((0, 0.4, "40% 미만"), (0.4, 0.7, "40~70%"), (0.7, 1.01, "70% 이상")):
            grp = [r for r in e1 if lo <= r["gt_util"] < hi and r["kg_ratio"] is not None]
            if grp:
                L.append(f"| {name} | {len(grp)} | {statistics.median(r['kg_ratio'] for r in grp):.3f} | {statistics.median(r['sheets_ratio'] for r in grp):.3f} |")
        L += ["",
              "| WO | 조각 | 그룹 | 판 사람→우리 | kg 사람→우리 | kg 비율 | 활용률 사람→우리 | 제외판 | 가능 | 초 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(e1, key=lambda x: x["kg_ratio"] or 9):
            L.append(f"| {r['wo']} | {r['n_pieces']} | {r['n_groups']} | {r['gt_sheets']}→{r['our_sheets']} | {r['gt_gross_kg']:,}→{r['our_gross_kg']:,} | "
                     f"{r['kg_ratio']:.3f} | {r['gt_util']:.0%}→{r['our_util']:.0%} | {r.get('excluded_sheets', 0)} | {'✓' if r['feasible'] else '✗ ' + r['placed']} | {r['sec']} |")
    L += ["", "## E2 HCE — 고객 전개 DXF 21개 → 네스팅 vs TruTops", ""]
    for r in e2:
        L += [f"- 조각 {r['n_pieces']}개, 사람 1장 2438x1219 ({r['gt_gross_kg']} kg, 활용률 {r['gt_util']:.0%}) → 우리 {r['our_sheets']}장 "
              f"{', '.join(r['by_group'][next(iter(r['by_group']))]['sizes'])} ({r['our_gross_kg']} kg, 활용률 {r['our_util']:.0%}), 겹침 {'없음' if r['feasible'] else '있음'}",
              "- 전개도: 고객 DXF 5종을 개별 PNG + 카탈로그 DXF/PNG 로 출력 (runs/experiments/E2_hce_oracle/)"]
    L += ["", "## 건너뛴 / 막힌 항목", ""] + [f"- {r['exp']} {r['wo']}: {r.get('reason','')}" for r in skipped]
    L += ["", "## 산출물", "", "- `runs/experiments/<exp>/<WO>/unfold_catalog.dxf|png` 전개도 모음, `cutting_plan.dxf|png` 우리 커팅플랜, `metrics.json`",
          "- `runs/experiments/summary.csv` 전체 표", "",
          "## 해석 시 주의", "",
          "- E1 은 **조각이 정답으로 주어진** 조건이다. 도면에서 조각을 뽑는 L1·L2 가 들어가면 오차가 더해진다.",
          "- 활용률은 bbox 면적 기준이라 원형·부채꼴은 실제보다 높게 잡힌다 (사람·우리 동일 기준).",
          "- 판폭은 사람이 쓴 폭을 후보로 주었다 (폭 선택 능력은 평가에서 제외). 길이는 10mm 단위 맞춤.",
          "- 조각 간격 10mm(플라즈마), 판 가장자리 여유 0 (사람 CP 는 판을 부품에 맞춰 주문). 사람 CP 의 실제 간격은 측정하지 않았다.",
          "- parts.csv 의 bbox 는 곡선 부품을 작게 잡는 경우가 있어(ARC 꼭짓점 근사) 그런 조각은 실제보다 작게 들어갔다.",
          f"- 정답 판재 필터: bbox 활용률 {GT_UTIL_MIN:.0%}~{GT_UTIL_MAX:.0%} 밖(부품 누락·중복)이거나 풍선만 잡힌 판재는 양쪽에서 제외 (각 WO 의 excluded_sheets).",
          "- 조각 bbox 는 사람이 회전시켜 놓은 상태의 bbox 라 비스듬한 부품은 실제보다 크다 → 우리 쪽에 불리한 편향."]
    (EXP / "REPORT.md").write_text("\n".join(L), encoding="utf8")
    print("report:", EXP / "REPORT.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="E1,E2,E3,E4")
    ap.add_argument("--wo", default="")
    ap.add_argument("--skip-big", action="store_true")
    a = ap.parse_args()
    only = set(a.only.split(","))
    idx = [r for r in read_csv(TEST / "index.csv") if r["included"] == "yes"]
    kdm = [r["workorder"] for r in idx if not r["workorder"].startswith("HCE")]
    if a.wo:
        kdm = [w for w in kdm if w in a.wo.split(",")]
    creds = have_credentials()
    print(f"credentials: {creds}   KDM WOs: {len(kdm)}")
    results = []
    if "E1" in only:
        for wo in kdm:
            r = e1_kdm(wo, a.skip_big); results.append(r)
            print(f"E1 {wo}: {r.get('status')} sheets {r.get('gt_sheets')}→{r.get('our_sheets')} kg_ratio={r.get('kg_ratio')} {r.get('reason','')} {r.get('sec','')}s", flush=True)
    if "E2" in only:
        r = e2_hce(); results.append(r)
        print(f"E2 HCE: sheets 1→{r['our_sheets']} util {r['gt_util']}→{r['our_util']} feasible={r['feasible']}", flush=True)
    if "E3" in only:
        for wo in (kdm[:3] if creds else kdm[:1]):
            results.append(e34_vlm(wo, "KDM"))
    if "E4" in only:
        results.append(e34_vlm("HCE_76K3-40022", "HCE"))
    write_report(results, creds)


if __name__ == "__main__":
    main()
