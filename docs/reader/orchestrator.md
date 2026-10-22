# 도면 판독 orchestrator

자연어 명령 한 줄을 받아, 모델이 판독 13단계([stages.md](stages.md))를 tool 로 골라 부르는 실행기다. 2026-10-23 에 `reader-agent` 브랜치에서 만들어 main 에 머지했다. [harness_engineering.md](../harness_engineering.md) 로드맵 6번(로컬 orchestrator)의 첫 판이다.

- 단계 순서를 코드가 정하는 [`stages/run.py`](../../cutplan_agent/reader/stages/run.py) 와 달리, 어떤 단계를 언제 다시 부를지를 모델이 정한다. `run.py` 가 비교 기준선이다.
- 모델이 하는 일은 다음 tool 고르기뿐이다. 판독과 계산은 단계 함수(`stages/*.py` 의 `run`)가 하고, 결과도 단계 스크립트와 같은 파일로 남는다.
- 같은 루프를 로컬 모델(vLLM)과 Claude 로 돌릴 수 있어서, 같은 하네스에서 둘을 비교할 수 있다.

## 1. 실행

레포 루트에서 실행한다. 판독기 의존성은 pyproject 에 있으므로 `uv run python` 이면 된다 ([getting_started.md](../getting_started.md)).

```bash
. runs/vllm/ocr.env; . runs/vllm/reason.env      # serve.sh 로 띄운 서버. 단계 모델과 orchestrator 가 같이 쓴다

PYTHONPATH=. uv run python cutplan_agent/reader/orchestrator.py "cone_0019 를 전개도까지 판독하고 결과를 알려줘" --tool-mode schema
PYTHONPATH=. uv run python cutplan_agent/reader/orchestrator.py "cone_0019 의 view_labels 부터 다시 돌려줘" --tool-mode schema
PYTHONPATH=. uv run python cutplan_agent/reader/orchestrator.py "cone_0019 판독해줘" --provider anthropic   # Claude 가 orchestration
```

- 명령 하나를 처리하고 끝난다 (대화형이 아니다). 상태는 작업 폴더의 단계 파일에 남으므로, 다음 명령은 `stage_status` 로 이어서 일한다.
- 작업 폴더는 `--output-dir`(기본 `runs/reader/agent`) 아래 `<도면 이름>/` 이다. 입력 도면은 `--input-dir`(기본 `data_v3/synthetic`) 의 DXF 에서 찾는다. DWG 는 tool 이 없으므로 먼저 00 `convert` 로 바꿔 둔다 ([stages.md](stages.md)).
- 단계 모델은 `stages/run.py` 와 같은 옵션(`--ocr-*`, `--reason-*`, `--no-vlm`)이나 `CUTPLAN_OCR_*`, `CUTPLAN_REASON_*` 로 정한다.
- orchestrator 모델은 `--provider`, `--model`, `--base-url` 이나 `CUTPLAN_ORCH_{PROVIDER,MODEL,BASE_URL,API_KEY}` 로 정한다. openai 이면서 따로 정하지 않으면 추론 모델(`CUTPLAN_REASON_*`)을 쓴다.

## 2. tool 호출 방식

| `--provider` / `--tool-mode` | 모델이 tool 을 부르는 방법 | 서버 조건 |
|---|---|---|
| `openai` / `native` (기본) | OpenAI 호환 `tools`. 모델이 `tool_calls` 를 내고, 결과는 `role: tool` 메시지로 돌려준다 | vLLM 을 `--enable-auto-tool-choice --tool-call-parser <파서>` 로 띄워야 한다 |
| `openai` / `schema` | `tools` 없이, 응답마다 `{"thought", "tool", "arguments"}` JSON 하나를 JSON schema 로 강제한다. schema 는 tool 마다 인자 schema 를 가진 `anyOf` 이고 `finish` 가 끝이다. tool 설명은 system prompt 에 글로 넣는다 | structured outputs (지금 `serve.sh` 설정 그대로 된다) |
| `anthropic` | Claude tool use. 루프는 다른 방식과 같은 코드다 (`tool_runner` 를 쓰지 않는다). 거절된 요청은 server-side fallback 으로 다른 모델이 이어받는다 | `.env` 의 `ANTHROPIC_API_KEY` |

- 지금 `experiments/vllm_common.sh` 의 추론 서버는 tool parser 없이 뜬다. 그래서 `native` 는 400 을 받고, 오류 메시지가 서버 옵션이나 `--tool-mode schema` 를 안내한다.

