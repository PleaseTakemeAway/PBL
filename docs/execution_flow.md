# 실행 흐름: 워크오더 에이전트(v2) 와 도면 판독기(v3)

코드를 처음 읽는 사람을 위해 두 에이전트의 진입점과 함수 호출 순서를 정리했다. 2026-10-22 기준이다.

폴더는 하는 일로 나누고 버전은 git 으로 관리한다. 동료가 `cutplan_agent_v3/` 로 만든 v3 는 268b42e 에서 `cutplan_agent/reader/` 와 `cutplan_agent/reconstruct/` 로 옮겼다. 옛 상태는 git 에서 꺼낸다 (v3 원본 253020c, 옮기기 직전 ca142a8). 모든 명령은 레포 루트에서 실행한다.

## 1. 한눈에

| | v2 워크오더 에이전트 | v3 도면 판독기 |
|---|---|---|
| 폴더 | `cutplan_agent/` 의 `agent/`, `skills/`, `eval/`, `config.py`, `state.py`, `unfold.py` | `cutplan_agent/reader/` (판독·전개도·CLI), `cutplan_agent/reconstruct/` (3D 복원), `tests/`, `experiments/` |
| 하는 일 | 워크오더 하나의 도면 세트 → 판재 구매의뢰(POR) | 도면 1장(부품 1개) → 형상 분류와 전개도 (+3D 복원) |
| 처리 단위 | 워크오더 (도면 여러 장, 부품 여러 개) | 도면 1장 |
| 먼저 볼 진입점 | [`eval/smoke_kd25038.py`](../cutplan_agent/eval/smoke_kd25038.py) | [`reader/main.py`](../cutplan_agent/reader/main.py), 실험은 [`experiments/experiments.sh`](../experiments/experiments.sh) |
| 모델 | Claude (Anthropic SDK) | OCR 모델 + 추론 모델 두 역할. 로컬 vLLM(OpenAI 호환) 또는 Anthropic |
| 실행 | `PYTHONPATH=. uv run python <파일>` | `PYTHONPATH=. python cutplan_agent/reader/main.py ...` |
| 검증 상태 | API 없는 smoke test 통과 (22/22 배치, 6125.0 kg). VLM 경로는 README 기준 미실행 | 단위 테스트 83개 중 13개 실패 (알려진 상태). 합성 도면 30장 형상 분류 27/30 |

두 코드는 한 제품의 앞단과 뒷단에 가깝다. v3 는 v2 를 대체한 버전이 아니라, 앞단(도면 판독)을 새로 만든 것이다.

```
           앞단: 도면 판독                              뒷단: 계획 수립
v2   L1·L2: Claude 가 BOM·치수를 읽는다       →   L3·L4: 전개 → 분할 → 네스팅 → POR → 검증
v3   reader: DXF·이미지 판독 → 형상 분류 → 전개도     (없음)
```

## 2. v2 워크오더 에이전트

### 2.1 계층

skill 함수를 KDM 발표자료의 4계층으로 나눴다. 모든 skill 은 JSON 직렬화 가능한 인자를 받아 dict 를 돌려주고, 전역 `JobState` 하나를 읽고 쓴다. 호출은 `@logged` 가 trajectory 로 기록한다.

| 계층 | 파일 | 주요 함수 |
|---|---|---|
| L1 인식 | [`skills/l1_perception.py`](../cutplan_agent/skills/l1_perception.py) | `ingest_drawing` (DWG→DXF→PNG, PDF→PNG), `dxf_read_text`, `vlm_read_page`, `normalize_bom` |
| L2 관계·의미 | [`skills/l2_relation.py`](../cutplan_agent/skills/l2_relation.py) | `classify_drawing`, `extract_design_data`, `extract_part_model`, `set_part_spec`, `detect_split_lines`, `resolve_missing_spec` |
| L3 계산 | [`skills/l3_rules.py`](../cutplan_agent/skills/l3_rules.py) | `unfold_part`, `split_to_pieces`, `nest_group`, `nest_all`, `build_por`, `write_cutting_plan_dxf` |
| L4 검증·사람 확인 | [`skills/l4_verify.py`](../cutplan_agent/skills/l4_verify.py) | `verify_part_spec`, `verify_weight_vs_bom`, `verify_nesting`, `compare_with_gt`, `ask_human`, `confidence_report` |
| 공통 | [`state.py`](../cutplan_agent/state.py), [`config.py`](../cutplan_agent/config.py), [`client.py`](../cutplan_agent/client.py), [`unfold.py`](../cutplan_agent/unfold.py), [`skills/knowledge.py`](../cutplan_agent/skills/knowledge.py) | 상태와 trajectory / 경로·모델·현장 상수 / Anthropic 클라이언트 / 절곡판·평판 전개 엔진 / 도메인 지식 로더 |

