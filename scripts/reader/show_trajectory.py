"""orchestrator 실행 기록(<출력 폴더>/orchestrator/<시각>/)을 사람이 읽기 좋게 출력한다.

사용 (레포 루트에서):
  uv run python scripts/reader/show_trajectory.py [실행 폴더] [--width N]

  실행 폴더를 주지 않으면 runs/reader/agent/orchestrator/ 에서 가장 최근 실행을 보여 준다.
  명령과 모델, 턴마다 모델의 글 · 부른 tool 과 인자 · tool 결과 · 걸린 시간 · 토큰 수,
  마지막 보고를 차례로 출력한다. tool 결과는 --width 글자(기본 300)에서 자른다 (0 이면 전부).

기록 파일만 읽고 cutplan_agent 를 import 하지 않는다. 파일의 뜻은 docs/reader/orchestrator.md 4절에 있다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_RUNS = Path("runs/reader/agent/orchestrator")


def latest(runs: Path) -> Path:
    found = sorted(p for p in runs.iterdir() if (p / "trajectory.jsonl").is_file())
    if not found:
        raise SystemExit(f"{runs} 에 실행 기록이 없다")
    return found[-1]


def short(value, width: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if width <= 0 or len(text) <= width else text[:width] + " …"


def show(run: Path, width: int) -> None:
    command = json.loads((run / "command.json").read_text(encoding="utf-8"))
    print(f"실행 폴더   {run}")
    print(f"명령        {command.get('command')}")
    print(
        f"orchestrator {command.get('provider')} / {command.get('model')}"
        f" (tool 방식 {command.get('tool_mode')}, thinking {command.get('thinking')})"
    )
    stage_models = command.get("stage_models") or {}
    print(
        f"단계 모델   OCR {stage_models.get('ocr')} · 추론 {stage_models.get('reason')}"
    )
    print(f"tool        {len(command.get('tools') or [])}개")
    for line in (run / "trajectory.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "tool" in row:  # one tool call and its result
            print(f"    ← {row['tool']} 결과 ({row.get('seconds', 0):.1f} s)")
            print(f"      {short(row.get('result'), width)}")
            continue
        usage = row.get("usage") or {}
        tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        print(
            f"\n[턴 {row.get('turn')}] 시작 후 {row.get('seconds', 0):.1f} s · 입력 {tokens} 토큰"
        )
        if not row.get("calls"):
            print("  모델: tool 을 더 부르지 않고 보고한다 (아래 마지막 보고)")
        elif row.get("text"):
            print(f"  모델: {short(row['text'], width)}")
        for call in row.get("calls") or []:
            args = json.dumps(call.get("arguments"), ensure_ascii=False)
            print(f"  → {call.get('name')}({args})")
    answer = run / "answer.json"
    if answer.is_file():
        print("\n[마지막 보고]")
        print(json.loads(answer.read_text(encoding="utf-8")).get("answer"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", nargs="?", type=Path, help="실행 폴더 (기본: 가장 최근)")
    ap.add_argument("--width", type=int, default=300, help="tool 결과를 자를 길이")
    a = ap.parse_args()
    show(a.run or latest(DEFAULT_RUNS), a.width)


if __name__ == "__main__":
    main()
