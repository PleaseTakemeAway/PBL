# AGENTS.md

이 레포에서 일하는 코딩 에이전트를 위한 규칙과 맥락이다. 2026-10-21 에 쓰고 2026-10-22, 2026-10-23 에 고쳤다.

## 1. 비밀 정보 (절대 규칙)

- `.env`, `.env.*`, `~/.ssh/*`, 자격 증명·토큰 파일은 열지도, 파싱하지도 않는다.
- "키 이름만 보는" awk·sed·cut 도 금지한다. 파일이 `이름=값` 형식이 아니면 값이 그대로 출력된다. 실제로 이 방식 때문에 API 키가 대화에 노출된 사고가 있었다.
- 설정 여부는 고정된 단어만 출력하는 명령으로만 확인한다.
  `grep -q '^ANTHROPIC_API_KEY=.' .env && echo set || echo unset`
- 형식이 불확실하면 파일을 보지 말고 사용자에게 묻는다.
- `.env` 는 `ANTHROPIC_API_KEY=<키>` 형식이어야 코드가 읽는다. 한 줄에 키 값만 두면 읽히지 않는다.
- 이 레포는 public 이다. 데이터, 고객 도면, 판독 기록, 키를 커밋하지 않는다.

## 2. 작업 원칙

- 최종 목표는 orchestration 과 각 작업을 모두 로컬 LLM 이 맡는 하네스다 (`docs/harness_engineering.md`). 모델이 하는 일은 좁은 판단으로 나누고, 계산은 코드가 하고, 단계마다 입출력을 파일로 남긴다. 로드맵을 진행하면 그 문서의 표를 고친다.
- "정리"는 git 구조만이 아니라 이 환경에서 실제로 돌게 만드는 리팩터링까지 포함한다. 하드코딩 경로, 역슬래시 경로, 빠진 의존성이 대상이다.
- 동료와 협업하는 프로젝트다. 동료가 출장 중인 동안 사용자가 이어서 개발하고, 지금은 인수인계를 겸해 코드 정리와 리팩터링을 하고 있다. 동료가 돌아와 무엇이 바뀌었는지 볼 수 있게 동료의 원래 상태는 커밋과 태그로 재현할 수 있게 둔다.
- 사용자는 동료의 작업을 먼저 그대로 돌려 보고 필요한 것을 파악한 뒤에 바꾸길 원한다. 리팩터링은 별도 브랜치나 분리된 커밋으로 한다.
- 결과가 바뀌면 안 되는 변경은 전후를 비교해 확인하고, 그 근거를 커밋 메시지에 적는다. 비교 대상은 smoke test 출력 전체, v3 단위 테스트의 실패 목록, 레포 루트에서 `PYTHONPATH=. python cutplan_agent/reader/main.py --batch --input-mode dxf --no-vlm --output-dir <폴더> data_v3/synthetic` 의 출력이다. 이 출력은 출력 폴더 경로와 시각을 빼면 실행마다 같다. 입력 경로는 출력에 그대로 기록되므로 비교할 두 실행은 같은 경로 표기로 돌린다. 2026-10-22 (`reader-stages`) 부터 이 출력에는 도면마다 `stages/` 가 생기므로, 그 전 출력과 비교할 때는 `stages/` 를 뺀다.
- git 밖에서 가져온 파일은 출처와 동일하다는 근거를 함께 남긴다. 예를 들면 diff 결과나 sha256 이다.
- 사용자는 에이전트의 세션 기록을 다시 볼 수 없다. 사용법, 실행 명령, 옵션이 왜 그렇게 동작하는지, 판단 근거와 확인한 결과는 대화로만 답하지 말고 `docs/` 의 해당 문서에 적는다. 명령은 그대로 붙여 넣어 돌 수 있게 쓴다 (reader 는 `docs/reader/quickstart.md`, 실행 일반은 `docs/getting_started.md`). 실행 방법을 바꾸는 커밋에는 문서 수정을 같이 넣는다.

## 3. 코드 스타일