API 가 필요한 skill 은 `vlm_read_page`, `classify_drawing`, `extract_design_data`, `extract_part_model`, `detect_split_lines` 다. L3·L4 는 결정적 계산이라 API 없이 돈다.

### 2.2 진입점

| 파일 | 하는 일 | API |
|---|---|---|
| [`eval/smoke_kd25038.py`](../cutplan_agent/eval/smoke_kd25038.py) | KD25038 부품을 손으로 넣고 L3·L4 를 고정 순서로 한 번 돈다. **처음 읽을 파일** | 불필요 |
| [`agent/orchestrator.py`](../cutplan_agent/agent/orchestrator.py) | 실제 에이전트. Claude 가 skill 25개를 tool 로 불러 절차 ①~⑥ 을 수행한다 | 필요 |
| [`eval/run_eval.py`](../cutplan_agent/eval/run_eval.py) | 여러 워크오더에 orchestrator 를 평가 모드로 돌리고 사람 커팅플랜(`gt/sheets.csv`)과 비교 | 필요 |
| [`eval/run_experiments.py`](../cutplan_agent/eval/run_experiments.py) | `test_data` 전체 실험. E1·E2 는 API 없이 돈다 | E3·E4 만 |
| [`eval/manual_vlm_run.py`](../cutplan_agent/eval/manual_vlm_run.py) | VLM 자리를 사람이 대신한다. `ingest` 로 도면을 PNG 로 만들고, 사람이 쓴 `spec.json` 으로 `run` 이 전개~POR~정답 비교 | 불필요 |
| [`eval/status.py`](../cutplan_agent/eval/status.py) | 실행 중인 job 의 진행 상황 (다른 터미널에서) | 불필요 |
| `eval/compare_outputs.py`, `reading_sheet.py`, `tiles.py`, `aggregate_manual.py` | 결과 비교와 수동 판독 보조 | 불필요 |
| [`unfold.py`](../cutplan_agent/unfold.py) `--validate` | 원통 전개 공식을 `Data/_dataset/part_tags.csv` 로 재검증 | 불필요 |

### 2.3 smoke test 실행 순서 — `smoke_kd25038.py` 의 `main()`

```bash
PYTHONPATH=. uv run python cutplan_agent/eval/smoke_kd25038.py
```

1. `JobState`, `Trajectory` 를 만들고 `set_context` 로 등록한다. 이후 모든 skill 이 이 상태를 읽고 쓴다.
2. `K.list_topics()` — 지식 문서 목록을 출력한다.
3. `L2.set_part_spec` × 8 — 부품 8개(쉘, 상부 헤드, 콘 2개, 노즐 패드, 레그·러그 패드, 베이스 플레이트)를 직접 넣는다. orchestrator 에서는 이 자리를 L1 판독과 `extract_part_model` 이 채운다.
4. 부품마다:
   1. `L4.verify_part_spec(i)` — 스펙 검사
   2. `L3.unfold_part(i)` — 전개. 원통·원추·경판·패드링은 `l3_rules.py` 안의 공식(`_cyl`, `_cone`, `_head_blank`, `_pad`)을, 절곡판·평판은 `cutplan_agent/unfold.py` 엔진을 쓴다
   3. `L3.split_to_pieces(i, max_w=...)` — 판 폭(2438, 헤드는 2000)에 맞춰 조각으로 나눈다
5. `L3.nest_all(cut="gas", allow_custom=True)` — (재질, 두께) 그룹마다 조각을 판에 배치한다
6. `L4.verify_nesting()` — 겹침·간격·판 초과·미배치 검사. 기대값 `placed 22/22`
7. `L3.build_por()` — 구매의뢰 행과 중량. 기대값 `total 6125.0 kg`
8. `L3.write_cutting_plan_dxf()` — 커팅플랜 DXF
9. `L4.confidence_report()`, `L4.ask_human("H4", ...)` — 저신뢰 항목 보고와 최종 확인 (평가 모드라 자동 응답)
10. `runs/KD25038_smoke/` 에 `state.json`, `trajectory.json` 저장

