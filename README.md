# cutplan_agent

압력용기·판금 도면을 읽어 부품을 전개하고, 판에 배치(네스팅)해 판재 구매의뢰(POR)까지 만드는 에이전트다. 두 부분으로 되어 있다.

- **v2 워크오더 에이전트** (`cutplan_agent/agent/`, `skills/`, `eval/`): 워크오더 하나의 도면 세트 → 자재목록 → 전개·분할 → 네스팅 → POR. Claude 가 skill 함수를 tool 로 부른다.
- **v3 도면 판독기** (`cutplan_agent/reader/`, `reconstruct/`): 도면 1장 → 형상 분류 → 전개도 (+3D 복원). 로컬 vLLM 또는 Anthropic 모델을 쓴다.

## 빠른 시작

```bash
uv sync
PYTHONPATH=. uv run python cutplan_agent/eval/smoke_kd25038.py   # API 없이 v2 전체 경로. 기대값 22/22 배치, 6125.0 kg
```

## 문서

문서는 모두 [docs/](docs/README.md) 에 있다. 처음이면 [docs/README.md](docs/README.md) 의 읽는 순서를 따른다.
코딩 에이전트용 규칙은 [AGENTS.md](AGENTS.md) 에 있다.