- Python 코드는 `ruff format` 형식에 맞춰 작성하고, `ruff check` 를 통과하게 한다. 검사하는 규칙은 `pyproject.toml` 의 `[tool.ruff.lint] select` 에 있다: F(안 쓰는 import·변수 등), I(import 정렬), TID252(상대 import 금지), UP009(coding 선언 금지). 포맷은 ruff 기본값(줄 길이 88, 큰따옴표)이다.
- ruff 는 dev 의존성으로 0.17.1 에 고정돼 있다. 버전마다 결과가 달라질 수 있으니 `uvx ruff` 나 전역 ruff 대신 `uv run ruff` 를 쓴다.
- 파일을 고친 뒤 `uv run ruff check --fix <파일>` 와 `uv run ruff format <파일>` 를 차례로 돌린다. 커밋 전에 `uv run ruff check .` 와 `uv run ruff format --check .` 가 둘 다 통과해야 한다.
- 상대 import(`from .x import`, `from ..x import`)는 쓰지 않는다. `from cutplan_agent.skills.l1_perception import vlm_parse` 처럼 레포 루트부터 쓴다. 파일을 직접 실행하면 상대 import 가 깨진다. `TID252` 가 이를 잡는다.
- `__init__.py` 를 만들지 않는다. `cutplan_agent` 는 설치하지 않는 namespace package 이고, 레포 루트에서 `PYTHONPATH=. uv run python <파일 경로>` 로 실행한다. `python -m` 은 쓰지 않는다.
- `cutplan_agent/skills/` 의 skill 함수는 JSON 직렬화 가능한 인자를 받아 dict 를 돌려준다. orchestrator 가 이 함수를 그대로 Claude tool 로 노출한다.
- `.md` 는 포맷하지 않는다. ruff 가 마크다운 안의 코드 블록까지 고쳐서 `skills/` 의 sha256 일치가 깨진다. `pyproject.toml` 의 `extend-exclude` 로 제외해 두었다.
- 포맷만 한 커밋은 `.git-blame-ignore-revs` 에 해시를 적는다. 로컬 blame 에 반영하려면 `git config blame.ignoreRevsFile .git-blame-ignore-revs` 를 한 번 설정한다.
- 2026-10-22 에 레포의 `.py` 전체를 한 번 포맷하고 import 를 정렬했다. docstring 들여쓰기와 import 블록 안의 순서를 빼면 AST 가 같아 동작은 바뀌지 않았다. 동료 원본(v3, `scripts/`)의 바이트 단위 상태는 4절 표의 커밋과 태그에서 본다.
- 포맷 변경은 로직 변경과 같은 커밋에 섞지 않는다.

## 4. 레포 구조와 출처

