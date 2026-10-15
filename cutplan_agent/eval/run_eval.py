# -*- coding: utf-8 -*-
"""
dataset 워크오더에 대해 에이전트를 평가 모드로 돌리고 사람 커팅플랜(gt/sheets.csv)과 비교한다.

    uv run python -m cutplan_agent.eval.run_eval --jobs KD23002,KD23015,KD23022 [--max-steps 80]

결과: runs/<job>/state.json, trajectory.json, final.md, runs/_eval_summary.csv
ANTHROPIC_API_KEY 필요.
"""
import argparse, csv

from cutplan_agent.config import RUNS_DIR
from cutplan_agent.agent.orchestrator import run, job_inputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--max-steps", type=int, default=80)
    a = ap.parse_args()
    rows = []
    for job in [j.strip() for j in a.jobs.split(",") if j.strip()]:
        ins = job_inputs(job)
        if not ins:
            print(f"[{job}] 입력 도면 없음 — 건너뜀"); continue
        st = run(job, ins, eval_mode=True, max_steps=a.max_steps)
        gt = st.verify.get("gt", {})
        rows.append({"job": job, "n_inputs": len(ins), "bom_plates": sum(1 for b in st.bom if b.is_plate), "parts": len(st.parts),
                     "pieces": len(st.pieces), "sheets": len(st.sheets), "gt_total_kg": gt.get("gt_total_kg"),
                     "our_total_kg": gt.get("our_total_kg"), "kg_ratio": gt.get("kg_ratio"), "hitl": len(st.hitl),
                     "nesting_ok": st.verify.get("nesting", {}).get("ok")})
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    p = RUNS_DIR / "_eval_summary.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["job"])
        w.writeheader(); w.writerows(rows)
    print("summary:", p)


if __name__ == "__main__":
    main()
