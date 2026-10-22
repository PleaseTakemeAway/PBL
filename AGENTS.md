# AGENTS.md

이 레포에서 일하는 코딩 에이전트를 위한 규칙과 맥락이다. 2026-10-21 기준으로 썼다.

## 1. 비밀 정보 (절대 규칙)

- `.env`, `.env.*`, `~/.ssh/*`, 자격 증명·토큰 파일은 열지도, 파싱하지도 않는다.
- "키 이름만 보는" awk·sed·cut 도 금지한다. 파일이 `이름=값` 형식이 아니면 값이 그대로 출력된다. 실제로 이 방식 때문에 API 키가 대화에 노출된 사고가 있었다.
- 설정 여부는 고정된 단어만 출력하는 명령으로만 확인한다.
  `grep -q '^ANTHROPIC_API_KEY=.' .env && echo set || echo unset`
- 형식이 불확실하면 파일을 보지 말고 사용자에게 묻는다.
- `.env` 는 `ANTHROPIC_API_KEY=<키>` 형식이어야 코드가 읽는다. 한 줄에 키 값만 두면 읽히지 않는다.
- 이 레포는 public 이다. 데이터, 고객 도면, 판독 기록, 키를 커밋하지 않는다.

## 2. 작업 원칙

- "정리"는 git 구조만이 아니라 이 환경에서 실제로 돌게 만드는 리팩터링까지 포함한다. 하드코딩 경로, 역슬래시 경로, 빠진 의존성이 대상이다.
- 사용자는 동료(전임자)의 작업을 먼저 그대로 돌려 보고 필요한 것을 파악한 뒤에 바꾸길 원한다. 동료의 원래 상태를 재현할 수 있게 두고, 리팩터링은 별도 브랜치나 분리된 커밋으로 한다.
- git 밖에서 가져온 파일은 출처와 동일하다는 근거를 함께 남긴다. 예를 들면 diff 결과나 sha256 이다.

## 3. 코드 스타일

- Python 코드는 `ruff format` 형식에 맞춰 작성하고, import 는 ruff 의 isort 규칙(`I`)대로 정렬한다. 설정은 ruff 기본값(줄 길이 88, 큰따옴표)이다.
- ruff 는 dev 의존성으로 0.17.1 에 고정돼 있다. 버전마다 결과가 달라질 수 있으니 `uvx ruff` 나 전역 ruff 대신 `uv run ruff` 를 쓴다.
- 파일을 고친 뒤 `uv run ruff check --select I --fix <파일>` 로 import 를 정렬하고 `uv run ruff format <파일>` 로 포맷한다. 커밋 전에 `uv run ruff check --select I,TID252 .` 와 `uv run ruff format --check .` 가 둘 다 통과해야 한다.
- 상대 import(`from .x import`, `from ..x import`)는 쓰지 않는다. `from cutplan_agent.skills.l1_perception import vlm_parse` 처럼 레포 루트부터 쓴다. 파일을 직접 실행하면 상대 import 가 깨진다. `TID252` 가 이를 잡는다.
- `.md` 는 포맷하지 않는다. ruff 가 마크다운 안의 코드 블록까지 고쳐서 `skills/` 의 sha256 일치가 깨진다. `pyproject.toml` 의 `extend-exclude` 로 제외해 두었다.
- 포맷만 한 커밋은 `.git-blame-ignore-revs` 에 해시를 적는다. 로컬 blame 에 반영하려면 `git config blame.ignoreRevsFile .git-blame-ignore-revs` 를 한 번 설정한다.
- 2026-10-22 에 레포의 `.py` 전체를 한 번 포맷하고 import 를 정렬했다. docstring 들여쓰기와 import 블록 안의 순서를 빼면 AST 가 같아 동작은 바뀌지 않았다. 동료 원본(`cutplan_agent_v3/`, `scripts/`)의 바이트 단위 상태는 4절 표의 커밋과 태그에서 본다.
- 포맷 변경은 로직 변경과 같은 커밋에 섞지 않는다.

## 4. 레포 구조와 출처

| 경로 | 출처 |
|---|---|
| `cutplan_agent/` | 전임자의 v2 skill 에이전트. refactor 작업으로 uv 패키지가 됐다 |
| `cutplan_agent/unfold.py` | 툴킷의 `tools/dwg2png/vlm/unfold.py` 를 옮김 (db70044, 줄바꿈만 LF) |
| `cutplan_agent_v3/` | 동료 커밋 253020c 그대로 (subtree merge 1ea7cc6) |
| `scripts/` | 동료 커밋 148e703 그대로, pyc 만 제외 (b82ebe8) |
| `skills/` | 동료 zip 의 skills 폴더 그대로 (5f45c38). 동료 실행 기록의 sha256 과 일치 |
| 태그 `archive/cutplan_v3`, `archive/data_script` | 통합 전 원격 브랜치 상태 |