### 2.1 모델이 도구를 부르는 방식들 (2026-10-23 확인)

"tool calling" 은 두 가지를 가리킨다. 하나는 패턴이다: 모델이 함수와 인자를 고르고, 프로그램이 실행하고, 결과를 모델에게 돌려주는 반복. 다른 하나는 API 기능이다: 요청의 `tools` 를 서버가 모델이 학습한 형식(Qwen3.6 은 `<tool_call><function=…>`)으로 프롬프트에 넣고, 모델이 쓴 호출을 서버의 tool parser 가 꺼내 `tool_calls` 로 돌려준다. `schema` 모드는 패턴은 같지만 API 기능을 쓰지 않는다. 도구 설명은 system prompt 에 글로 넣고, 답을 structured outputs(`response_format: json_schema`)로 강제하고, 그 JSON 을 이 코드가 읽어 함수를 부른다. 2026-10-23 의 cone_0019 시연(5.1절)은 `schema` 모드다.

| 방식 | 요청 | 형식 보장 | 이 서버 (`serve.sh` 기본값, 2026-10-23) |
|---|---|---|---|
| 프롬프트만 (ReAct 식) | 도구를 글로 설명하고 모델이 쓴 글을 파싱 | 없다 | 된다 (서버 기능이 필요 없다) |
| JSON mode | `response_format: {"type": "json_object"}` | JSON 문법만 | 된다 |
| structured outputs (`schema` 모드) | `response_format: {"type": "json_schema", …}`. vLLM 은 xgrammar 로 스키마에 맞는 토큰만 만든다 | 스키마까지 | 된다 |
| native `auto` | `tools`, `tool_choice: "auto"`. 모델이 호출 여부와 개수를 정하고 parser 가 꺼낸다 | 없다 (parser 가 놓칠 수 있다) | 400 `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set` |
| native `required` | `tool_choice: "required"`. 하나 이상 호출 | 있다 | 400 `tool_choice="required" requires --tool-call-parser to be set` |
| native 지정 | `tool_choice: {"type": "function", "function": {"name": …}}` | 있다 | 400 `tool_choice=function "…" requires --tool-call-parser to be set` |

- 확인 방법: 떠 있던 추론 서버(Qwen3.6-27B)에 도구 하나(`stage_status`)를 넣은 요청을 `tool_choice` 만 바꿔 세 번 보냈다. 서버는 재기동하지 않았다.
- vLLM 0.31 코드(`vllm/tool_parsers/utils.py` 의 `get_json_schema_from_tools`)를 보면 `required` 는 "도구 스키마들의 `anyOf` 를 항목으로 하는 배열(`minItems: 1`)" 을, 지정은 그 함수의 인자 스키마를 structured outputs 로 강제한다. 즉 `required` 는 `schema` 모드와 거의 같은 원리다. 그래도 서버는 `--tool-call-parser` 가 없으면 요청을 거절한다 (코드의 응답 조립 부분만 보면 parser 없이 될 것처럼 보이지만 실제로는 거절된다).
- native 의 장점은 모델이 학습한 호출 형식이라는 것, 글과 호출을 함께 쓰거나 한 번에 여러 도구를 부를 수 있다는 것이다. `schema` 모드의 장점은 약한 모델도 형식을 틀릴 수 없다는 것이고, 대가는 한 턴에 도구 하나와 우리가 만든 형식이다. 어느 쪽이 나은지는 재지 않았다. 같은 도면으로 비교하는 것이 하네스 실험 항목이다.
- vLLM 밖의 방식: Claude tool use (`--provider anthropic`. v2 워크오더 에이전트도 Claude 의 `tool_runner` 로 skill 25개를 이 방식으로 불렀다), 모델이 파이썬 코드를 써서 함수를 부르는 방식(code-as-action, 실행 샌드박스가 필요하다).
- `native` 를 쓰려면 서버를 `--reason-vllm-arg=--enable-auto-tool-choice --reason-vllm-arg=--tool-call-parser=qwen3_coder` 를 붙여 다시 띄운다. Qwen3.6 chat template 은 `<tool_call><function=…><parameter=…>` 형식이라 vLLM 0.31 의 `qwen3_coder`(= `qwen3_xml`) 파서가 맞을 것으로 보인다. 아직 띄워서 확인하지 않았다.
- `schema` 는 약한 모델이 tool 형식을 틀릴 일을 디코딩 단계에서 없앤다. 대신 응답마다 tool 을 정확히 하나만 부르고, `thought` 가 생각할 자리를 대신한다. 두 방식의 차이는 그 자체로 하네스 비교 항목이다.
- `--thinking off|on|default` (openai): Qwen3 의 `enable_thinking` 을 `chat_template_kwargs` 로 보낸다. 기본은 `off` 다. 서버의 `--max-model-len` 이 16384 라서 생각 토큰이 쌓이면 대화가 넘친다. `--effort` (anthropic) 의 기본은 `medium` 이다.

