# -*- coding: utf-8 -*-
"""
수동 판독(또는 VLM) 실행들의 compare 결과를 한 표로 모은다.

    uv run python -m cutplan_agent.eval.aggregate_manual --runs KD23002_manual,KD23022_manual,... [--out runs/experiments/E7_manual_5samples.md]
각 run 의 compare/cp_compare.csv, unfold_compare.csv 를 읽어 kg 비율·판 수·부품 일치율을 집계.
"""
import argparse, csv, json, statistics
from pathlib import Path
from cutplan_agent.config import RUNS_DIR


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", required=True); ap.add_argument("--out", default=""); a = ap.parse_args()
    rows = []
    for run in [r.strip() for r in a.runs.split(",") if r.strip()]:
        d = RUNS_DIR / run / "compare"
        if not (d / "cp_compare.csv").exists():
            rows.append({"run": run, "status": "no compare"}); continue
        cp = list(csv.DictReader(open(d / "cp_compare.csv", encoding="utf-8-sig")))
        uf = list(csv.DictReader(open(d / "unfold_compare.csv", encoding="utf-8-sig")))
        gt_kg = sum(float(r["gt_kg"] or 0) for r in cp); our_kg = sum(float(r["our_kg"] or 0) for r in cp)
        gt_sh = sum(int(float(r["gt_sheets"] or 0)) for r in cp); our_sh = sum(int(float(r["our_sheets"] or 0)) for r in cp)
        matched = [r for r in uf if r["our_part_id"]]
        good = [r for r in matched if r["dim_err_pct"] not in ("", None) and float(r["dim_err_pct"]) <= 5]
        qok = [r for r in matched if r["qty_match"] == "True"]
        groups_both = [r for r in cp if float(r["gt_kg"] or 0) > 0 and float(r["our_kg"] or 0) > 0]
        st = json.loads((RUNS_DIR / run / "state.json").read_text(encoding="utf8"))
        rows.append({"run": run, "status": "ok", "parts": len(st["parts"]), "pieces": sum(p["qty"] for p in st["pieces"]),
                     "gt_sheets": gt_sh, "our_sheets": our_sh, "gt_kg": round(gt_kg), "our_kg": round(our_kg),
                     "kg_ratio": round(our_kg / gt_kg, 3) if gt_kg else None, "groups_gt": sum(1 for r in cp if float(r["gt_kg"] or 0) > 0),
                     "groups_both": len(groups_both), "tags": len(uf), "matched": len(matched), "dim_ok5": len(good), "qty_ok": len(qok),
                     "feasible": st.get("verify", {}).get("nesting", {}).get("ok")})
    ok = [r for r in rows if r["status"] == "ok" and r["kg_ratio"]]
    L = ["# 수동 판독 end-to-end 집계", "", "| run | 부품 | 조각 | 판 사람→우리 | kg 사람→우리 | kg 비율 | 그룹(사람/겹침) | 태그 | 매칭 | 5%이내 | 수량일치 | 배치 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["status"] != "ok":
            L.append(f"| {r['run']} | {r['status']} |||||||||||"); continue
        L.append(f"| {r['run']} | {r['parts']} | {r['pieces']} | {r['gt_sheets']}→{r['our_sheets']} | {r['gt_kg']:,}→{r['our_kg']:,} | {r['kg_ratio']} | "
                 f"{r['groups_gt']}/{r['groups_both']} | {r['tags']} | {r['matched']} | {r['dim_ok5']} | {r['qty_ok']} | {'✓' if r['feasible'] else '✗'} |")
    if ok:
        L += ["", f"kg 비율: 중앙값 {statistics.median(r['kg_ratio'] for r in ok):.3f}, 평균 {statistics.mean(r['kg_ratio'] for r in ok):.3f}, "
              f"범위 {min(r['kg_ratio'] for r in ok):.3f}~{max(r['kg_ratio'] for r in ok):.3f}",
              f"부품 일치율(5% 이내 / 태그): {sum(r['dim_ok5'] for r in ok)}/{sum(r['tags'] for r in ok)} = {sum(r['dim_ok5'] for r in ok)/max(sum(r['tags'] for r in ok),1):.0%}, "
              f"수량 일치 {sum(r['qty_ok'] for r in ok)}/{sum(r['tags'] for r in ok)}"]
    text = "\n".join(L)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf8")


if __name__ == "__main__":
    main()