| 경로 | 출처 |
|---|---|
| `cutplan_agent/` | 제품 패키지. 바로 아래의 `agent/`, `skills/`, `eval/`, `config.py` 등은 동료의 v2 skill 에이전트 (최초 커밋 f51473f). refactor 작업으로 uv 프로젝트가 됐고, 패키지로 설치하지 않는다. `eval/cp_parse.py`, `eval/drawing_refs.py` 는 이 레포에서 썼다 (2026-10-23) |
| `cutplan_agent/unfold.py` | 툴킷의 `tools/dwg2png/vlm/unfold.py` 를 옮김 (db70044, 줄바꿈만 LF) |
| `cutplan_agent/reader/`, `cutplan_agent/reconstruct/` | 동료의 v3 (커밋 253020c, subtree merge 1ea7cc6). 268b42e 에서 `cutplan_agent_v3/` 를 역할별로 나눠 옮겼다. reader 는 도면 판독·전개도·CLI, reconstruct 는 3D 복원이다 |
| `cutplan_agent/reader/stages/` | 이 레포에서 만들었다 (2026-10-22, `reader-stages`). `--batch --input-mode dxf` 가 부르는 판독 13단계와, 그 앞에서 DWG 를 DXF 로 바꾸는 선택 단계 00 `convert` (2026-10-23, `dwg-input`). 사용법은 `docs/reader/stages.md` |
| `cutplan_agent/reader/tools.py`, `cutplan_agent/reader/orchestrator.py` | 이 레포에서 만들었다 (2026-10-23, `reader-agent`). 판독 13단계(`STAGES`)를 tool 로 노출하고 모델이 자연어 명령에 따라 부른다. 00 `convert` 는 tool 이 아니다. 사용법은 `docs/reader/orchestrator.md` |
| `tests/`, `experiments/`, `docs/reader/` | 같은 v3 의 단위 테스트, 실험 스크립트, 문서. 268b42e 에서 옮겼다. `tests/test_stages.py`, `tests/test_cp_parse.py`, `tests/test_l3_formulas.py`, `tests/test_reader_tools.py`, `tests/test_orchestrator.py`, `tests/test_build_synthetic.py`, `docs/reader/stages.md`, `docs/reader/orchestrator.md`, `experiments/serve.sh`, `experiments/vllm_common.sh` 는 이 레포에서 썼다. `vllm_common.sh` 는 동료의 `experiments.sh` 에서 옮긴 코드다 (a2c06a3) |
| `presentation/` | 이 레포에서 만들었다 (2026-10-23, `presentation`). 발표 슬라이드를 만드는 스크립트. pptx 는 스크립트로 만들고 커밋하지 않는다. 사용법은 `docs/presentation.md` |
| `scripts/` | 동료 커밋 148e703, pyc 만 제외 (b82ebe8). 이후 정리 내역은 `git log -- scripts`. `scripts/build_synthetic.py` (합성 도면 생성기)와 `scripts/synthetic_figures.py` 는 이 레포에서 썼다 (2026-10-27, `docs/data/synthetic.md`). `scripts/reader/` 는 이 레포에서 썼다 (2026-10-23): reader 단계를 번호로 골라 돌리고 (`run_stages.py`) 결과를 표와 그림으로 보여 준다 (`show_stages.py`). orchestrator 실행 기록을 읽기 좋게 출력한다 (`show_trajectory.py`). 배치 출력을 합성 정답과 단계별로 채점한다 (`score_synthetic.py`, 2026-10-27) |
| `skills/` | 동료 zip 의 skills 폴더 (5f45c38). 코드가 읽는 `02_prompts/` 는 그대로이고 동료 실행 기록의 sha256 과 일치한다. `01_core_knowledge/` 는 2026-10-23 에 회사 담당자의 계산 문서 `shell_cone_head_unfold.md` 를 더하고 (녹음 정리본 원문은 b399b4d, 같은 날 기준 문서 형식으로 다시 썼다) `unfold_rules.md`·`site_constants.md` 를 그 문서에 맞춰 고쳤다. 그 전 상태는 5a710f6, 동료 실행 기록과 sha256 이 맞는 판이다. 같은 날 S-2120 부품표 대조(`docs/v4.md`, 2026-10-27 에 지웠다. `git show c71cca0:docs/v4.md`)로 `drawing_conventions_kr.md`·`nesting_rules.md` 에 품번과 커팅플랜 부품 라벨의 대응, 판재가 아닌 행을 더했다. 사람용 문서(`README.md`, `03_reference/`)는 2026-10-22 에 내용 그대로 `docs/` 로 옮겼다 |
| `docs/` | 사람이 읽는 문서 전부. 목차는 `docs/README.md`. `README.md`, `harness_engineering.md`, `v3_upgrade.md`, `data/synthetic.md` (그림 `data/synthetic/*.png` 은 `scripts/synthetic_figures.py` 가 그린다), `getting_started.md`, `execution_flow.md`, `data/overview.md`, `data/cutplan_cases.md`, `agent/skills.md`, `reader/stages.md`, `reader/quickstart.md`, `reader/orchestrator.md`, `domain/company_questions.md`, `presentation.md`, `company_brief.md` 는 이 레포에서 썼다. 실행 방법, 진입점, 호출 순서, 데이터 흐름을 바꾸면 해당 문서를 같이 고친다 |
| 태그 `archive/cutplan_v3`, `archive/data_script` | 통합 전 원격 브랜치 상태. 브랜치 `cutplan_v3`·`data_script`·`refactor` 는 2026-10-22 에 원격에서 지웠다 (`refactor` 는 main 에 다 들어 있다) |
| 태그 `archive/reader-stages-7stage` | 다른 서버에서 같은 요청으로 만든 7단계 판 `reader-stages` (46fd37a). main 에는 13단계 판을 머지했다 |

- 사람이 읽는 문서는 `docs/` 아래에만 둔다. 예외는 코드가 실행 중에 읽는 문서(`skills/`, `cutplan_agent/knowledge/`, `cutplan_agent/agent/system.md`), 도구가 루트에서 찾는 `AGENTS.md`·`CLAUDE.md`, 짧은 소개만 두는 루트 `README.md` 다.
- 폴더는 하는 일로 이름을 짓고, 버전은 git 으로 관리한다. `_v3` 같은 버전 폴더나 복사본을 만들지 않는다. 옛 상태는 커밋과 태그로 꺼낸다. 동료의 v3 원본은 253020c, 폴더를 옮기기 직전은 ca142a8 이다.
- reader 도 레포 루트에서 `PYTHONPATH=. python cutplan_agent/reader/main.py ...` 로 실행한다. 단계 스크립트도 같다: `PYTHONPATH=. python cutplan_agent/reader/stages/<단계>.py <작업 폴더>`. `knowledge.py` 는 레포 루트의 `skills/` 를, `experiments/*.sh` 는 `data_v3/synthetic` 과 `runs/reader/` 를 기본값으로 쓴다.
- `scripts/` 의 경로는 `cutplan_agent.config` 의 프로젝트 루트(또는 `CUTPLAN_ROOT`) 기준이다. 레포 루트에서 `PYTHONPATH=. uv run python scripts/<이름>.py` 로 실행한다. Windows PowerShell 은 먼저 `$env:PYTHONPATH = "."` 를 실행한다. `manifest.csv` 의 경로는 슬래시로 쓰고, 예전 역슬래시 경로도 읽는다. 동료 원본 스크립트는 b82ebe8 시점의 것이다.

