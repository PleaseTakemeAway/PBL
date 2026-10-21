# cutplan_agent — 도면 → 자재목록 → 전개·분할 → 네스팅 → POR 를 수행하는 VLM skill 에이전트

KDM 발표자료(`주차별_슬라이드/KDMTECH_발표자료_통합.pptx`, 2026-08-03)의 4계층 구분을 skill 분류의 뼈대로 썼다.
"OCR 은 무엇이 어디 적혀 있나까지. 무엇을 의미하고 무엇과 이어지나는 OCR 의 일이 아니다." — 이 경계가 L1 / L2 의 경계다.

## 1. Skill 분류 (25개 tool)

| 계층 | KDM 정의 | skill | 구현 | 비고 |
|---|---|---|---|---|
| **L1 인식** | OCR: 문자·위치·표 구조 → JSON | `ingest_drawing` DWG→DXF→PNG / PDF→PNG | ✅ 동작 | libredwg `dwg2dxf` + ezdxf 렌더 + PyMuPDF |
| | | `dxf_read_text` 벡터 텍스트·치수 좌표 추출 | ✅ 동작 | 정확한 숫자의 1차 출처. VLM 판독값과 교차검증 |
| | | `vlm_read_page(what=title_block/bom/design_data/dims/notes)` | 🔑 API 필요 | Claude structured output (pydantic 스키마) |
| | | `normalize_bom` 재질·두께·수량·단위·전개판정 | ✅ 동작 | 정규식 + 전개구분표 키워드 |
| **L2 관계·의미** | 심볼·연결관계·의미 매핑 (VLM 추론의 본체) | `classify_drawing` GA/BODY/NOZZLE/SADDLE/… | 🔑 | |
| | | `extract_design_data` GA 설계조건·재질표·노즐표 | 🔑 | 패드 치수 계산의 출처 (발표자료 10쪽 결론) |
| | | `extract_part_model` BOM 항목 → 3D 파라미터(PartSpec) | 🔑 | `skills/02_prompts/unfold_extract.md` 프롬프트. "따라 그리지 말고 형상을 읽어라" |
| | | `set_part_spec` 파라미터 직접 입력 | ✅ | KDM 접근 B(조각+스펙 입력) / HITL 경로 |
| | | `detect_split_lines` 용접선 배치도 → 코스·롱심 (RQ1) | 🔑 | |
| | | `resolve_missing_spec` 두께만 있는 패드 → 노즐표/관례 | ✅ | 추정값은 confidence=estimated → H2 |
| | | `load_domain_prompt(topic)` 도메인 지식 7종 | ✅ | `knowledge/*.md`. 언제 불러오는지도 정책의 일부 |
| **L3 계산·로직** | 규칙엔진 (검증 완료) | `unfold_part` 원통·원뿔·절곡·평판·헤드·패드 | ✅ | 절곡·평판은 `cutplan_agent/unfold.py` (툴킷에서 이전, 원통 공식 44건 역산 검증) + 헤드 블랭크·패드 링 추가 |
| | | `split_to_pieces` 판폭/길이·용접선 기준 분할 + 여유 | ✅ | 쉘 롱심/원주분할, 헤드 현 분할(오프셋), 콘 부채꼴 n 분할 |
| | | `nest_group` / `nest_all` shelf 배치, 멀티규격·맞춤 길이 | ✅ | bbox 기반. 목적함수 4종 비교 후 `pieces` 기본 |
| | | `write_cutting_plan_dxf` 기존 CP 도면 형식 | ✅ | 라벨 `A516-70 t10 x 2438 x 9150 - 1 SH'T` |
| | | `build_por` POR PLATE 행 + por.csv | ✅ | 중량 = t×W×L×7.85e-6 (실제 POR 1,751kg 재현) |
| **L4 검증·HITL** | 저신뢰 항목 사람 확정 | `verify_part_spec` / `verify_weight_vs_bom` / `verify_nesting` | ✅ | reward 함수의 원형 |
| | | `compare_with_gt` 사람 커팅플랜(gt/sheets.csv) 대비 | ✅ | 개발·평가용 |
| | | `ask_human(H1~H4)` | ✅ | policy: ask / auto. eval 모드는 자동 응답 + 기록 |
| | | `confidence_report` | ✅ | HITL 위치 결정 근거 (RQ2) |
| 보조 | | `list_inputs`, `get_state_summary` | ✅ | |

