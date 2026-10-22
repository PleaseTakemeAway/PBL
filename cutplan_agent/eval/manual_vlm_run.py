# -*- coding: utf-8 -*-
"""
VLM 자리를 사람(또는 Claude 세션)이 대신하는 수동 파이프라인.

  1) ingest : 입력 도면을 PNG(+DXF 텍스트 덤프)로 만든다 → 사람이 도면을 보고 spec.json 을 쓴다
  2) run    : spec.json(부품 3D 파라미터) → 전개 → 분할 → 네스팅 → 검증 → POR → DXF/PNG → 정답 비교

    PYTHONPATH=. uv run python cutplan_agent/eval/manual_vlm_run.py ingest --job KD23002
    PYTHONPATH=. uv run python cutplan_agent/eval/manual_vlm_run.py run --job KD23002 --spec runs/KD23002/spec.json

spec.json 형식:
{
  "job": "KD23002", "domain": "KDM",
  "sheet_widths": {"SA516-70|12": [2990], "SA283-C|16": [2438]},     # 선택: 그룹별 판 폭 후보
  "parts": [ {"part_name": "SHELL", "part_type": "cylinder", "material": "SA516-70", "thickness": 12, "quantity": 1,
              "inner_dia": 1017, "courses": [2949, 2949], "long_seams": 1, "confidence": "high",
              "note": "Detail of body: SHELL I.D 1017, welding seam plan 2764.5x2"}, ... ]
}
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from cutplan_agent.agent.orchestrator import job_inputs
from cutplan_agent.config import RUNS_DIR, TEST_DATA
from cutplan_agent.skills import (
    l1_perception as L1,
)
from cutplan_agent.skills import (
    l2_relation as L2,
)
from cutplan_agent.skills import (
    l3_rules as L3,
)
from cutplan_agent.skills import (
    l4_verify as L4,
)
from cutplan_agent.state import JobState, Trajectory, set_context


def ingest(job: str, inputs: list[str]):
    st = JobState(job=job, inputs=inputs)
    set_context(st, Trajectory(job))
    out = []
    for p in inputs:
        r = L1.ingest_drawing(p)
        if "error" in r:
            print("  !!", Path(p).name, r["error"])
            continue
        d = st.drawings[r["index"]]
        rec = {
            "index": r["index"],
            "name": d["name"],
            "kind": d["kind"],
            "pages": d["pages"],
        }
        if d.get("dxf"):
            t = L1.dxf_read_text(r["index"], max_items=3000)
            dump = st.run_dir() / "dxf_text" / (Path(p).stem + ".json")
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_text(
                json.dumps(t, ensure_ascii=False, indent=0), encoding="utf8"
            )
            rec["dxf_text"] = str(dump)
            rec["n_texts"] = t.get("n_texts")
            rec["n_dims"] = t.get("n_dims")
        out.append(rec)
        print(
            f"  [{r['index']}] {d['name']}  kind={d['kind']}  pages={len(d['pages'])}  texts={rec.get('n_texts', '-')} dims={rec.get('n_dims', '-')}"
        )
    st.save()
    (st.run_dir() / "ingest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8"
    )
    print("pages dir:", st.run_dir() / "pages")


def run(job: str, spec_path: str, domain: str = "KDM"):
    spec = json.loads(Path(spec_path).read_text(encoding="utf8"))
    st = JobState(job=job, eval_mode=True)
    set_context(st, Trajectory(job))
    widths = {k: v for k, v in spec.get("sheet_widths", {}).items()}
    # --- L2 (사람이 쓴 스펙) ---
    for p in spec["parts"]:
        L2.set_part_spec(**{k: v for k, v in p.items() if k not in ("evidence",)})
    # --- L3/L4 ---
    unfold_dir = st.run_dir() / "unfold"
    unfold_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, p in enumerate(st.parts):
        v = L4.verify_part_spec(i)
        f = L3.unfold_part(i)
        key = f"{p.material}|{p.thickness:g}"
        mw = max(widths.get(key, [0]) or [0]) or 0
        s = L3.split_to_pieces(i, max_w=mw) if "error" not in f else {"pieces": []}
        rows.append(
            {
                "part": p.part_name,
                "type": p.part_type,
                "spec_ok": v["ok"],
                "issues": v["issues"],
                "blank": (f.get("blank_w"), f.get("blank_h"))
                if "error" not in f
                else f["error"],
                "formula": f.get("formula", ""),
                "pieces": [
                    (x["label"], x["w"], x["h"], x["qty"]) for x in s.get("pieces", [])
                ],
            }
        )
        if "error" not in f:
            write_unfold_dxf(
                p,
                f,
                s.get("pieces", []),
                unfold_dir
                / f"{i:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', p.part_name)}.dxf",
            )
    for dxf in sorted(unfold_dir.glob("*.dxf")):
        try:
            L1._render_dxf(dxf, dxf.with_suffix(".png"), 1400)
        except Exception as e:
            print("  render fail", dxf.name, e)
    # 네스팅: 그룹별 폭 후보 적용
    st.sheets = []
    old_edge = L3.EDGE_MARGIN
    L3.EDGE_MARGIN = 0.0
    try:
        for m, t in sorted({(p.material, p.thickness) for p in st.pieces}):
            L3.nest_group(
                m, t, cut="plasma", widths=widths.get(f"{m}|{t:g}"), allow_custom=True
            )
        ver = L4.verify_nesting("plasma")
    finally:
        L3.EDGE_MARGIN = old_edge
    por = L3.build_por()
    cp = L3.write_cutting_plan_dxf(str(st.run_dir() / f"{job}_CP.dxf"))
    L1._render_dxf(Path(cp["path"]), st.run_dir() / f"{job}_CP.png", 2400)
    gt = (
        L4.compare_with_gt(job.split("_")[0]) if domain == "KDM" else {}
    )  # job 이름 'KD23022_manual' → WO 'KD23022'
    st.save()
    # --- 보고 ---
    print(
        f"\n== {job} 부품 {len(st.parts)}개 → 조각 {sum(p.qty for p in st.pieces)}개 → 판 {len(st.sheets)}장 =="
    )
    for r in rows:
        print(
            f"  {r['part']:<18} {r['type']:<12} ok={r['spec_ok']} blank={r['blank']}  {r['pieces']}"
        )
    print("\n== 판재 ==")
    for s in st.sheets:
        print(
            f"  {s.material} t{s.thickness:g} x {s.w:.0f} x {s.l:.0f}  util {s.utilization:.0%}  {s.gross_kg} kg  [{', '.join(pl.piece_id.split(':')[-1].split('#')[0] for pl in s.placements)}]"
        )
    print("== 검증 ==", ver)
    print(
        "== POR ==",
        [(r["spec"], r["material"], r["qty"], r["weight_kg"]) for r in por["rows"]],
        "total",
        por["total_kg"],
    )
    if gt and "groups" in gt:
        print("\n== 정답(사람 커팅플랜) 대비 ==  kg_ratio", gt.get("kg_ratio"))
        for g in gt["groups"]:
            print(
                f"  {g['group']:<18} 판 {g['gt_sheets']}→{g['our_sheets']}   kg {g['gt_kg']:.0f}→{g['our_kg']:.0f}"
            )
    (st.run_dir() / "manual_metrics.json").write_text(
        json.dumps(
            {"rows": rows, "verify": ver, "por": por["rows"], "gt": gt},
            ensure_ascii=False,
            indent=1,
            default=str,
        ),
        encoding="utf8",
    )
    print("\noutputs:", st.run_dir())


def write_unfold_dxf(p, flat, pieces, path: Path):
    """부품 하나의 전개도 DXF: 전개 블랭크(원통=직사각, 콘=부채꼴, 헤드/패드=원, 평판=윤곽) + 분할 조각 bbox + 정보 텍스트."""
    import math

    import ezdxf
    from ezdxf import units

    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.MM
    msp = doc.modelspace()
    for n, c in (("BLANK", 7), ("SPLIT", 1), ("INFO", 5)):
        doc.layers.add(n, color=c)
    t = flat["type"]
    if t == "cylinder":
        y = 0.0
        for c in flat["courses"]:
            msp.add_lwpolyline(
                [
                    (0, y),
                    (c["blank_w"], y),
                    (c["blank_w"], y + c["blank_h"]),
                    (0, y + c["blank_h"]),
                ],
                close=True,
                dxfattribs={"layer": "BLANK"},
            )
            y += c["blank_h"] + 100
    elif t == "cone_frustum":
        R1, R2, th = flat["R1"], flat["R2"], math.radians(flat["theta_deg"])
        a0 = -th / 2
        msp.add_arc(
            (0, 0),
            R1,
            math.degrees(a0),
            math.degrees(a0 + th),
            dxfattribs={"layer": "BLANK"},
        )
        msp.add_arc(
            (0, 0),
            R2,
            math.degrees(a0),
            math.degrees(a0 + th),
            dxfattribs={"layer": "BLANK"},
        )
        for a in (a0, a0 + th):
            msp.add_line(
                (R2 * math.cos(a), R2 * math.sin(a)),
                (R1 * math.cos(a), R1 * math.sin(a)),
                dxfattribs={"layer": "BLANK"},
            )
    elif t in ("head", "pad_ring"):
        D = flat["blank_w"]
        msp.add_circle((D / 2, D / 2), D / 2, dxfattribs={"layer": "BLANK"})
        if t == "pad_ring" and p.pad_id > 0:
            msp.add_circle((D / 2, D / 2), p.pad_id / 2, dxfattribs={"layer": "BLANK"})
    elif flat.get("outline"):
        msp.add_lwpolyline(flat["outline"], close=True, dxfattribs={"layer": "BLANK"})
    y = -200.0
    for ln in [
        f"{p.part_name}  {p.material} t{p.thickness:g}  x{p.quantity}",
        f"{t}: {flat.get('formula', '')}",
    ] + [
        f"piece {x['label']}: {x['w']} x {x['h']}  x{x['qty']}  {x.get('note', '')}"
        for x in pieces
    ]:
        msp.add_text(
            ln,
            height=max(flat.get("blank_h", 500) * 0.03, 25),
            dxfattribs={"layer": "INFO"},
        ).set_placement((0, y))
        y -= max(flat.get("blank_h", 500) * 0.045, 40)
    doc.saveas(str(path))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["ingest", "run"])
    ap.add_argument("--job", required=True)
    ap.add_argument("--spec", default="")
    ap.add_argument("--domain", default="KDM")
    a = ap.parse_args()
    if a.mode == "ingest":
        wo = a.job.split("_")[0]
        ins = (
            job_inputs(wo)
            if a.domain == "KDM"
            else [
                str(TEST_DATA / "HCE_76K3-40022" / "input_drawings" / "76K3-40022.pdf")
            ]
        )
        print(f"{a.job}: {len(ins)} inputs")
        ingest(a.job, ins)
    else:
        run(a.job, a.spec or str(RUNS_DIR / a.job / "spec.json"), a.domain)