### 2.4 orchestrator 실행 순서 — `orchestrator.py` 의 `run()`

```bash
PYTHONPATH=. uv run python cutplan_agent/agent/orchestrator.py --job KD23002 [--eval] [--max-steps 80]
```

1. 입력 도면을 모은다. `--inputs` 가 없으면 `job_inputs` 가 `Data/dataset/KDM/20<yy>/<job>/input/drawings/` 아래의 `.dwg`·`.pdf` 를 찾는다. 이름에 `CUTTING`·`_CP` 가 들어간 파일(정답 커팅플랜)은 빼고, 같은 이름이면 DWG 를 고른다.
2. `JobState`, `Trajectory` 를 만들고 `set_context` 로 등록한다.
3. `client.make_client()` 로 Anthropic 클라이언트를 만든다. API 키는 `config.py` 가 import 될 때 `.env` 에서 읽힌다.
4. [`agent/system.md`](../cutplan_agent/agent/system.md) 를 system prompt 로, "절차 ①~⑥ 을 수행하라" 를 첫 메시지로 `client.beta.messages.tool_runner(...)` 를 시작한다. tool 은 `SKILLS` 목록의 함수 25개다 (`build_tools` 가 `beta_tool` 로 감싼다).
5. 턴마다 Claude 가 tool 을 고르고 SDK 가 그 함수를 실행한다. 턴마다 호출 내용을 출력하고 state·trajectory 를 저장하므로 `status.py` 로 진행을 볼 수 있다. `--max-steps` 에서 멈춘다.
6. 마지막 텍스트 답을 `final.md` 로 저장한다.

Claude 가 따르는 절차 (`agent/system.md`):

| 단계 | 부르는 skill |
|---|---|
| ① 도면 읽기 | `ingest_drawing` → `classify_drawing`. GA 도면은 `extract_design_data` |
| ② 자재목록 | `vlm_read_page(what="bom")` → `normalize_bom`. 빠진 값은 `resolve_missing_spec` 또는 `ask_human(H2)` |
| ③ 전개·분할 | `extract_part_model` (`dxf_read_text`, `detect_split_lines` 로 확인) → `verify_part_spec` → `unfold_part` → `split_to_pieces`. 저신뢰 항목은 `ask_human(H1)` |
| ④ 네스팅 | `nest_all` → `verify_nesting`. 활용률이 낮으면 `nest_group` 재시도 |
| ⑤ 구매의뢰 | `build_por` → `write_cutting_plan_dxf` |
| ⑥ 검증 | `confidence_report` → `ask_human(H4)`. 평가 모드면 `compare_with_gt` |

smoke test 는 ③ 의 `verify_part_spec` 부터 ⑥ 까지를 정해진 순서로 돈 것이다.

### 2.5 결과물

`runs/<job>/` 아래에 `state.json` (전체 상태), `trajectory.json` (skill 호출 기록), `final.md`, `por.csv`, `<job>_CP.dxf` (커팅플랜).

## 3. v3 도면 판독기 — `cutplan_agent/reader/`, `cutplan_agent/reconstruct/`

### 3.1 흐름

```
DXF/이미지 ─▶ reader: 표제란 · 뷰 분할 · 도면 종류 ─▶ 추론 모델이 뷰와 형상(part_class)을 정함
          ─▶ reader: 전개 파라미터 → 전개도 (flat_pattern)
          └▶ reconstruct: (복원 가능할 때) 3D 복원 step1~5 → 후보 확인 → STEP 내보내기 (step6)
```

모델은 두 역할로 나뉜다. OCR 모델은 글자를 읽고, 추론 모델은 그 글자와 도면으로 JSON 판단을 낸다. 모든 모델 단계에는 결정적 fallback 이 있어서 `--no-vlm` 으로 모델 없이도 끝까지 돈다 (형상은 맞히지 못한다). `reconstruct` 는 `reader` 의 모듈을 쓰지 않고, `reader` 만 `reconstruct` 를 쓴다.

### 3.2 진입점