✅ = API 없이 smoke test 통과, 🔑 = 코드는 있으나 `ANTHROPIC_API_KEY` 가 없어 미실행.

## 2. 구조

```
pyproject.toml, uv.lock  uv 의존성
.env.example           .env (API 키·머신별 값, git 제외) 템플릿
cutplan_agent/
  config.py            경로, 모델(claude-opus-5-5), 커팅여유 20(가스), 운반상한 12000x3050, 표준폭, 전개판정 키워드
  state.py             JobState(도면·BOM·PartSpec·조각·판·POR·HITL) + Trajectory(skill 호출 로그 = RL 데이터) + @logged
  unfold.py            절곡·평판 전개 엔진 (tools/dwg2png/vlm/unfold.py 에서 이전). --validate 로 원통 공식 재검증
  skills/l1_perception.py  l2_relation.py  l3_rules.py  l4_verify.py  knowledge.py
  knowledge/*.md       drawing_conventions_kr, unfold_rules, split_and_margin, material_mapping, nesting_rules, design_data_ga, por_format
  agent/orchestrator.py  Claude tool_runner. agent/system.md = 절차 ①~⑥ + 원칙
  eval/smoke_kd25038.py  API 없이 L2(B경로)→L3→L4 전체 경로 실행
  eval/run_eval.py       dataset 워크오더 평가 (API 필요)
  eval/run_experiments.py  E1·E2 는 API 없이 test_data 로 실행
cutplan_agent_v3/      v3 정투영 복원 파이프라인 (step1~6, OCR·추론 VLM). 자체 README.md, code_v3.md 참조
scripts/               Data/dataset · part_class_dataset · test_data 구축 스크립트 (아직 D:\노바투스2026 경로 하드코딩)
skills/                v3 와 cutplan_agent 가 읽는 도메인 문서·프롬프트 (04_reading_records 는 git 제외)

# 아래는 git 제외
Data/                  원본·정제 데이터 (dataset, _dataset, part_class_dataset, 연도별 cutting plan)
test_data/             scripts/build_test_data.py 가 Data/dataset 에서 만든 평가 세트
data_v3/synthetic/     v3 입력: 합성 DXF + label.json 30개
tools/dwg2png/         이전 세션 툴킷 (Windows 용 libredwg, cp_extract 등). 코드는 Windows 의 dwg2dxf.exe 만 쓴다
runs/<job>/            state.json, trajectory.json, <job>_CP.dxf, por.csv, final.md
```

## 3. 실행

