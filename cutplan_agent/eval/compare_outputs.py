# -*- coding: utf-8 -*-
"""
우리 결과(runs/<run>) 를 정답 파일(test_data/<job>/output_unfold, output_cutting_plan) 과 나란히 비교.

    uv run python -m cutplan_agent.eval.compare_outputs --job KD23002 --run runs/KD23002_vlm
    uv run python -m cutplan_agent.eval.compare_outputs --job KD23002 --run runs/KD23002_manual

출력 (runs/<run>/compare/):
  cp_compare.md / cp_compare.csv   (재질, 두께) 그룹별 판 규격·수량·중량  사람 vs 우리, 총계·비율
  cp_compare.png                   사람 커팅플랜 도면(PNG) 위, 우리 커팅플랜 아래
  unfold_compare.md / .csv         설계자 커팅 태그(part_tags) ↔ 우리 부품 매칭: 치수 오차 %, 수량
  unfold_compare.png               매칭된 부품의 정답 외곽(커팅플랜에서 잘라낸 DXF) vs 우리 전개 블랭크, 나란히
  unfold/*.dxf                     state.json 의 전개 결과를 부품별 DXF 로 (없을 때 생성)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

from cutplan_agent.config import (
    DENSITY_STEEL,
    HANGUL_FONT_FAMILIES,
    HANGUL_FONT_FILE,
    TEST_DATA,
)
from cutplan_agent.state import JobState, PartSpec


# ----------------------------------------------------------------------------- 공통
def read_csv(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if p.exists() else []


def norm_mat(m: str) -> str:
    m = (m or "").upper().replace(" ", "")
    m = re.sub(r"^A(\d{3})", r"SA\1", m)
    return m


def parse_size(s: str):
    """태그 SIZE → (w, h, kind). '2800x2949' / '⌀1296' / '⌀168x⌀300' / '695x930xR465' / '420x3050'"""
    s = (s or "").replace("⌀", "Ø").replace("Φ", "Ø").replace(" ", "")
    m = re.match(r"^Ø([\d.]+)xØ([\d.]+)$", s)
    if m:
        return float(m.group(2)), float(m.group(2)), f"ring ID{m.group(1)}"
    m = re.match(r"^Ø([\d.]+)$", s)
    if m:
        return float(m.group(1)), float(m.group(1)), "circle"
    m = re.match(r"^([\d.]+)x([\d.]+)(?:xR([\d.]+))?$", s)
    if m:
        return (
            float(m.group(1)),
            float(m.group(2)),
            "rect" if not m.group(3) else f"segment R{m.group(3)}",
        )
    return None


def our_blank(p: PartSpec, flat: dict):
    """우리 부품의 블랭크 (w, h, shape, per_qty) — cylinder 는 코스별."""
    t = flat.get("type")
    if t == "cylinder":
        c = flat["courses"][0]
        return c["blank_w"], c["blank_h"], "rect", p.quantity * len(flat["courses"])
    if t in ("head", "pad_ring"):
        return (
            flat["blank_w"],
            flat["blank_h"],
            ("circle" if t == "head" else f"ring ID{p.pad_id:g}"),
            p.quantity,
        )
    if t == "cone_frustum":
        return flat["blank_w"], flat["blank_h"], "sector", p.quantity
    return (
        flat.get("blank_w", 0),
        flat.get("blank_h", 0),
        flat.get("shape", "rect"),
        p.quantity,
    )


TOKENS = {
    "PL": "PLATE",
    "PLATE": "PLATE",
    "PART": "PARTITION",
    "PARTITION": "PARTITION",
    "SUPT": "SUPPORT",
    "SUPPORT": "SUPPORT",
    "IMP.": "IMPINGEMENT",
    "IMPINGEMENT": "IMPINGEMENT",
    "SLDING": "SLIDING",
    "SLIDING": "SLIDING",
    "DOWER": "DOWEL",
    "DOWEL": "DOWEL",
    "L/SHELL": "LARGE SHELL",
    "LARGE": "LARGE",
    "SHELL": "SHELL",
    "HEAD": "HEAD",
    "CHANNEL": "CHANNEL",
    "BAFFLE": "BAFFLE",
    "SEAL": "SEALING",
    "SEALING": "SEALING",
    "STRIP": "STRIP",
    "SHOE": "SHOE",
    "LUG": "LUG",
    "LIFTING": "LIFTING",
    "PUSH": "PUSH",
    "PAD": "PAD",
    "SADDLE": "SADDLE",
    "REINF": "PAD",
    "REINF.": "PAD",
    "BASE": "BASE",
    "WEB": "WEB",
    "RIB": "RIB",
    "FLOATING": "FLOATING",
    "TEST": "TEST",
    "RING": "RING",
    "CLIP": "CLIP",
    "BRACKET": "BRACKET",
    "NAME": "NAME",
}


def tokens(name: str) -> set:
    out = set()
    for w in re.split(r"[\s,/\-()]+", (name or "").upper()):
        w = w.strip(".")
        if not w:
            continue
        out.add(TOKENS.get(w, TOKENS.get(w + ".", w)))
    # 노즐 마크 S1,S2,T1 ... → NOZ
    if re.search(r"\b[ST]\d\b", name.upper()):
        out.add("NOZ")
    return out - {"PLATE", "PL", "", "1", "2", "3", "4"}


def match_parts(gt_tags, parts, flats):
    """태그 하나에 우리 부품 하나 (재질·두께 일치 + 이름 토큰 유사 + 치수 근접)."""
    rows, used = [], set()
    for g in gt_tags:
        gsz = parse_size(g["size"])
        gm, gt_t = norm_mat(g["material"]), float(g["thickness"] or 0)
        gtok = tokens(g["part_name"])
        best = None
        for i, p in enumerate(parts):
            if i in used or p.part_id not in flats:
                continue
            same_mat = norm_mat(p.material) == gm or (
                g["dwg_no"] == g["part_name"]
            )  # HCE 는 재질 표기(SS400 vs St37)가 달라 무시
            if not same_mat or abs(p.thickness - gt_t) > 0.6:
                continue
            w, h, shape, q = our_blank(p, flats[p.part_id])
            sim = len(gtok & tokens(p.part_name)) / max(
                len(gtok | tokens(p.part_name)), 1
            )
            derr = 9
            if gsz:
                a = sorted([gsz[0], gsz[1]])
                b = sorted([w, h])
                derr = (
                    abs(a[0] - b[0]) / max(a[0], 1) + abs(a[1] - b[1]) / max(a[1], 1)
                ) / 2
            score = sim * 2 - min(derr, 1)
            if best is None or score > best[0]:
                best = (score, i, w, h, shape, q, derr, sim)
        if best and (best[7] > 0 or best[6] < 0.15):
            _, i, w, h, shape, q, derr, sim = best
            used.add(i)
            rows.append(
                {
                    "gt_dwg_no": g["dwg_no"],
                    "gt_name": g["part_name"],
                    "material": g["material"],
                    "t": g["thickness"],
                    "gt_size": g["size"],
                    "gt_qty": g["qty"],
                    "our_name": parts[i].part_name,
                    "our_size": f"{w:g} x {h:g}"
                    if shape not in ("circle",)
                    else f"Ø{w:g}",
                    "our_shape": shape,
                    "our_qty": q,
                    "dim_err_pct": round(derr * 100, 1) if gsz else "",
                    "qty_match": int(g["qty"] or 0) == q,
                    "confidence": parts[i].confidence,
                    "our_part_id": parts[i].part_id,
                }
            )
        else:
            rows.append(
                {
                    "gt_dwg_no": g["dwg_no"],
                    "gt_name": g["part_name"],
                    "material": g["material"],
                    "t": g["thickness"],
                    "gt_size": g["size"],
                    "gt_qty": g["qty"],
                    "our_name": "",
                    "our_size": "",
                    "our_shape": "",
                    "our_qty": "",
                    "dim_err_pct": "",
                    "qty_match": "",
                    "confidence": "",
                    "our_part_id": "",
                }
            )
    extra = [p for i, p in enumerate(parts) if i not in used and p.part_id in flats]
    return rows, extra


def hce_tags(gt: Path):
    """HCE 샘플: 고객 제공 전개 DXF(bbox) + parts.csv(수량) + sheets.csv(재질·두께) 로 태그를 만든다."""
    import ezdxf
    from ezdxf import bbox

    sheet = read_csv(gt / "output_cutting_plan" / "sheets.csv")[0]
    parts = read_csv(gt / "output_cutting_plan" / "parts.csv")
    qty = {}
    for p in parts:
        qty[p["part_label"]] = qty.get(p["part_label"], 0) + 1
    out = []
    for f in sorted((gt / "output_unfold").glob("*.dxf")):
        name = f.stem.split("／")[0]
        doc = ezdxf.readfile(str(f))
        ents = [
            e
            for e in doc.modelspace()
            if e.dxftype() in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE")
        ]
        ex = bbox.extents(ents, fast=False)
        out.append(
            {
                "dwg_no": name,
                "part_name": name,
                "material": sheet["material"],
                "thickness": sheet["thickness"],
                "size": f"{ex.size.x:.1f}x{ex.size.y:.1f}",
                "qty": str(qty.get(name, 1)),
                "_file": str(f),
            }
        )
    return out


# ----------------------------------------------------------------------------- 그림
def draw_outline(
    ax,
    kind,
    w,
    h,
    outline=None,
    R1=None,
    R2=None,
    theta=None,
    pad_id=0,
    color="#1f5f8b",
):
    import matplotlib.patches as mp

    if kind == "circle":
        ax.add_patch(mp.Circle((w / 2, h / 2), w / 2, fill=False, lw=1.6, ec=color))
        if pad_id:
            ax.add_patch(
                mp.Circle((w / 2, h / 2), pad_id / 2, fill=False, lw=1.2, ec=color)
            )
    elif kind == "sector" and R1:
        th = math.radians(theta)
        a0 = -th / 2
        import numpy as np

        a = np.linspace(a0, a0 + th, 60)
        xs = list(R1 * np.cos(a)) + list(R2 * np.cos(a[::-1]))
        ys = list(R1 * np.sin(a)) + list(R2 * np.sin(a[::-1]))
        ax.plot(xs + [xs[0]], ys + [ys[0]], lw=1.6, color=color)
    elif outline:
        xs = [p[0] for p in outline] + [outline[0][0]]
        ys = [p[1] for p in outline] + [outline[0][1]]
        ax.plot(xs, ys, lw=1.6, color=color)
    else:
        ax.add_patch(mp.Rectangle((0, 0), w, h, fill=False, lw=1.6, ec=color))


def draw_dxf(ax, path: Path, color="#b85042"):
    import ezdxf
    from ezdxf import bbox

    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    ents = [
        e
        for e in msp
        if e.dxftype()
        in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE")
    ]
    ex = bbox.extents(ents, fast=True)
    ox, oy = (ex.extmin.x, ex.extmin.y) if ex.has_data else (0, 0)
    import numpy as np

    for e in ents:
        t = e.dxftype()
        if t == "LINE":
            ax.plot(
                [e.dxf.start.x - ox, e.dxf.end.x - ox],
                [e.dxf.start.y - oy, e.dxf.end.y - oy],
                lw=1.2,
                color=color,
            )
        elif t == "CIRCLE":
            a = np.linspace(0, 2 * math.pi, 80)
            ax.plot(
                e.dxf.center.x - ox + e.dxf.radius * np.cos(a),
                e.dxf.center.y - oy + e.dxf.radius * np.sin(a),
                lw=1.2,
                color=color,
            )
        elif t == "ARC":
            s, en = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
            if en < s:
                en += 2 * math.pi
            a = np.linspace(s, en, 60)
            ax.plot(
                e.dxf.center.x - ox + e.dxf.radius * np.cos(a),
                e.dxf.center.y - oy + e.dxf.radius * np.sin(a),
                lw=1.2,
                color=color,
            )
        elif t == "LWPOLYLINE":
            pts = [(p[0] - ox, p[1] - oy) for p in e.get_points()]
            if e.closed and pts:
                pts.append(pts[0])
            ax.plot([p[0] for p in pts], [p[1] for p in pts], lw=1.2, color=color)
    return (ex.size.x, ex.size.y) if ex.has_data else (0, 0)


def unfold_compare_png(rows, parts, flats, gt_dir: Path, out: Path, max_n: int = 12):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = (
        HANGUL_FONT_FAMILIES  # 한글 글리프 (그림 만들기 전에 설정)
    )
    plt.rcParams["axes.unicode_minus"] = False
    idx = read_csv(gt_dir / "index.csv")
    pid = {p.part_id: p for p in parts}
    cand = [r for r in rows if r["our_part_id"]]
    cand.sort(
        key=lambda r: (
            -(
                parse_size(r["gt_size"])[0] * parse_size(r["gt_size"])[1]
                if parse_size(r["gt_size"])
                else 0
            )
        )
    )
    cand = cand[:max_n]
    if not cand:
        return 0
    n = len(cand)
    fig, axes = plt.subplots(n, 2, figsize=(11, 3.2 * n))
    if n == 1:
        axes = [axes]
    for k, r in enumerate(cand):
        axg, axo = axes[k]
        # 정답 외곽: index.csv 에서 tag_name 이 같은 crop (match=ok 우선), 없으면 치수가 같은 crop
        gsz = parse_size(r["gt_size"])
        crop = None
        if not idx:  # HCE: index.csv 없음 → 고객 DXF 파일을 직접
            cand_f = sorted(gt_dir.glob(f"{r['gt_name']}*.dxf"))
            if cand_f:
                crop = {"file": cand_f[0].name, "match": "customer"}
        for x in sorted(idx, key=lambda x: x["match"] != "ok"):
            if not x["file"]:
                continue
            if (x.get("tag_name") or "").strip().upper()[:6] == r[
                "gt_name"
            ].strip().upper()[:6] and x["match"] == "ok":
                crop = x
                break
        if crop is None and gsz:
            for x in sorted(idx, key=lambda x: x["match"] != "ok"):
                if not x["file"]:
                    continue
                a = sorted([float(x["w"]), float(x["h"])])
                b = sorted([gsz[0], gsz[1]])
                if abs(a[0] - b[0]) < 3 and abs(a[1] - b[1]) < 3:
                    crop = x
                    break
        if crop:
            w, h = draw_dxf(axg, gt_dir / crop["file"])
            axg.set_title(
                f"정답: {r['gt_name']}  태그 {r['gt_size']} ×{r['gt_qty']}  (crop {w:.0f}×{h:.0f}, {crop['match']})",
                fontsize=9,
            )
        else:
            axg.set_title(
                f"정답: {r['gt_name']}  태그 {r['gt_size']} ×{r['gt_qty']}  (외곽 crop 없음)",
                fontsize=9,
            )
            if gsz:
                draw_outline(
                    axg,
                    gsz[2] if gsz[2] in ("circle",) else "rect",
                    gsz[0],
                    gsz[1],
                    color="#b85042",
                )
        p = pid[r["our_part_id"]]
        f = flats[p.part_id]
        w, h, shape, q = our_blank(p, f)
        kind = (
            "circle"
            if shape == "circle" or shape.startswith("ring")
            else ("sector" if shape == "sector" else "poly")
        )
        draw_outline(
            axo,
            kind,
            w,
            h,
            outline=f.get("outline"),
            R1=f.get("R1"),
            R2=f.get("R2"),
            theta=f.get("theta_deg"),
            pad_id=p.pad_id if shape.startswith("ring") else 0,
        )
        axo.set_title(
            f"우리: {p.part_name}  {r['our_size']} ×{q}  오차 {r['dim_err_pct']}%  ({p.confidence})",
            fontsize=9,
        )
        for ax in (axg, axo):
            ax.set_aspect("equal")
            ax.autoscale()
            ax.margins(0.08)
            ax.tick_params(labelsize=7)
    plt.rcParams["font.family"] = HANGUL_FONT_FAMILIES
    for ax_row in axes:
        for ax in ax_row:
            for t in ax.get_xticklabels() + ax.get_yticklabels():
                t.set_fontsize(7)
    fig.suptitle(
        "전개도 비교 — 왼쪽 정답(커팅플랜에서 잘라낸 외곽), 오른쪽 우리 전개 블랭크",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(str(out), dpi=110)
    plt.close(fig)
    return n


def cp_compare_png(gt_png: Path, our_png: Path, out: Path):
    from PIL import Image, ImageDraw, ImageFont

    a = Image.open(gt_png).convert("RGB")
    b = Image.open(our_png).convert("RGB")
    W = 1600
    a = a.resize((W, int(a.height * W / a.width)))
    b = b.resize((W, int(b.height * W / b.width)))
    H = a.height + b.height + 90
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(HANGUL_FONT_FILE, 26)
    except Exception:
        font = ImageFont.load_default()
    d.text(
        (20, 10),
        "사람 커팅플랜 (정답, test_data/output_cutting_plan)",
        fill="#b85042",
        font=font,
    )
    im.paste(a, (0, 45))
    d.text(
        (20, 45 + a.height + 5),
        "우리 커팅플랜 (runs/.../*_CP.png)",
        fill="#1f5f8b",
        font=font,
    )
    im.paste(b, (0, 45 + a.height + 45))
    im.save(str(out))


# ----------------------------------------------------------------------------- 메인
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run = Path(a.run)
    gt = TEST_DATA / a.job
    out = run / "compare"
    out.mkdir(parents=True, exist_ok=True)
    st = JobState.model_validate_json((run / "state.json").read_text(encoding="utf8"))
    parts, flats = st.parts, st.flats

    # ---- 커팅플랜 비교 ----
    gt_sheets = read_csv(gt / "output_cutting_plan" / "sheets.csv")
    g = {}
    for s in gt_sheets:
        k = f"{norm_mat(s['material'])}|t{float(s['thickness']):g}"
        q = int(float(s["sheet_qty"] or 1))
        W, H = float(s["sheet_w"]), float(s["sheet_h"])
        t = float(s["thickness"])
        d = g.setdefault(k, {"sheets": 0, "kg": 0.0, "sizes": [], "ok": 0})
        d["sheets"] += q
        d["kg"] += t * W * H * q * DENSITY_STEEL
        d["sizes"].append(
            f"{min(W, H):.0f}x{max(W, H):.0f}x{q}"
            + ("" if s["quality"] == "ok" else f"({s['quality']})")
        )
        d["ok"] += q if s["quality"] == "ok" else 0
    o = {}
    for s in st.sheets:
        k = f"{norm_mat(s.material)}|t{s.thickness:g}"
        d = o.setdefault(k, {"sheets": 0, "kg": 0.0, "sizes": [], "util": []})
        d["sheets"] += s.qty
        d["kg"] += s.gross_kg
        d["sizes"].append(f"{s.w:.0f}x{s.l:.0f}x{s.qty}")
        d["util"].append(s.utilization)
    keys = sorted(set(g) | set(o))
    rows = []
    for k in keys:
        rows.append(
            {
                "group": k,
                "gt_sheets": g.get(k, {}).get("sheets", 0),
                "gt_sizes": " ".join(g.get(k, {}).get("sizes", [])),
                "gt_kg": round(g.get(k, {}).get("kg", 0)),
                "our_sheets": o.get(k, {}).get("sheets", 0),
                "our_sizes": " ".join(o.get(k, {}).get("sizes", [])),
                "our_kg": round(o.get(k, {}).get("kg", 0)),
                "kg_ratio": round(o.get(k, {}).get("kg", 0) / g[k]["kg"], 2)
                if k in g and g[k]["kg"]
                else "",
            }
        )
    tot_g, tot_o = sum(r["gt_kg"] for r in rows), sum(r["our_kg"] for r in rows)
    with open(out / "cp_compare.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    md = [
        f"# 커팅플랜 비교 — {a.job}  ({run.name})",
        "",
        "| 그룹 | 사람 판 | 사람 규격(폭x길이x수량) | 사람 kg | 우리 판 | 우리 규격 | 우리 kg | 비율 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            f"| {r['group']} | {r['gt_sheets']} | {r['gt_sizes']} | {r['gt_kg']:,} | {r['our_sheets']} | {r['our_sizes']} | {r['our_kg']:,} | {r['kg_ratio']} |"
        )
    md += [
        "",
        f"**총계** 사람 {sum(r['gt_sheets'] for r in rows)}장 {tot_g:,} kg → 우리 {sum(r['our_sheets'] for r in rows)}장 {tot_o:,} kg, 비율 **{tot_o / tot_g:.3f}**"
        if tot_g
        else "",
        "",
        "사람 규격 뒤 괄호는 추출 품질(low/chain_path = 부품 분리 실패 판재). 사람 kg 는 모든 판재 포함.",
    ]
    (out / "cp_compare.md").write_text("\n".join(md), encoding="utf8")
    gt_png = next(iter((gt / "output_cutting_plan").glob("*.png")), None)
    our_png = next(iter(run.glob("*_CP.png")), None)
    if gt_png and our_png:
        cp_compare_png(gt_png, our_png, out / "cp_compare.png")

    # ---- 전개도 비교 ----
    tags = read_csv(gt / "output_cutting_plan" / "part_tags.csv")
    if not tags and a.job.startswith("HCE"):
        tags = hce_tags(gt)
    urows, extra = match_parts(tags, parts, flats)
    with open(out / "unfold_compare.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=list(urows[0].keys()) if urows else ["gt_name"]
        )
        w.writeheader()
        w.writerows(urows)
    matched = [r for r in urows if r["our_part_id"]]
    good = [r for r in matched if r["dim_err_pct"] != "" and r["dim_err_pct"] <= 5]
    qty_ok = [r for r in matched if r["qty_match"] is True]
    md = [
        f"# 전개도 비교 — {a.job}  ({run.name})",
        "",
        f"설계자 커팅 태그 {len(urows)}건 중 매칭 {len(matched)}건, 치수 오차 5% 이내 {len(good)}건, 수량 일치 {len(qty_ok)}건. 우리 쪽에만 있는 부품 {len(extra)}종.",
        "",
        "| 태그 | 부품 | 재질 t | 설계자 치수 ×수량 | 우리 부품 | 우리 치수 ×수량 | 오차% | 신뢰도 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in urows:
        md.append(
            f"| {r['gt_dwg_no']} | {r['gt_name']} | {r['material']} t{r['t']} | {r['gt_size']} ×{r['gt_qty']} | {r['our_name'] or '—'} | "
            f"{(r['our_size'] + ' ×' + str(r['our_qty'])) if r['our_name'] else '—'} | {r['dim_err_pct']} | {r['confidence']} |"
        )
    md += [
        "",
        "우리 쪽에만 있는 부품 (태그 없음 = 사람 CP 의 저품질 판재에 있거나 재고 처리): "
        + ", ".join(
            f"{p.part_name}({p.material} t{p.thickness:g} ×{p.quantity})" for p in extra
        ),
    ]
    (out / "unfold_compare.md").write_text("\n".join(md), encoding="utf8")
    n = unfold_compare_png(
        urows, parts, flats, gt / "output_unfold", out / "unfold_compare.png"
    )

    # ---- 우리 전개도 DXF 가 없으면 생성 ----
    unfold_dir = run / "unfold"
    if not unfold_dir.exists():
        from cutplan_agent.eval.manual_vlm_run import write_unfold_dxf

        unfold_dir.mkdir()
        for i, p in enumerate(parts):
            if p.part_id in flats:
                write_unfold_dxf(
                    p,
                    flats[p.part_id],
                    [],
                    unfold_dir
                    / f"{i:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', p.part_name)}.dxf",
                )
    print(
        f"커팅플랜: 사람 {sum(r['gt_sheets'] for r in rows)}장 {tot_g:,}kg → 우리 {sum(r['our_sheets'] for r in rows)}장 {tot_o:,}kg (비율 {tot_o / tot_g:.3f})"
    )
    print(
        f"전개도: 태그 {len(urows)} 매칭 {len(matched)} 오차5%이내 {len(good)} 수량일치 {len(qty_ok)} | 그림 {n}쌍"
    )
    print("outputs:", out)


if __name__ == "__main__":
    main()
