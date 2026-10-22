"""
오케스트레이터: Claude tool_runner 가 skill 들을 도구로 호출한다. 모든 호출은 trajectory 로 남는다.

사용
    PYTHONPATH=. uv run python cutplan_agent/agent/orchestrator.py --job KD23002 [--eval] [--max-steps 80]
    PYTHONPATH=. uv run python cutplan_agent/agent/orchestrator.py --job KD23002 --inputs "a.pdf;b.dwg"

ANTHROPIC_API_KEY 가 필요하다. 없으면 eval/smoke_kd25038.py (L3/L4 만, API 불필요) 를 먼저 돌려라.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path
from typing import Callable, List

from cutplan_agent.config import DATASET, MAX_TOKENS, MODEL
from cutplan_agent.skills import knowledge as K
from cutplan_agent.skills import l1_perception as L1
from cutplan_agent.skills import l2_relation as L2
from cutplan_agent.skills import l3_rules as L3
from cutplan_agent.skills import l4_verify as L4
from cutplan_agent.state import JobState, Trajectory, get_state, set_context


def _tool(fn: Callable) -> Callable:
    """skill 함수 → Claude tool. 반환 dict 를 JSON 문자열로. 시그니처/독스트링은 그대로 (스키마 자동 생성)."""
    from anthropic import beta_tool

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        out = fn(*a, **kw)
        return (
            out
            if isinstance(out, str)
            else json.dumps(out, ensure_ascii=False, default=str)
        )

    return beta_tool(wrapper)


def list_inputs() -> dict:
    """현재 job 의 입력 도면 목록 (dataset/KDM/<year>/<job>/input/drawings 의 pdf/dwg). 같은 이름의 dwg 와 pdf 가 있으면 dwg 를 우선."""
    st = get_state()
    files = {}
    for p in st.inputs:
        files[Path(p).stem] = p
    return {"job": st.job, "n": len(files), "files": list(files.values())}


def get_state_summary() -> dict:
    """state 요약: 도면/BOM/부품/조각/판/HITL 개수와 판재 항목 목록."""
    st = get_state()
    return {
        "drawings": [
            {
                "i": i,
                "name": d["name"],
                "kind": d["kind"],
                "category": d.get("category", ""),
            }
            for i, d in enumerate(st.drawings)
        ],
        "bom_plates": [
            {
                "i": i,
                "item": b.item_no,
                "name": b.part_name,
                "mat": b.material,
                "t": b.thickness,
                "qty": b.qty,
                "cls": b.unfold_class,
            }
            for i, b in enumerate(st.bom)
            if b.is_plate
        ],
        "parts": [
            {
                "i": i,
                "id": p.part_id,
                "type": p.part_type,
                "conf": p.confidence,
                "unfolded": p.part_id in st.flats,
            }
            for i, p in enumerate(st.parts)
        ],
        "pieces": len(st.pieces),
        "sheets": len(st.sheets),
        "por_rows": len(st.por),
        "hitl": len(st.hitl),
    }


SKILLS: List[Callable] = [
    list_inputs,
    get_state_summary,
    K.load_domain_prompt,
    L1.ingest_drawing,
    L1.dxf_read_text,
    L1.vlm_read_page,
    L1.normalize_bom,
    L2.classify_drawing,
    L2.extract_design_data,
    L2.extract_part_model,
    L2.set_part_spec,
    L2.detect_split_lines,
    L2.resolve_missing_spec,
    L3.unfold_part,
    L3.split_to_pieces,
    L3.nest_group,
    L3.nest_all,
    L3.write_cutting_plan_dxf,
    L3.build_por,
    L4.verify_part_spec,
    L4.verify_weight_vs_bom,
    L4.verify_nesting,
    L4.compare_with_gt,
    L4.ask_human,
    L4.confidence_report,
]


def build_tools() -> list:
    return [_tool(f) for f in SKILLS]


def job_inputs(job: str) -> List[str]:
    year = "20" + job[2:4]
    d = DATASET / "KDM" / year / job / "input" / "drawings"
    if not d.exists():
        return []
    files = {}
    for p in sorted(d.rglob("*")):
        if (
            p.suffix.lower() in (".dwg", ".pdf")
            and "CUTTING" not in p.name.upper()
            and "_CP" not in p.name.upper()
        ):
            cur = files.get(p.stem)
            if cur is None or (p.suffix.lower() == ".dwg"):
                files[p.stem] = str(p)
    return list(files.values())


def run(
    job: str,
    inputs: List[str],
    eval_mode: bool = False,
    max_steps: int = 80,
    hitl_policy: dict | None = None,
) -> JobState:

    state = JobState(job=job, inputs=inputs, eval_mode=eval_mode)
    if hitl_policy:
        state.hitl_policy.update(hitl_policy)
    traj = Trajectory(job)
    set_context(state, traj)
    from cutplan_agent.client import make_client

    client = make_client()
    system = (Path(__file__).parent / "system.md").read_text(encoding="utf8")
    user = (
        f"워크오더 {job} 의 도면 {len(inputs)}장을 처리하라. list_inputs 로 파일을 확인하고 절차 ①~⑥ 을 수행하라. "
        + (
            "평가 모드: ask_human 은 자동 응답되며, 마지막에 compare_with_gt 를 호출하라."
            if eval_mode
            else "사람 확인이 필요하면 ask_human 을 호출하라."
        )
    )
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=build_tools(),
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": user}],
    )
    final_text = ""
    import time as _time

    t0 = _time.time()
    print(
        f"[start] job={job} inputs={len(inputs)} model={MODEL}  (각 턴은 API 응답에 수십 초~수 분 걸릴 수 있다)",
        flush=True,
    )
    for i, msg in enumerate(runner):
        el = int(_time.time() - t0)
        for b in msg.content:
            if b.type == "tool_use":
                args = json.dumps(b.input, ensure_ascii=False)
                print(
                    f"[turn {i:02d} {el:4d}s] -> {b.name}({args[:140]}{'...' if len(args) > 140 else ''})",
                    flush=True,
                )
            elif b.type == "text" and b.text.strip():
                final_text = b.text
                print(
                    f"[turn {i:02d} {el:4d}s] text: {b.text.strip()[:200].replace(chr(10), ' ')}",
                    flush=True,
                )
        state.save()
        traj.save()  # 매 턴 저장 → 다른 터미널에서 status.py 로 확인 가능
        if i >= max_steps:
            print(f"[max_steps={max_steps}] 중단")
            break
    (state.run_dir() / "final.md").write_text(final_text, encoding="utf8")
    state.save()
    traj.save()
    print(final_text)
    print(
        f"\nstate: {state.run_dir() / 'state.json'}  trajectory: {state.run_dir() / 'trajectory.json'}"
    )
    return state


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument(
        "--inputs", default="", help="';' 로 구분. 비우면 dataset 의 input/drawings"
    )
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--max-steps", type=int, default=80)
    a = ap.parse_args()
    ins = [s for s in a.inputs.split(";") if s] or job_inputs(a.job)
    if not ins:
        sys.exit("입력 도면이 없다")
    run(a.job, ins, a.eval, a.max_steps)
