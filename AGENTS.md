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

## 3. 레포 구조와 출처

| 경로 | 출처 |
|---|---|
| `cutplan_agent/` | 전임자의 v2 skill 에이전트. refactor 작업으로 uv 패키지가 됐다 |
| `cutplan_agent/unfold.py` | 툴킷의 `tools/dwg2png/vlm/unfold.py` 를 옮김 (db70044, 줄바꿈만 LF) |
| `cutplan_agent_v3/` | 동료 커밋 253020c 그대로 (subtree merge 1ea7cc6) |
| `scripts/` | 동료 커밋 148e703 그대로, pyc 만 제외 (b82ebe8) |
| `skills/` | 동료 zip 의 skills 폴더 그대로 (5f45c38). 동료 실행 기록의 sha256 과 일치 |
| 태그 `archive/cutplan_v3`, `archive/data_script` | 통합 전 원격 브랜치 상태 |

- `cutplan_agent_v3/` 는 패키지가 아니다. `python cutplan_agent_v3/main.py` 처럼 파일로 실행한다. 한 단계 위의 `skills/` 와 `data_v3/` 를 읽으므로, 레포 루트가 동료 서버의 `PBL_2026/` 폴더 역할을 한다.
- `scripts/` 는 아직 `D:\노바투스2026` 경로와 `manifest.csv` 의 역슬래시 경로를 가정한다. Linux 에서 그대로 실행하면 현재 폴더에 Windows 경로 이름의 폴더를 만들고 실패한다.

## 4. git 제외 데이터 (레포 루트 기준)

| 경로 | 크기 | 출처 | 쓰는 곳 |
|---|---|---|---|
| `Data/` | 1.4G | 노바투스2026.zip 의 `Data/` | cutplan_agent, scripts |
| `test_data/` | 712M | `scripts/build_test_data.py` 로 `Data/dataset` 에서 생성 | cutplan_agent 평가 |
| `data_v3/synthetic/` | 3.1M | 동료 서버에서 rsync. 합성 DXF + label.json 30개 | v3 입력 |
| `cutplan_agent_v3/examples/` | 3.6M | zip | v3 단위 테스트 |
| `cutplan_agent_v3/output/`, `cutplan_agent_v3/data_v3_claude_batch_10141611/` | 70M | zip | 동료 실행 결과, 비교 기준 |
| `tools/dwg2png/` | 65M | 동료에게 받은 툴킷 | Windows 의 `dwg2dxf.exe` 만 코드가 쓴다 |
| `skills/04_reading_records/` | 44K | zip | 코드가 읽지 않는다 |
| `runs/` | | 실행 산출물 | |

## 5. 실행 환경

- 2026-10-21 부터 작업은 GPU 가 있는 원격 서버에서 한다. 그 전 정리는 로컬 `/home/unist/developer/pbl` 에서 했다.
- cutplan_agent: Python 3.12 이상, `uv sync` 후 `uv run python -m cutplan_agent.eval.smoke_kd25038`. 기대 결과는 22/22 배치, 총 6125.0 kg 이다.
- v3: `cutplan_agent_v3/requirements.txt` 와 vllm 이 깔린 파이썬으로 `cd cutplan_agent_v3 && ./experiments.sh --python <파이썬>`. 기본값은 DeepSeek-OCR-2 (GPU 4, 포트 8000) 와 Qwen3.6-27B (GPU 5, 포트 8001) 이다.
- v3 기준값: 동료의 2026-10-18 실행 `cutplan_agent_v3/output/deepseek_ocr_qwen_reasoning_skills` 가 형상 분류 30개 중 27개를 맞췄다. `xgrammar_batch` 의 29/30 은 v2 코드 결과다.
- 동료 서버 구성 (출력 JSON 의 절대 경로에서 추론. 접속한 적은 없다): `/home/hwang/yechanhwang/PBL_2026/` 아래에 `cutplan_agent_v3`, `cutplan_agent_v2`, `skills`, `data_v3`, `pbl` 이 있었다. `pbl` 은 vllm 이 설치된 Python 3.10 가상환경이다.
- v3 의 `--no-vlm` 모드와 OCR 폴백 테스트는 tesseract 바이너리가 필요하다.
- DWG 입력을 읽으려면 `dwg2dxf` 가 필요하다. Ubuntu 24.04 apt 에는 없으므로 GNU LibreDWG 를 소스에서 빌드한다.

## 6. 알려진 상태와 할 일 (2026-10-21)

- v3 단위 테스트 83건 중 13건이 실패한다. 동료가 올린 상태 그대로다. tesseract 미설치 7건, 실험 스크립트 GPU 기본값과 어긋난 테스트 2건, 원인 미확인 4건이다. 미확인 4건은 `test_dxf_layer_adapter`, `test_two_up_cutting_plan_yields_nine_captioned_plates`, `test_cli_analyze_only_and_reconstruct`, `test_cli_image_end_to_end` 이다.
- smoke test 의 t10 중량이 README 4절의 2026-10-01 기록과 다르다. 기록은 5,657 kg, 현재는 5,828 kg 이다. 수정 전 코드에 툴킷을 붙여도 같으므로 이후 변경 때문은 아니다. 원인은 모른다.
- Google Drive 원본은 일부만 처리돼 있다. 커팅플랜은 있는데 입력 도면이 없는 KDM 워크오더가 21개다.
- cutplan_agent 의 VLM 경로(L1·L2)는 README 기준으로 한 번도 실행된 적이 없다.
- 할 일: scripts 경로 리팩터링(별도 브랜치), v3·scripts 의존성의 pyproject 이전, `cutplan_agent/knowledge/` 와 `skills/01_core_knowledge/` 중복 정리, 원격의 옛 브랜치 `cutplan_v3`·`data_script`·`refactor` 삭제.