- `cutplan_agent_v3/` 는 패키지가 아니다. `python cutplan_agent_v3/main.py` 처럼 파일로 실행한다. 한 단계 위의 `skills/` 와 `data_v3/` 를 읽으므로, 레포 루트가 동료 서버의 `PBL_2026/` 폴더 역할을 한다.
- `scripts/` 의 경로는 `cutplan_agent.config` 의 프로젝트 루트(또는 `CUTPLAN_ROOT`) 기준이다. Windows 와 Linux 모두 `uv run python scripts/<이름>.py` 로 실행한다. `manifest.csv` 의 경로는 슬래시로 쓰고, 예전 역슬래시 경로도 읽는다. 동료 원본 스크립트는 b82ebe8 시점의 것이다.

## 5. git 제외 데이터 (레포 루트 기준)

| 경로 | 크기 | 출처 | 쓰는 곳 |
|---|---|---|---|
| `Data/` | 1.4G | 노바투스2026.zip 의 `Data/` | cutplan_agent, scripts |
| `test_data/` | 712M | `scripts/build_test_data.py` 로 `Data/dataset` 에서 생성 | cutplan_agent 평가 |
| `data_v3/synthetic/` | 3.1M | 동료 서버에서 rsync. 합성 DXF + label.json 30개 | v3 입력 |
| `cutplan_agent_v3/examples/` | 3.6M | zip | v3 단위 테스트 |
| `cutplan_agent_v3/output/`, `cutplan_agent_v3/data_v3_claude_batch_10141611/` | 70M | zip | 동료 실행 결과, 비교 기준 |
| `tools/dwg2png/` | 65M | 동료에게 받은 툴킷 | Windows 의 `dwg2dxf.exe` 만 코드가 쓴다 |
| `skills/04_reading_records/` | 44K | zip | 코드가 읽지 않는다 |
| `Data/drive/8. Data/` | | Google Drive 원본을 푸는 위치. 아직 없다 | `scripts/ingest_drive_inputs.py` |
| `runs/` | | 실행 산출물 | |

## 6. 실행 환경

- 2026-10-21 부터 작업은 GPU 가 있는 원격 서버에서 한다. 그 전 정리는 로컬 `/home/unist/developer/pbl` 에서 했다.
- cutplan_agent: Python 3.12 이상, `uv sync` 후 `uv run python -m cutplan_agent.eval.smoke_kd25038`. 기대 결과는 22/22 배치, 총 6125.0 kg 이다.
- v3: `cutplan_agent_v3/requirements.txt` 와 vllm 이 깔린 파이썬으로 `cd cutplan_agent_v3 && ./experiments.sh --python <파이썬>`. 기본값은 DeepSeek-OCR-2 (GPU 4, 포트 8000) 와 Qwen3.6-27B (GPU 5, 포트 8001) 이다.
- v3 기준값: 동료의 2026-10-18 실행 `cutplan_agent_v3/output/deepseek_ocr_qwen_reasoning_skills` 가 형상 분류 30개 중 27개를 맞췄다. `xgrammar_batch` 의 29/30 은 v2 코드 결과다.
- 동료 서버 구성 (출력 JSON 의 절대 경로에서 추론. 접속한 적은 없다): `/home/hwang/yechanhwang/PBL_2026/` 아래에 `cutplan_agent_v3`, `cutplan_agent_v2`, `skills`, `data_v3`, `pbl` 이 있었다. `pbl` 은 vllm 이 설치된 Python 3.10 가상환경이다.
- v3 의 `--no-vlm` 모드와 OCR 폴백 테스트는 tesseract 바이너리가 필요하다.
- DWG 입력을 읽으려면 `dwg2dxf` 가 필요하다. Ubuntu 24.04 apt 에는 없으므로 GNU LibreDWG 를 소스에서 빌드한다.

## 7. 알려진 상태와 할 일 (2026-10-21)

- v3 단위 테스트 83건 중 13건이 실패한다. 동료가 올린 상태 그대로다. tesseract 미설치 7건, 실험 스크립트 GPU 기본값과 어긋난 테스트 2건, 원인 미확인 4건이다. 미확인 4건은 `test_dxf_layer_adapter`, `test_two_up_cutting_plan_yields_nine_captioned_plates`, `test_cli_analyze_only_and_reconstruct`, `test_cli_image_end_to_end` 이다.
- smoke test 의 t10 중량이 README 4절의 2026-10-01 기록과 다르다. 기록은 5,657 kg, 현재는 5,828 kg 이다. 수정 전 코드에 툴킷을 붙여도 같으므로 이후 변경 때문은 아니다. 원인은 모른다.
- Google Drive 원본은 일부만 처리돼 있다. 커팅플랜은 있는데 입력 도면이 없는 KDM 워크오더가 21개다.
- cutplan_agent 의 VLM 경로(L1·L2)는 README 기준으로 한 번도 실행된 적이 없다.
- 할 일: v3 의존성의 pyproject 이전, `cutplan_agent/knowledge/` 와 `skills/01_core_knowledge/` 중복 정리, 원격의 옛 브랜치 `cutplan_v3`·`data_script`·`refactor` 삭제.