필요한 도구는 [uv](https://docs.astral.sh/uv/) 하나다. Python 설치·가상환경·패키지 설치를 uv 가 모두 맡는다.

### 3.1 처음 한 번

1. uv 설치 (설치 후 터미널을 새로 연다)
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. 프로젝트 폴더에서 `uv sync` — `.venv` 를 만들고 의존성과 `cutplan_agent` 를 설치한다. 의존성이 바뀌어 `git pull` 한 뒤에도 다시 실행한다.
3. `.env.example` 을 `.env` 로 복사하고 값을 채운다 (Windows: `copy .env.example .env`, Linux: `cp .env.example .env`).
   - `ANTHROPIC_API_KEY`: VLM 단계(L1·L2, orchestrator)에 필요. smoke test 만 돌릴 땐 비워도 된다.
   - `CUTPLAN_ROOT`: 데이터가 project root 가 아닌 곳에 있을 때만.
   - `.env` 는 실행 시 자동으로 읽히고 git 에 올라가지 않는다.

### 3.2 실행

프로젝트 폴더에서 `uv run python -m ...` 로 실행한다.

```bash
uv run python -m cutplan_agent.eval.smoke_kd25038                       # API 불필요
uv run python -m cutplan_agent.agent.orchestrator --job KD23002 --eval  # dataset/KDM/2023/KD23002/input/drawings 사용
uv run python -m cutplan_agent.eval.run_eval --jobs KD23002,KD23015,KD23022
```

VSCode: `Ctrl+Shift+P` → `Python: Select Interpreter` → `.venv` 를 고르면 실행·디버그도 같은 환경을 쓴다.

### 3.3 데이터·외부 도구

- 데이터·결과는 기본으로 project root 의 `Data/`, `test_data/`, `data_v3/synthetic/`, `runs/` 를 쓴다 (git 제외). `Data/` 는 팀 공유 압축본(노바투스2026)의 `Data/` 를 그대로 둔다.
- `test_data/` 는 `scripts/build_test_data.py` 가 `Data/dataset` 에서 만든다. 스크립트가 아직 `D:\노바투스2026` 경로와 `manifest.csv` 의 역슬래시 경로를 가정하므로, Linux 에서는 두 가지를 고쳐서 실행한다.
- DWG 변환: Windows 는 `tools/dwg2png/libredwg/dwg2dxf.exe` 를, 그 밖에는 PATH 의 `dwg2dxf` 를 쓴다. Ubuntu 24.04 apt 에는 libredwg 패키지가 없으므로 GNU LibreDWG 를 소스에서 빌드해 설치한다.
- v3 테스트: `cd cutplan_agent_v3 && uv run --with requests --with opencv-python-headless --with pytesseract python -m unittest discover -s tests`. OCR 폴백 테스트는 tesseract 바이너리가 필요하다 (`sudo apt install tesseract-ocr`).

### 3.4 자주 나는 문제

| 증상 | 해결 |
|---|---|
| `uv: command not found` / `'uv' 은(는) ... 아닙니다` | uv 설치 후 터미널을 새로 연다 |
| `ModuleNotFoundError: No module named 'cutplan_agent'` (또는 `dotenv` 등) | `uv sync` 를 다시 실행하고, `python` 대신 `uv run python` 으로 실행했는지 확인 |
| `Could not resolve authentication method` / API 키 오류 | `.env` 의 `ANTHROPIC_API_KEY` 확인 (파일 이름이 `.env.txt` 가 아닌지도) |
| `This API key is not scoped to a workspace` | `.env` 에 `ANTHROPIC_WORKSPACE_ID` 추가 (`cutplan_agent/client.py` 참조) |
| `dwg2dxf 실패` | 3.3 의 dwg2dxf 설치 확인 |

## 4. Smoke test 결과 (KD25038, 발표자료 검증 사례, 2026-10-01)

| 항목 | 이 코드 | KDM 배치툴 / 실제 PO | 비고 |
|---|---|---|---|
| 쉘 전개 길이 | π(2600+10) = **8199.6** | 8168 (= π×2600) | KDM 툴은 ID 기준. 툴킷 44건 역산은 평균지름. **어느 쪽이 KDM 표준인지 확인 필요** |
| 헤드 블랭크 | 1.25×ID = **3250** | 3240 | 경험계수. part_tags HEAD 14건으로 보정 예정 |
| 헤드 분할 | 1970 + 1280 (오프셋 345) | 1970 + 1270 (오프셋 350) | 현 분할 규칙 일치 |
| 콘 분할 | 폭 2438 기준 4조각 (1447×1998) | 폭 3048 기준 2조각 (2604×2604) | **분할 수는 판폭 선택에 종속** → 분할·판폭 공동 탐색 필요 |
| t10 판 수 / gross | 4장 / 5,657 kg (활용률 75%) | 3장 / 5,486 kg (77%) | 중량 +3%. bbox 배치라 반원·부채꼴 맞물림 불가 → NFP 엔진 필요 |
| 검증 | 겹침 0, 여유 위반 0, 22/22 배치 | | |

목적함수 비교 (콘 폭 2438): pieces 4장 5,657 / util 4장 5,671 / net 3장 6,692 / net_util 4장 5,671 → `pieces` 채택.

## 5. 다음 단계
1. `ANTHROPIC_API_KEY` 를 넣고 KD23002 (도면 12장, 정답 완비) 로 L1·L2 실행 → `runs/KD23002/trajectory.json` 확보.
2. 분할·판폭 공동 최적화: `split_to_pieces(max_w)` 를 후보 폭마다 돌려 `nest_group` 결과가 최소인 조합 선택 (RQ1 과 직결).
3. 곡선 맞물림 네스팅 (NFP: SVGnest/Deepnest 포트 또는 shapely 기반).
4. 헤드 블랭크 계수·쉘 중립축 규약을 part_tags.csv 로 확정.
5. 평가: scorecard 성공 워크오더 30건에 run_eval → 판 수·중량 비율 분포 → verifier 를 reward 로 Phase 2.