## 5. git 제외 데이터 (레포 루트 기준)

| 경로 | 크기 | 출처 | 쓰는 곳 |
|---|---|---|---|
| `Data/` | 1.4G | 노바투스2026.zip 의 `Data/` | cutplan_agent, scripts |
| `test_data/` | 729M | `scripts/build_test_data.py` 로 `Data/dataset` 에서 생성 | cutplan_agent 평가 |
| `test_data/cutting_plan/` | | 회사 담당자에게 받은 설비 2개 (S-2120, D-1203) 의 설계 도면과 커팅플랜 (2026-10-22). 2026-10-23 00:59 쯤 지워져 `mlic` 에는 없다. 받은 파일은 `test_data/cases/` 에 sha256 이 `source.csv` 와 같은 사본으로 남아 있어, 그 사본으로 되살린다 (`docs/data/cutplan_cases.md` 4절) | `scripts/build_cutplan_cases.py` |
| `test_data/cases/` | 14M | `scripts/build_cutplan_cases.py` 로 `test_data/cutting_plan` 에서 생성 (`docs/data/cutplan_cases.md`) | 실도면 평가 (아직 쓰는 코드 없음) |
| `data_v3/synthetic/` | 3.1M | 동료 서버에서 rsync. 합성 DXF + label.json 30개. 콘·헤드·굽힘판 정답이 회사 계산 기준과 다르다 (`docs/data/synthetic.md` 5절) | v3 기본 입력 |
| `data_v3/generated/` | 4.3M | `scripts/build_synthetic.py` 로 생성 (2026-10-27). 같은 30장을 회사 기준 정답으로 | 아직 기본 입력이 아니다 |
| `tests/fixtures/` | 3.6M | zip 의 `cutplan_agent_v3/examples/`. 고객 도면이 들어 있다. `mlic` 에는 없다 | 단위 테스트 |
| `runs/reader/` | 89M | zip 의 `cutplan_agent_v3/output/*` 와 `data_v3_claude_batch_10141611/` (70M), 그 뒤 `mlic` 에서 돌린 판독 결과 | 동료 실행 결과, 비교 기준 |
| `tools/dwg2png/` | 65M | 동료에게 받은 툴킷. `mlic` 에는 레포 밖 `~/dwg2png` 에 있다 (2026-10-23 확인) | Windows 의 `dwg2dxf.exe` 만 코드가 쓴다 |
| `skills/04_reading_records/` | 44K | zip. `mlic` 에는 없다 | 코드가 읽지 않는다 |
| `Data/drive/8. Data/` | | Google Drive 원본을 푸는 위치. 아직 없다 | `scripts/ingest_drive_inputs.py` |
| `runs/render_drawings/kdm_input/` | | `scripts/render_drawings.py` 를 `Data/dataset/KDM/*/*/input` 에 돌린 결과 (2026-10-23). PNG 와 변환 실패 목록 `render_failures.txt`, 엑셀용 `render_failures_summary.tsv` | `presentation/build_dwg_dxf.py` 의 부록 |
| `runs/` | | 실행 산출물 | |

## 6. 실행 환경