## 3. tool

정의는 [`reader/tools.py`](../../cutplan_agent/reader/tools.py) 에 있다. 모든 tool 은 JSON 인자를 받고 작은 JSON 을 돌려준다. 단계 파일 전체(01 은 엔티티 목록 전부)가 아니라 상태, `describe()` 요약, 모델 호출 결과(ok, error)만 돌려준다.

| tool | 하는 일 |
|---|---|
| `list_drawings(folder?, name?)` | DXF 목록과 도면마다의 작업 폴더(`work`), 이미 있는 단계 |
| `stage_status(work)` | 13단계 각각의 상태: done, skipped(이유), failed(오류), not run |
| `show_stage(work, stage)` | 한 단계의 요약, review 항목, 모델 원문 앞부분 1500자 |
| `run_<단계>(work, …)` | 13개. 설명은 단계 스크립트 docstring 의 첫 문단과 `in :` 줄이다. 옵션: `run_read(drawing)`, `run_views(gap_ratio)`, `run_view_labels(projection_default)`, `run_document(units)`, `run_reconstruct(tolerance, max_candidates)` |
| `run_stages(work, first?, last?, drawing?)` | 여러 단계를 차례로 (`stages/run.py` 의 `run_drawing`) |

- 단계 모델(OCR, 추론)은 tool 을 만들 때 고정한다. orchestrator 모델은 모델을 바꿀 수 없다.
- 틀린 tool 이름, 없는 인자, 빠진 인자, 앞 단계가 없는 단계(`not_ready`), 단계 오류는 모두 `{"error": …}` 결과로 모델에게 돌아간다. 루프는 멈추지 않는다.
- `work` 는 `--output-dir` 아래여야 한다. 상대 경로는 출력 폴더 기준으로도 읽으므로 `cone_0019` 만 줘도 된다.

## 4. 기록

실행마다 `<output-dir>/orchestrator/<YYYYmmdd-HHMMSS>/` 에 남는다.

| 파일 | 내용 |
|---|---|
| `command.json` | 명령, provider, 모델, tool 방식, 단계 모델, tool 목록 전체(설명과 schema) |
| `trajectory.jsonl` | 모델 턴마다 한 줄(글, tool 호출, 종료 이유, 토큰 수, 경과 시간)과 tool 호출마다 한 줄(인자, 결과, 걸린 시간) |
| `messages.json` | provider 에 보낸 대화 그대로 |
| `answer.json` | 마지막 보고 |

사람이 읽기 좋게 보려면 `uv run python scripts/reader/show_trajectory.py [실행 폴더]` 를 쓴다. 폴더를 주지 않으면 `runs/reader/agent/orchestrator/` 의 가장 최근 실행을 보여 준다. 명령과 모델, 턴마다 모델의 글 · 부른 tool 과 인자 · tool 결과 · 시간 · 토큰, 마지막 보고를 출력한다.

## 5. 확인한 것 (2026-10-23, `mlic`)

- `tests/test_reader_tools.py`: 모델 없이 tool 목록, 잘못된 호출, 단계 실행·상태 조회를 확인한다. `tests/test_orchestrator.py`: 정해진 턴을 재생하는 가짜 backend 로 루프와 기록을 확인한다. schema 모드의 `anyOf` 에 tool 전부와 `finish` 가 들어가는지도 본다.
- Qwen3.6-27B, `--tool-mode schema`, 단계 모델 DeepSeek-OCR-2 + Qwen3.6-27B 로 `"cone_0019 도면을 전개도까지 판독하고 결과를 알려줘"`: 모델이 `list_drawings(name="cone_0019")` → `run_stages(first="read", last="develop")` → `finish` 순서로 3턴 만에 끝냈다 (133초, 그중 단계 실행 92초, 마지막 턴 입력 4.3k 토큰). 보고에 쓴 숫자(지름 150/92, 높이 150, 전개 반지름 405.65/252.87, 68.33°)는 모두 tool 결과에 있는 값이다. 작은 지름 92 는 정답 100 과 다른데, 이것은 09 `unfold_params` 의 판독 결과이고 orchestrator 와는 관계없다.
- 확인하지 않은 것: `native` 모드 (서버 재기동 필요), `--provider anthropic` (API 비용), 여러 도면을 한 명령으로 처리, 실패한 단계를 모델이 다시 부르는 경우.