| 파일 | 하는 일 |
|---|---|
| [`experiments/experiments.sh`](../experiments/experiments.sh) | 동료가 27/30 을 낸 실험. vLLM 서버 두 개를 띄우고 (OCR DeepSeek-OCR-2: GPU 4, 포트 8000 / 추론 Qwen3.6-27B: GPU 5, 포트 8001) `reader/main.py --batch --input-mode dxf` 로 `data_v3/synthetic` 30장을 돈 뒤 서버를 끈다. 변형: `experiments_local.sh` (GPU 0/1), `experiments_claude.sh` (Anthropic) |
| [`cutplan_agent/reader/main.py`](../cutplan_agent/reader/main.py) | CLI. 아래 세 모드 |
| `tests/` | 단위 테스트. `PYTHONPATH=. python -m unittest discover -s tests` |

`experiments.sh` 의 기본 출력 폴더는 동료의 기준 결과 폴더(`runs/reader/deepseek_ocr_qwen_reasoning_skills`)다. `--overwrite` 없이는 덮어쓰지 않고 멈추지만, 새 실험에는 `--output-dir` 로 다른 폴더를 주는 게 안전하다. `--dry-run` 은 서버를 띄우지 않고 설정만 출력한다.

`main.py` 의 모드:

| 모드 | 조건 | 흐름 |
|---|---|---|
| 배치 | `--batch`, 입력이 여러 개, 또는 폴더 | `batch.run_batch` (3.3) |
| 판독만 | `--analyze-only` | `analyze_dxf` 또는 `analyze_image` → `run_unfold` |
| 단일 (기본) | 입력 1개 | `load_drawing` → `run_unfold` → `ReconstructionPipeline.run` → `confirm_candidates` → `ReconstructionExporter` |

### 3.3 배치 실행 순서 — `experiments.sh` → `batch.run_batch`

```bash
./experiments/experiments.sh --python <vllm 이 있는 python> --output-dir runs/reader/<새 폴더>
# 모델 없이 (GPU 불필요):
PYTHONPATH=. python cutplan_agent/reader/main.py --batch --input-mode dxf --no-vlm --output-dir <폴더> data_v3/synthetic
```

1. `main.py` — 인자를 해석하고 `vlm.make_clients` 로 OCR·추론 클라이언트를 만든다 (`--no-vlm` 이면 꺼진 클라이언트).
2. [`reader/batch.py`](../cutplan_agent/reader/batch.py) 의 `run_batch` — `discover_dxf` 로 DXF 를 찾고, 도면마다:
   1. `drawing_io.load_drawing` → `dxf_adapter.load_dxf_document` → **`analyze_dxf`** ([`reader/dxf_adapter.py`](../cutplan_agent/reader/dxf_adapter.py)):
      - `read_dxf` — DXF 엔티티를 읽는다 (ezdxf, 없으면 순수 파이썬 리더)
      - `detect_frames`, `find_title_region`, `parse_title_block` — 도면 틀과 표제란 (OCR → 추론 모델)
      - `segment_views` — 뷰를 나눈다
      - `classify_sheet` — 정투상 / 네스팅(커팅플랜) / 기타. 네스팅 도면이면 판 정보만 뽑고 복원은 하지 않는다
      - `label_with_vlm` — 추론 모델이 뷰 종류, 투상법, 형상(`part_class`), 복원 가능 여부를 정한다
   2. `dxf_adapter.build_document` — 판독 결과를 `reconstruct/models.py` 의 `DrawingDocument` 로 만든다
   3. **`unfold.run_unfold`** ([`reader/unfold.py`](../cutplan_agent/reader/unfold.py)) — `extract_params` (추론 모델 `ask_unfold_params`, 실패하면 기하 기반 `fallback_params`) → `develop` (전개 계산) → `export_flat_pattern`
   4. 복원 가능하면 [`reconstruct/pipeline.py`](../cutplan_agent/reconstruct/pipeline.py) 의 `ReconstructionPipeline.run` — step1 도면 해석 → step2 뷰 매칭 → step3 후보 생성 → step4 후보 평가 → step5 모호성 정리
   5. `vision_adapter.confirm_candidates` — 추론 모델이 복원 후보를 확인한다
   6. `step6.ReconstructionExporter` — `provenance.json`, `report.md`, `reconstruction.step`, `parameters.json`
   7. 추론이 모두 끝난 뒤(`finally`)에야 정답 `label.json` 을 읽어 비교한다. 정답이 추론에 섞이지 않게 하려는 순서다