- 2026-10-21 부터 작업은 GPU 가 있는 원격 서버에서 한다. 그 전 정리는 로컬 `/home/unist/developer/pbl` 에서 했다.
- cutplan_agent: Python 3.12 이상, `uv sync` 후 `PYTHONPATH=. uv run python cutplan_agent/eval/smoke_kd25038.py`. 기대 결과는 22/22 배치, 총 6132.2 kg 이다. 2026-10-23 에 헤드 원판 식을 회사 계산 문서 식으로 바꾸기 전에는 6125.0 kg 이었다.
- 작업 서버(호스트 `mlic`)는 RTX A5000 24GB 4장(GPU 0–3)이고 NVIDIA 드라이버는 535(CUDA 12.2)다. PyPI 기본 vLLM·torch 는 CUDA 13 용이라 이 드라이버에서 돌지 않는다. vLLM 0.31.0+cu129 환경을 `~/venvs/vllm-0.31` 에 만들어 두었고, 만드는 법은 `docs/getting_started.md` 3절에 있다.
- v3 (reader): 판독기 의존성(`requests`, `opencv-python-headless`, `pytesseract`)은 2026-10-23 에 pyproject 로 옮겨서 `PYTHONPATH=. uv run python cutplan_agent/reader/...` 로 돈다. 로컬 모델 실험은 `experiments/requirements.txt` 와 vllm 이 깔린 파이썬으로 레포 루트에서 `./experiments/experiments.sh --python <파이썬> --vllm-bin <vllm>`. 기본값은 DeepSeek-OCR-2 (GPU 0, 포트 8000) 와 Qwen3.6-27B (GPU 1,2,3 pipeline parallel, 포트 8001) 로, 작업 서버에 맞춘 것이다. 동료는 90GB 급 GPU 한 장씩(GPU 4, 5)을 썼다.
- 서버를 띄워 두고 여러 번 돌릴 때는 `./experiments/serve.sh --vllm-bin <vllm>` 로 서버만 띄운다 (Ctrl-C 까지 유지). 다른 셸에서 `. runs/vllm/ocr.env; . runs/vllm/reason.env` 를 하면 `main.py`, 단계 스크립트, `experiments.sh` 가 그 서버를 쓴다. `experiments.sh` 와 `serve.sh` 의 역할 설정과 서버 기동 코드는 `experiments/vllm_common.sh` 에 한 벌만 있다.
- v3 기준값: 동료의 2026-10-18 실행 `runs/reader/deepseek_ocr_qwen_reasoning_skills` 가 형상 분류 30개 중 27개를 맞췄다. `xgrammar_batch` 의 29/30 은 v2 코드 결과다.
- 동료 서버 구성 (출력 JSON 의 절대 경로에서 추론. 접속한 적은 없다): `/home/hwang/yechanhwang/PBL_2026/` 아래에 `cutplan_agent_v3`, `cutplan_agent_v2`, `skills`, `data_v3`, `pbl` 이 있었다. `pbl` 은 vllm 이 설치된 Python 3.10 가상환경이다.
- 이미지 입력의 `--no-vlm` 과 OCR 폴백 테스트는 tesseract 바이너리가 필요하다. DXF 입력의 `--no-vlm` 배치는 tesseract 없이 돈다.
- DWG 입력을 읽으려면 `dwg2dxf` 가 필요하다. Ubuntu 22.04·24.04 apt 에는 없으므로 `scripts/install_libredwg.sh` 로 GNU LibreDWG 0.14 를 `~/.local` 에 빌드한다. 2026-10-23 에 확인했을 때 `mlic` 에는 없어서 이 스크립트로 `~/.local/bin/dwg2dxf` 에 설치했다. 동료 툴킷의 Windows `dwg2dxf.exe` 도 0.14 다.
- 사람이 볼 도면 PDF·PNG 는 `scripts/render_drawings.py` 로 만든다. 에이전트 코드를 import 하지 않는 독립 스크립트다.
- `mlic` 에는 시스템 한글 폰트가 없다 (2026-10-23 `fc-list :lang=ko` 빈 결과). 나눔고딕을 `~/.local/share/fonts/nanum/` 에 받아 두었다. ezdxf 는 폰트 캐시를 따로 두므로 `uv run ezdxf --fonts` 로 캐시를 다시 만들기 전에는 `render_drawings.py` 가 한글 폰트를 찾지 못했다고 경고하고 한글을 네모로 그린다. 발표 슬라이드 미리보기(`presentation/render.py`)는 이 나눔고딕을 쓴다.
- LibreDWG 0.14 의 한계 (2026-10-22, `Data/dataset/KDM` 기준): 커팅플랜 DWG 67개는 모두 읽고, 동료가 Windows 에서 만든 DXF 와 헤더 날짜·정수 부호 표기만 다르다. 입력 도면 DWG 536개 중 87개는 읽지 못한다. 77개는 오류를 내고도 종료 코드 0 으로 빈 DXF 를 쓰고 (DWG 버전은 R2007 76개, R2004 1개), 10개는 ezdxf 가 열지 못하는 DXF 를 쓴다. 87개 중 47개는 같은 이름의 PDF 가 옆에 있다. 2026-10-23 에 다시 돌려 같은 수를 얻었고, 목록은 `runs/render_drawings/kdm_input/render_failures_summary.tsv` 에 있다. 일부 도면은 글자 뒤에 실행마다 다른 쓰레기 바이트를 붙여 DXF 가 실행마다 조금씩 다르다. v2 의 `ingest_drawing` 도 같은 dwg2dxf 를 쓰므로 이 도면들에서 같은 문제를 겪는다. 회사에서 받은 D-1203 입력 DWG 6개도 DXF 를 TABLES 구간까지만 쓰고 멈춰 ezdxf 가 열지 못한다. 같은 이름의 PDF 가 있다.