### 5.1 시연 기록 (발표에서 보여 줄 것)

위 두 번째 항목의 실행이다. 기록은 git 에 넣지 않는다 (`runs/` 는 git 밖이다). 이 실행은 `reader-agent` worktree(`~/developer/pbl-reader-agent`)에서 했고, worktree 를 지워도 남도록 원래 clone(`~/developer/pbl`)의 같은 경로에 복사해 두었다 (2026-10-23).

| 무엇 | 어디 |
|---|---|
| 실행한 명령 | 레포 루트에서 `. runs/vllm/ocr.env; . runs/vllm/reason.env` 후 `PYTHONPATH=. uv run python cutplan_agent/reader/orchestrator.py "cone_0019 도면을 전개도까지 판독하고 결과를 알려줘" --tool-mode schema` (당시는 판독기 의존성이 pyproject 에 없어 `uv run --with requests --with opencv-python-headless --with pytesseract python` 으로 돌렸다. orchestrator 와 추론 단계 모두 `serve.sh` 의 Qwen3.6-27B, OCR 은 DeepSeek-OCR-2) |
| 실행 기록 | `runs/reader/agent/orchestrator/20261023-021136/` (`command.json`, `trajectory.jsonl`, `messages.json`, `answer.json`) |
| 단계 파일 | `runs/reader/agent/cone_0019/stages/01_read.json` … `10_develop.json`, 전개도 `flat_pattern.{json,dxf,png}` |
| 코드 | [`reader/tools.py`](../../cutplan_agent/reader/tools.py) (tool 17개), [`reader/orchestrator.py`](../../cutplan_agent/reader/orchestrator.py) (루프, 세 가지 호출 방식, 기록) |

보여 주는 순서:

```bash
uv run python scripts/reader/show_trajectory.py runs/reader/agent/orchestrator/20261023-021136   # 모델이 무엇을 왜 불렀나
uv run python scripts/reader/show_stages.py runs/reader/agent/cone_0019 9-10                   # tool 이 실제로 낸 값 (main 의 stage-viewer 스크립트)
```

"지어낸 숫자 0" 은 마지막 보고(`answer.json`)의 숫자를 `trajectory.jsonl` 의 `run_stages` 결과와 하나씩 맞춰 본 것이다. 보고의 작은 지름 92 는 09 `unfold_params` 가 낸 값이고 정답은 100 이다. 이 실행에서 모델의 판단은 세 번이고, 처음부터 끝까지 그대로 돌리는 명령이라 고정 순서 `run.py` 와 하는 일이 같다.

## 6. 설계 판단

- **대화형이 아니라 명령 1회 처리기다.** 평가하려면 같은 명령을 같은 조건으로 다시 돌릴 수 있어야 하고, 실행 하나가 기록 폴더 하나로 끝나야 비교가 쉽다. 이어서 일하는 데 필요한 상태는 대화가 아니라 작업 폴더의 단계 파일에 있다. 대화형이 필요하면 같은 backend 에 사용자 메시지를 덧붙이는 반복문만 더하면 된다.
- **MCP 를 쓰지 않는다.** tool 을 쓰는 프로그램이 이 orchestrator 하나뿐이고, tool 은 같은 프로세스의 파이썬 함수다. 로컬 모델에 MCP 를 붙여도 결국 host 가 모델의 tool calling 형식으로 바꿔 넘긴다. Claude Code 같은 다른 클라이언트에서 같은 단계를 부르고 싶어지면, `ReaderTools` 의 tool 목록을 MCP 서버로 감싸면 된다 (이름, 설명, schema, 호출 함수가 이미 있다).
- **`tool_runner` 대신 루프를 직접 쓴다.** 세 방식이 같은 루프, 같은 기록 형식을 써야 Claude 와 로컬 모델을 같은 조건에서 비교할 수 있다.

## 7. 다음 할 일

- 추론 서버를 tool parser 와 함께 띄워 `native` 모드를 확인하고, 되면 `vllm_common.sh` 기본값에 넣는다.
- 고정 순서 `run.py` 와 orchestrator 를 합성 30장에서 비교한다 (단계 결과가 같은지, 턴 수, 시간, 토큰).
- 모델 오류(`model_calls` 의 ok=false)나 review 가 있을 때 다시 묻기 같은 보완 장치를 orchestrator 가 쓰게 할지 정한다 (로드맵 5번).