3. 전체 집계: `predictions.json`, `reconstruction.json`, `accuracy.md`, `flat_patterns.json`, `flat_patterns.md`

이미지·PDF 입력은 `vision_adapter.analyze_image` 가 `analyze_dxf` 자리를 맡는다. 기하는 OpenCV 로, 글자는 OCR 모델이나 tesseract 로 읽는다.

### 3.4 모듈 지도

| 파일 | 역할 |
|---|---|
| `reader/main.py`, `reader/batch.py` | CLI, 배치 실행과 집계 |
| `reader/drawing_io.py`, `reader/drawing_io_legacy_layers.py` | 입력 종류(JSON / 이미지·PDF / DXF)별 분기 |
| `reader/dxf_reader.py` | DXF 파싱 |
| `reader/dxf_adapter.py` | DXF 도면 판독. 가장 큰 파일 |
| `reader/vision_reader.py`, `reader/vision_adapter.py` | 이미지·PDF 판독, 복원 후보 확인 |
| `reader/vlm.py`, `reader/vlm_output.py` | VLM 클라이언트, 응답 스키마와 검증 |
| `reader/knowledge.py` | 레포 루트 `skills/` 의 문서를 프롬프트로 붙인다. 쓴 문서의 sha256 을 기록한다 |
| `reader/unfold.py` | 전개 파라미터와 전개도 |
| `reconstruct/models.py`, `geometry.py`, `pipeline.py`, `step1.py`~`step6.py` | 3D 복원 |
| `experiments/verify_ocr_output.py` | OCR 서버 출력 확인 도구 |

### 3.5 결과물

도면마다 `<출력 폴더>/<도면 이름>/` 아래에 `analysis/` (`sheet.png`, `sheet_analysis.json` 등), `prediction.json`, 전개에 성공하면 `flat_pattern.json`·`.dxf`·`.png`, 복원 결과 `provenance.json`, `report.md`, `reconstruction.step`, `parameters.json`.

## 4. 같은 일을 하는 곳

두 쪽은 서로 import 하지 않는다. 아래는 같은 일을 각자 구현한 곳이라 나란히 읽으면 차이가 보인다.

| 일 | v2 | v3 | 차이 |
|---|---|---|---|
| 전개 계산 | `skills/l3_rules.unfold_part` (+ `cutplan_agent/unfold.py` 엔진) | `reader/unfold.develop` | 경판 블랭크 (ID 2600, SF 50): v2 3250, v3 3415, KDM 실제 3240. 소경 0 인 원추는 v3 에서 에러 |
| 지식 문서 로더 | `skills/knowledge.py` → `cutplan_agent/knowledge/*.md` | `reader/knowledge.py` → `skills/**/*.md` | 두 문서 묶음은 바이트 단위로 같다 |
| VLM 호출 | `skills/l1_perception.vlm_parse` (Anthropic SDK) | `reader/vlm.VLMClient` (requests, 여러 provider) | |
| DXF 읽기 | `skills/l1_perception.dxf_read_text` (글자·치수만) | `reader/dxf_reader.read_dxf` (기하 전체) | |
| 형상 이름 | cylinder, cone_frustum, head, pad_ring, bent_sheet, flat | cylinder, cone, press_formed, bent_sheet, flat, other | v3 에는 pad_ring 이 없고, 경판을 press_formed 라고 부른다 |

## 5. 명령 모음 (레포 루트에서)

```bash
# v2
PYTHONPATH=. uv run python cutplan_agent/eval/smoke_kd25038.py                       # API 불필요
PYTHONPATH=. uv run python cutplan_agent/agent/orchestrator.py --job KD23002 --eval  # API 필요
PYTHONPATH=. uv run python cutplan_agent/eval/status.py --job KD23002 --watch       # 다른 터미널에서 진행 확인

# v3. uv 환경에는 아직 v3 의존성이 없어 --with 로 붙인다
PYTHONPATH=. uv run --with requests --with opencv-python-headless --with pytesseract \
  python -m unittest discover -s tests
PYTHONPATH=. uv run --with requests --with opencv-python-headless --with pytesseract \
  python cutplan_agent/reader/main.py --batch --input-mode dxf --no-vlm --output-dir /tmp/reader_novlm data_v3/synthetic
./experiments/experiments.sh --dry-run                                               # 설정만 출력
```