## 7. 알려진 상태와 할 일 (2026-10-23)

- 단위 테스트는 120건이다: 동료의 v3 테스트 88건과 이 레포에서 쓴 `test_stages.py` 7건, `test_cp_parse.py` 5건, `test_l3_formulas.py` 8건, `test_reader_tools.py` 3건, `test_orchestrator.py` 2건, `test_build_synthetic.py` 7건. 이 레포의 32건은 모두 통과한다. v3 88건은 `tests/fixtures/` 가 있고 tesseract 가 없던 로컬(2026-10-21)에서 11건이 실패했다. tesseract 미설치 7건, 원인 미확인 4건이다. 동료가 올린 상태에서는 실험 스크립트 GPU 기본값과 어긋난 테스트 2건도 실패했는데, 2026-10-22 에 기본값을 GPU 0 / 1,2,3 으로 바꾸면서 고쳤다. `tests/fixtures/` 와 tesseract 가 둘 다 없는 `mlic` 에서는 17건이 실패한다 (2026-10-23 확인, 모두 v3 테스트). 미확인 4건은 `test_dxf_layer_adapter`, `test_two_up_cutting_plan_yields_nine_captioned_plates`, `test_cli_analyze_only_and_reconstruct`, `test_cli_image_end_to_end` 이다.
- smoke test 의 t10 중량이 `docs/agent/skills.md` 2절의 2026-10-01 기록과 다르다. 기록은 5,657 kg, 2026-10-21 에는 5,828 kg 이었다. 수정 전 코드에 툴킷을 붙여도 같으므로 이후 변경 때문은 아니다. 원인은 모른다. 2026-10-23 에 헤드 원판 식을 바꾼 뒤에는 5,835.2 kg 이다 (총 6132.2 kg 과 같은 실행).
- Google Drive 원본은 일부만 처리돼 있다. 커팅플랜은 있는데 입력 도면이 없는 KDM 워크오더가 21개다.
- cutplan_agent 의 VLM 경로(L1·L2)는 `docs/agent/skills.md` 기준으로 한 번도 실행된 적이 없다.
- `test_data/` 는 입력 도면이 정답을 다 설명하지 못한다. 2026-10-23 기준으로 정답 부품 라벨에서 도면 번호를 읽은 1,605개 중 638개가 입력에 없는 도면을 가리킨다. 이 수는 `scripts/build_test_data.py` 가 `index.csv` 에 쓰는 `parts_ref_missing` 열에서 나오는데, 임시 폴더에서 돌려 얻은 값이다 (24f624d). `mlic` 의 `test_data/` 는 2026-10-21 판이라 `index.csv` 에 이 열이 없다. 입력과 정답이 짝지어진 실도면 세트는 `test_data/cases/` 의 2건이다 (`docs/data/cutplan_cases.md`). `tests/test_cp_parse.py` 의 5건은 통과한다.
- 2026-10-27 에 목표를 v3 고도화로 바꿨다. 합성 도면 생성기를 레포에 다시 쓰고 검증한 뒤, 합성 30장(`data_v3/synthetic`)을 모든 단계에서 정답과 맞게 완주한다. 실도면 작업(v4)은 이 브랜치에서 지웠다 (`git show c71cca0:docs/v4.md`). 기준, 계획, 합성 도면의 이상한 점 목록은 `docs/v3_upgrade.md`. 작업 브랜치는 `synthetic` 이다.
- 할 일: `docs/harness_engineering.md` 3절의 로드맵 (단계별 평가 → 작업별 모델 설정 → Claude 대 로컬 비교 → 보완 장치 → 로컬 orchestrator), `cutplan_agent/knowledge/` 와 `skills/01_core_knowledge/` 중복 정리.
