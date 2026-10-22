# cutplan_agent_v3 코드 구조 — `experiments.sh` 실행 흐름

> **위치가 바뀌었다 (2026-10-22, 268b42e).** 이 문서는 동료가 `cutplan_agent_v3/` 시절에 쓴 그대로다. 지금 코드는 `cutplan_agent/reader/` (판독) 와 `cutplan_agent/reconstruct/` (3D 복원) 에, 실험 스크립트는 `experiments/`, 테스트는 `tests/`, 예제 입력은 `tests/fixtures/` 에 있다. 아래의 `python main.py ...` 는 레포 루트에서 `PYTHONPATH=. python cutplan_agent/reader/main.py ...` 로, `bash experiments.sh` 는 `bash experiments/experiments.sh` 로 읽는다. 실행 순서는 [docs/execution_flow.md](../execution_flow.md) 에 정리했다.

`experiments.sh`를 실행했을 때 호출되는 하위 파일들의 구조와 각 파일의 동작을 정리한 문서입니다.

## 1. 전체 호출 흐름

```
experiments.sh                     (bash: 설정 → vLLM 서버 2개 기동 → 파이썬 실행)
 └─ main.py --batch --input-mode dxf --output-dir ...
     ├─ vlm.make_clients()         → (ocr, reason) VLMClient 2개
     └─ batch.run_batch()
         ├─ discover_dxf()         ../data_v3/synthetic/**/*.dxf 수집
         └─ DXF 1개마다:
             ├─ drawing_io.load_drawing()
             │    └─ dxf_adapter.load_dxf_document()
             │         ├─ dxf_reader.read_dxf()          엔티티 파싱
             │         ├─ parse_title_block()            regex → (없는 필드만) OCR+reason
             │         ├─ segment_views()                뷰 영역 클러스터링
             │         ├─ classify_sheet()               orthographic / nesting
             │         ├─ label_with_vlm()               reason VLM + skills → 뷰 라벨, 투상법, part_class
             │         └─ build_document()               → DrawingDocument (models.py)
             ├─ unfold.run_unfold()                      part_class → 치수 → 전개도
             ├─ pipeline.ReconstructionPipeline.run()    step1~5 (3D 와이어프레임)
             ├─ vision_adapter.confirm_candidates()      reason VLM이 상위 후보를 다시 확인
             ├─ step6.ReconstructionExporter             STEP/JSON/MD 저장
             └─ label.json과 비교해 정확도 기록 (finally 블록)
         └─ 집계: predictions.json, reconstruction.json, accuracy.md, flat_patterns.*
```

## 2. 파일별 역할

### 2.1 진입점과 오케스트레이션

| 파일 | 역할 |
|---|---|
| `experiments.sh` | `ocr`과 `reason` 두 역할을 설정합니다. 우선순위는 CLI > `CUTPLAN_*` 환경변수 > 기본값입니다. 기본값은 OCR=`deepseek-ai/DeepSeek-OCR-2`(GPU 0, :8000), reason=`Qwen/Qwen3.6-27B`(GPU 1,2,3 pipeline parallel, :8001, `json_schema`/xgrammar)입니다. GPU 목록의 개수가 병렬 크기가 되고, 나누는 방식은 `--ocr-parallel`·`--reason-parallel`(`tensor`|`pipeline`)로 고릅니다. 역할이 `local`이면 `vllm serve`를 백그라운드로 띄우고 `/health`가 응답할 때까지 기다립니다. 로그는 `server_logs/{ocr,reason}_vllm.log`에 쌓입니다. 설정은 `CUTPLAN_{OCR,REASON}_{PROVIDER,MODEL,BASE_URL,OUTPUT_FORMAT,API_KEY}`로 export되어 파이썬에 전달됩니다. 스크립트가 끝나면 trap이 서버를 종료합니다. |
| `main.py` | argparse 진입점입니다. 이 스크립트에서는 항상 `--batch`로 호출되므로 `run_batch`로 넘어갑니다. 끝나면 요약, 정확도 표, 전개도 통계를 출력합니다. |
| `batch.py` | 샘플마다 `output/<id>/` 폴더를 만들고 분석, 전개, 복원, 내보내기를 수행합니다. 상태는 `reconstructed` / `prediction_only` / `no_valid_candidate` / `failed` 중 하나로 기록됩니다. 정답 `label.json`은 추론이 모두 끝난 뒤(`finally`)에만 읽으므로 추론 과정에 새어 들어가지 않습니다. |
| `drawing_io.py` | 입력 종류에 따라 처리 경로를 나눕니다. 이 스크립트에서는 `.dxf` + `input_mode=dxf` + `dxf_mode=auto`이므로 `dxf_adapter`로 갑니다. |

### 2.2 DXF 해석 (도면 → 구조화 데이터)

| 파일 | 역할 |
|---|---|
| `dxf_reader.py` | 레이어와 무관하게 모든 엔티티를 `RawEntity`로 읽습니다. ezdxf를 우선 쓰고, 실패하면 자체 파서(`PureDxfReader`)로 대체합니다. bulge→arc 변환과 MTEXT 정리도 여기서 합니다. |
| `dxf_adapter.py` | 핵심 어댑터이고 `analyze_dxf()`가 중심입니다. ① 프레임과 표제란 위치를 찾습니다. ② 표제란은 먼저 regex로 읽고, 비어 있는 필드만 OCR→reason으로 채웁니다(`read_ocr_task`). ③ 형상 엔티티를 공간 클러스터링해서 뷰 후보를 만듭니다. ④ 위치 기반으로 라벨을 먼저 붙인 뒤(`label_by_position`), reason VLM이 라벨, 투상법, `part_class` 점수, 복원 가능 여부를 판단합니다(`label_with_vlm`). 두 결과가 다르면 review 항목으로 남깁니다. ⑤ `build_document()`가 front/top/right 계약에 맞게 변환합니다(arc 분할, left/bottom/back 뷰는 미러링). nesting 도면이면 `NotOrthographicSheet`를 던지고 `prediction_only`로 처리됩니다. |
| `models.py` | 공용 데이터클래스입니다(`DrawingDocument`, `DrawingView`, `ReconstructionCandidate`, `ReconstructionResult` 등). |

