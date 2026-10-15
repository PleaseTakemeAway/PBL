# -*- coding: utf-8 -*-
"""
실행 중인(또는 끝난) job 의 진행 상황 조회. 다른 터미널에서:

    uv run python -m cutplan_agent.eval.status --job KD23002          # 한 번
    uv run python -m cutplan_agent.eval.status --job KD23002 --watch  # 10초마다 갱신

읽는 것: runs/<job>/state.json (매 턴 저장), trajectory.json (skill 호출 로그), pages/ (렌더된 도면), final.md (끝났을 때)
"""
import argparse, json, os, time
from datetime import datetime
from cutplan_agent.config import RUNS_DIR


def show(job: str):
    d = RUNS_DIR / job
    if not d.exists():
        print(f"{d} 없음 — 아직 시작 안 됨 (ingest 전)"); return
    st = d / "state.json"; tr = d / "trajectory.json"; fin = d / "final.md"
    print(f"== {job}  {datetime.now().strftime('%H:%M:%S')} ==")
    if st.exists():
        age = time.time() - st.stat().st_mtime
        s = json.loads(st.read_text(encoding="utf8"))
        print(f"state.json  갱신 {age:5.0f}초 전 | 도면 {len(s.get('drawings', []))} | BOM {len(s.get('bom', []))} (판재 {sum(1 for b in s.get('bom', []) if b.get('is_plate'))}) "
              f"| 부품 {len(s.get('parts', []))} | 전개 {len(s.get('flats', {}))} | 조각 {len(s.get('pieces', []))} | 판 {len(s.get('sheets', []))} | POR {len(s.get('por', []))} | HITL {len(s.get('hitl', []))}")
        cats = [f"{x['name'][:28]}:{x.get('category') or '?'}" for x in s.get("drawings", [])]
        if cats:
            print("  도면 분류:", "; ".join(cats))
        pend = [h for h in s.get("hitl", []) if h.get("answer") is None]
        if pend:
            print("  ! HITL 대기:", [h["question"][:60] for h in pend])
    else:
        print("state.json 아직 없음")
    if tr.exists():
        steps = json.loads(tr.read_text(encoding="utf8"))
        print(f"trajectory  skill 호출 {len(steps)}회. 최근:")
        for x in steps[-8:]:
            r = x["result"]
            err = r.get("error") if isinstance(r, dict) else None
            print(f"   {x['step']:3d}. {x['skill']:<22} {x['dt']:6.1f}s  {('ERROR ' + err) if err else ''}")
    pages = d / "pages"
    if pages.exists():
        print(f"pages/      렌더된 페이지 {len(list(pages.glob('*.png')))}장")
    if fin.exists():
        print(f"final.md    완료 ({fin.stat().st_size} bytes) — 최종 요약 있음")
    else:
        print("final.md    없음 → 아직 진행 중이거나 중단됨 (python 프로세스와 콘솔 출력 확인)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    while True:
        show(a.job)
        if not a.watch:
            break
        time.sleep(10); print()