### 2.3 모델 호출

| 파일 | 역할 |
|---|---|
| `vlm.py` | `VLMClient`는 OpenAI 호환 API(vLLM)와 Anthropic API 호출을 담당하고, 모든 호출을 `trace`에 기록합니다. OCR 역할은 항상 스키마 없이 원문 텍스트만 받습니다("Free OCR."). JSON은 reason 역할만 만듭니다. `softmax_class_scores`와 `final_part_class`는 모델이 낸 logit을 확률로 바꾸고 최종 클래스를 정합니다. |
| `vlm_output.py` | task별 JSON 스키마(title_block, view_labels, unfold, candidate_confirmation 등)와 응답 검증/정규화를 담당합니다. vLLM의 `response_format: json_schema`로 전달됩니다. |
| `knowledge.py` | `../skills/*.md`를 읽어 system prompt에 `<skill>` 블록으로 넣습니다. 단계별 문서는 `STAGE_TOPICS`가 정합니다(part_class 단계는 `unfold_rules`, `unfold_extract`). 문서마다 sha256을 trace에 남깁니다. |

### 2.4 전개도

| 파일 | 역할 |
|---|---|
| `unfold.py` | part_class를 part_type으로 매핑합니다(cone→cone_frustum, press_formed→head 등). reason VLM이 skills를 참고해 전개 파라미터만 읽고, 비어 있는 값은 뷰 외곽 치수로 채웁니다(fallback). 길이 계산은 모델에 맡기지 않고 `develop()`의 공식(K-factor 등)으로 코드에서 합니다. 결과는 `flat_pattern.{json,dxf,png}`로 저장하고, label과 비교해 1% 이내인지 평가합니다. |

### 2.5 3D 복원 (`pipeline.py`가 step1~5를 순서대로 호출)

| 파일 | 역할 |
|---|---|
| `pipeline.py` | `ReconstructionPipeline.run()`이 step1~5를 순서대로 연결하고 `ReconstructionResult`를 반환합니다. |
| `step1.py` | `DrawingInterpreter`: 단위를 mm로 통일하고 scale을 반영합니다. 뷰 식별과 정렬, 선 종류 분류(실선/숨은선), primitive 추출, 치수와 형상 연결을 합니다. |
| `step2.py` | `ViewMatcher`: 공유 축을 기준으로 뷰 간 꼭짓점과 모서리의 대응을 찾습니다. |
| `step3.py` | `CandidateGenerator`: 와이어프레임 후보와 feature 가설을 만들고 판금 제약을 적용합니다. |
| `step4.py` | `CandidateEvaluator`: 형상 유효성, 재투영, 치수, 물리 제약, 제조성을 검사해서 순위를 매깁니다. |
| `step5.py` | `AmbiguityResolver`: 남은 모호성을 사람이 검토할 요청(`review_request`)으로 정리합니다. |
| `geometry.py` | 투영 같은 공용 기하 함수입니다. |
| `vision_adapter.confirm_candidates` | 원본 뷰와 상위 3개 후보의 재투영을 나란히 그린 이미지(`candidates.png`)를 reason VLM에 보여주고 하나를 고르게 합니다. 최종 순위는 검증기 결과가 우선이고, VLM 선택이 다르면 review 항목으로 남깁니다. |
| `step6.py` | `ReconstructionExporter`: `reconstruction.step`, `parameters.json`, `provenance.json`, `report.md`를 씁니다. |

### 2.6 이 스크립트에서는 쓰이지 않는 파일

- `vision_reader.py`와 vision 경로의 나머지 코드: `--input-mode vision`일 때만 씁니다. 이 스크립트는 `dxf`로 고정되어 있습니다.
- `drawing_io_legacy_layers.py`: `--dxf-mode layers`일 때만 씁니다.
- `experiments_local.sh`, `experiments_claude.sh`: 같은 흐름을 다른 설정으로 돌리는 변형 스크립트입니다.

## 3. 출력 구조

기본 출력 경로는 `output/deepseek_ocr_qwen_reasoning_skills/`입니다.

```
server_logs/ocr_vllm.log, reason_vllm.log
predictions.json  reconstruction.json  accuracy.md  flat_patterns.json/.md   ← 배치 집계
<sample_id>/                       e.g. bent_sheet_0007/
  prediction.json                  샘플별 레코드 (예측, 정답, 전개도 평가)
  flat_pattern.{json,dxf,png}      전개도
  reconstruction.step, parameters.json   유효한 후보가 있을 때만 생성
  provenance.json, report.md
  analysis/ sheet.png, sheet_labeled.png, title_block.png, candidates.png, sheet_analysis.json
```

## 4. 확인해 볼 점

- 출력 폴더에 이전 결과가 있으면 `--overwrite`를 주지 않는 한 배치가 바로 실패합니다.
