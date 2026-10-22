# cutplan_agent_v2

> **위치가 바뀌었다 (2026-10-22, 268b42e).** 이 문서는 동료가 `cutplan_agent_v3/` 시절에 쓴 그대로다. 지금 코드는 `cutplan_agent/reader/` (판독) 와 `cutplan_agent/reconstruct/` (3D 복원) 에, 실험 스크립트는 `experiments/`, 테스트는 `tests/`, 예제 입력은 `tests/fixtures/` 에 있다. 아래의 `python main.py ...` 는 레포 루트에서 `PYTHONPATH=. python cutplan_agent/reader/main.py ...` 로, `bash experiments.sh` 는 `bash experiments/experiments.sh` 로 읽는다. 실행 순서는 [docs/execution_flow.md](../execution_flow.md) 에 정리했다.

정투영 도면의 뷰를 대응시켜 3D 와이어프레임 후보를 만들고, 검증 결과와
미해결 모호성을 함께 내보내는 Python 파이프라인입니다. Python 3.10 이상을 사용합니다.

| 단계 | 파일 / 클래스 | 주요 메서드 |
|---|---|---|
| 1. 도면 해석·뷰 구조화 | `step1.py` / `DrawingInterpreter` | `extract_metadata`, `segment_views`, `identify_views`, `align_views`, `classify_lines`, `extract_primitives`, `associate_annotations` |
| 2. 뷰 간 대응 | `step2.py` / `ViewMatcher` | `match_vertices`, `match_edges`, `match_features`, `check_projection_consistency` |
| 3. 3D 후보 생성 | `step3.py` / `CandidateGenerator` | `generate_wireframe_candidates`, `generate_feature_candidates`, `apply_sheet_metal_constraints` |
| 4. 검증·점수화 | `step4.py` / `CandidateEvaluator` | `validate_geometry`, `check_reprojection`, `check_dimensions`, `check_physical_constraints`, `check_manufacturability`, `rank_candidates` |
| 5. 모호성 해소 | `step5.py` / `AmbiguityResolver` | `detect_ambiguities`, `find_additional_evidence`, `build_resolution_options`, `create_review_request` |
| 6. 출력 | `step6.py` / `ReconstructionExporter` | `export_step`, `export_parameters`, `export_provenance`, `export_report` |

`models.py`는 데이터 계약, `geometry.py`는 투영·선분 검사, `drawing_io.py`는
파일 입력 라우팅, `dxf_reader.py`/`dxf_adapter.py`/`vlm.py`는 실제 DXF 시트 해석,
`vision_reader.py`/`vision_adapter.py`는 이미지(및 래스터화한 DXF) 해석, `pipeline.py`는 1~5단계 연결, `main.py`는 실행과 6단계 출력을 담당합니다.

## 실행

```powershell
python main.py examples/box.json --output-dir output
python -m unittest discover -s tests -v
```

예제는 100 × 60 × 2 mm 형상의 세 정투영 뷰입니다. 예상 결과는 정점 8개와
모서리 12개이며, `output`에 다음 파일이 생성됩니다.

- `reconstruction.step`: AP214 형식의 와이어프레임 STEP
- `parameters.json`: 크기, 판 두께, 특징 후보와 점수
- `provenance.json`: 입력 체크섬, 뷰 정규화, 대응 근거, 후보·검증·검토 요청
- `report.md`: 단계별 검사 상태와 추가 검토 항목

JSON 실행에는 외부 패키지가 필요하지 않습니다. DXF는 `ezdxf`가 있으면 그것을, 없으면 내장
순수 파이썬 리더(`dxf_reader.py`)를 사용합니다. VLM 호출에는 `requests`, 시트 렌더에는 `matplotlib`이 필요합니다.

```powershell
python -m pip install -r requirements.txt
python main.py scan.png --output-dir output                    # 스캔 이미지: OCR → 뷰 후보 → 추론 VLM → 3D 후보 → 후보 확인
python main.py drawing.pdf --dpi 250 --analyze-only            # PDF 1페이지, 표제란·뷰 라벨·보정만 확인
python main.py drawing.dxf --output-dir output                 # DXF도 기본은 래스터화 후 같은 비전 경로
python main.py drawing.dxf --input-mode dxf --output-dir out   # 엔티티 직접 파싱 경로
python main.py scan.png --no-vlm --no-confirm                  # 모델 없이 tesseract·위치 규칙만
```

## 입력 경로 (기본: 비전 경로)

```
PNG/JPG/PDF ─┐
DXF(래스터화)─┴▶ vision_reader ──▶ TextItem[] + PxPrimitive[] ──▶ vision_adapter ──▶ DrawingDocument ──▶ pipeline ──▶ confirm_candidates
               (OCR VLM / tesseract, OpenCV)                   (뷰 후보·추론 VLM·보정)                  (3D 후보)     (추론 VLM이 후보 비교)
```

`main.py`의 기본 `--input-mode vision`은 모든 입력을 **픽셀**로 다룹니다. DXF도 한 번 래스터화한 뒤 같은 길을
가므로 스캔본과 벡터 도면이 같은 코드로 처리됩니다. 엔티티를 직접 읽는 이전 경로는 `--input-mode dxf`로 남아 있습니다
(`drawing_io.load_drawing`의 API 기본값은 `auto`: 이미지는 비전, DXF는 엔티티).

| 단계 | 담당 | 방법 | 폴백 |
|---|---|---|---|
| 글자·치수·표제란 읽기 | **소형 OCR VLM** | 시트를 1400px 타일로 잘라 `{text, bbox, kind}` JSON을 받음. 표제란 크롭에서 축척·재질·두께·투상법 기호를 읽음 | `tesseract`(0°·90° 두 번) |
| 기하(선·원) 추출 | OpenCV | 잉크 런 스캔으로 축 정렬 선, Hough로 사선·원. 잉크 비율로 은선 판별, 스트로크 폭 기준 스냅 | - |
| 뷰 후보 | OpenCV | 프레임·표제란·BOM·치수 텍스트 제거 → 작은 간격의 연결 성분 → **폐곡선(구멍)을 가진 성분만 뷰**, 치수선·지시선 묶음은 가장 가까운 뷰 하나에 귀속 | - |
| 뷰 라벨·투상법·부품 class·전체 치수 | **추론 VLM** | 번호 박스 시트 + 영역별 치수 텍스트를 주고 JSON으로 받아 id·타입·front 중복 검증 | 양 축 정렬 이웃 기준 위치 규칙 |
| 픽셀→mm 보정 | 결정론 | 뷰별 (가장 긴 외곽선 px ÷ 전체 치수 mm)를 길이 가중 평균, 표제란 축척×용지 크기를 앵커로 이상치 제거 | 보정 불가 시 px 단위 + review |
| 3D 후보 확인 | **추론 VLM** | 원본 뷰와 상위 k개 후보의 재투영을 한 장에 그려 선택을 받음. 검증기 순위가 우선이며 불일치는 review | 생략 |

실제 스캔(HCE 76K3-42510, A3 1/3, 141dpi)에서 모델 없이도 정면·평면·우측면 3개 뷰가 정확히 분리되고
표제란·BOM·리비전·NOTE·테두리 눈금이 모두 제외되며, 두께 4t·용지 297×420이 읽히고 보정값 1.5~2.6 px/mm가
나옵니다(이론값 1.85). 저해상도(1000px 이하) 스캔은 2000px로 업스케일해 처리하지만 tesseract 품질이 떨어지므로
OCR VLM을 붙이는 것이 좋습니다.

### 비전 경로가 알아서 처리하는 스캔 특유의 문제

- 굵은 선이 Hough에서 두 줄로 잡히는 현상 → 스트로크 폭 기반 스냅으로 한 줄로 합침
- 얇은 판 뷰의 두 면 사이가 "점선"으로 오인되는 현상 → 대시 조각은 스트로크의 2배 이상 길이일 때만 이어 붙임, 스트로크보다 넓은 띠는 선이 아님
- 치수선·연장선이 두 뷰를 잇는 현상 → 폐곡선이 없는 성분은 주석으로 보고 한 뷰에만 귀속
- 기울어진 스캔의 프레임 → 수직 방향 팽창 후 연속 런 길이로 판정, 글자 마스크에 끊긴 선은 밀도로 보완
- 표제란이 "NEW DRAWING"·푸터 문구 때문에 전체로 번지는 현상 → 키워드를 근접 클러스터링하고 프레임 모서리까지 확장

## DXF 엔티티 어댑터 (`dxf_adapter.py`, `--input-mode dxf`)

실제 도면은 뷰별 레이어가 없고 ARC·bulge·블록·치수 블록이 섞여 있으므로, 레이어를 믿지 않고
시트 전체를 해석한 뒤 아래 계약으로 변환합니다. 각 단계는 결정론적 폴백을 가지며, 모델이 내린
결정은 전부 `sheet_analysis.json`의 `vlm_decision`·`vlm_trace`에 기록됩니다.

| 단계 | 방법 | 폴백 |
|---|---|---|
| 1. 엔티티 읽기 | 모든 레이어의 LINE/ARC/CIRCLE/LWPOLYLINE(bulge)/ELLIPSE/SPLINE/INSERT/DIMENSION/TEXT | - (결정론적) |
| 2. 표제란 | TEXT 정규식 → **OCR VLM**이 크롭을 원문 텍스트로 읽음 → **Reasoning VLM**이 원문과 이미지를 받아 빈 필드를 JSON으로 구조화 | 정규식 값만 유지 |
| 3. 뷰 후보 | 외곽 프레임(긴 선으로 닫힌 큰 사각형)·표제란·표 영역 제거 후, 프레임 대각선의 0.8% 간격으로 공간 클러스터링. 프레임 모서리에 붙은 클러스터는 표로 분류 | - |
| 4. 뷰 라벨 | 번호 박스를 그린 시트 이미지 + 영역 메타데이터를 **추론 VLM**에 보내 투상법·부품 class·뷰 종류·재구성 가능 여부를 JSON으로 받고, id·타입·중복(front 1개)을 검증 | 정면 = 양 축 모두에 정렬된 이웃이 있는 클러스터, 나머지는 상대 위치(1각/3각) |
| 5. 변환 | front/top/right 계약으로 변환. left/bottom/back은 축 반전, ARC는 현 오차 0.25로 선분화, DIMENSION은 `annotations[kind=dimension, axis, value]` | - |

시트 종류도 먼저 판별합니다. `t16 x 970 x 4220 - 1 SH'T` 같은 판재 캡션이 2개 이상이면
**네스팅(커팅 플랜)** 시트로 보고 정투영 재구성을 하지 않습니다. 대신 각 클러스터를 판재로 보고
`plates`에 재질·공칭 치수·도면상 외곽(리비전 클라우드 제외)·내부 부재 라벨·캡션-외곽 일치 여부를
기록하고 종료 코드 3을 반환합니다. 한 파일에 시트가 여러 장(two-up) 있어도 프레임 단위로 처리합니다.

### VLM 설정

두 역할을 분리합니다. OCR용은 작은 모델(예: Ollama의 `qwen2.5vl:3b`, `minicpm-v`, `granite3.2-vision`),
추론용은 큰 모델(예: `qwen2.5vl:32b`, OpenAI 호환 서버의 임의 VLM, 또는 Anthropic `claude-sonnet-4-5`)을 권장합니다.

```powershell
$env:CUTPLAN_OCR_BASE_URL="http://localhost:11434/v1";    $env:CUTPLAN_OCR_MODEL="qwen2.5vl:3b"
$env:CUTPLAN_REASON_PROVIDER="anthropic";                  $env:CUTPLAN_REASON_MODEL="claude-sonnet-4-5"; $env:CUTPLAN_REASON_API_KEY="..."
python main.py part.dxf --analyze-only --output-dir output
# 또는 플래그로: --ocr-model qwen2.5vl:3b --reason-model qwen2.5vl:32b --reason-base-url http://gpu-box:8000/v1
```

모델이 설정되지 않았거나 호출이 실패하면 해당 단계만 폴백으로 내려가고 `review`에 남습니다.
모델 라벨과 위치 규칙 라벨이 다르면 그 역시 `review`에 기록되어 사람이 확인할 수 있습니다.

#### OCR/Reasoning별 Local vLLM·API 혼합 실행

`experiments.sh`는 OCR과 Reasoning 실행 위치를 독립적으로 선택합니다. `local`(`vllm`도 동일)은
해당 역할의 vLLM 서버를 자동으로 시작·종료하고, `api`는 지정된 OpenAI 호환 또는 Anthropic
엔드포인트를 사용합니다. API 키는 셸 명령에 직접 쓰지 말고 환경변수로 전달합니다.

파일 상단의 `ocr`, `reason` 설정 블록을 수정하면 인자 없이 `bash experiments.sh`로 실행할 수
있습니다. 기본값은 OCR `deepseek-ai/DeepSeek-OCR-2`/GPU 0, Reasoning `Qwen/Qwen3.6-27B`/GPU 1,2,3이며,
입력은 `../data_v3/synthetic`, 출력은 `output/deepseek_ocr_qwen_reasoning_batch`입니다.
설정 우선순위는 명령행 > 환경변수 > 파일 기본값입니다.

GPU 목록의 개수가 vLLM 병렬 크기가 됩니다. `--ocr-parallel`·`--reason-parallel`이 `tensor`면
tensor parallel, `pipeline`이면 pipeline parallel로 나눕니다. 기본값은 OCR `tensor`, Reasoning
`pipeline`입니다. Qwen3.6-27B는 bf16 weight가 55.6GB라 24GB GPU 2장에 들어가지 않고, KV head가
4개라 tensor parallel은 1·2·4장만 됩니다. 그래서 RTX A5000 4장에서는 OCR에 1장, Reasoning에
3장을 pipeline parallel로 씁니다.

```bash
# 서버를 띄우거나 API를 호출하지 않고 실제 적용할 설정 확인
bash experiments.sh --dry-run

# 설정 확인 후 기본 배치 실행 (기존 결과가 있으면 --overwrite 또는 새 출력 폴더 지정)
bash experiments.sh
```

실행에 필요한 설정은 두 역할의 mode/model/GPU/parallel/port/provider/base_url/output_format과 공통 출력·실행
설정으로 모았습니다. 출력 포맷 옵션은 스크립트가 처리해 환경변수로 전달하므로 `main.py`에는
`--ocr-output-format`/`--reason-output-format`을 직접 붙이지 않습니다.
Local vLLM 기본값은 OCR 문맥 8,192·동시 sequence 16·메모리 비율 0.20,
Reasoning 문맥 16,384·동시 sequence 16·메모리 비율 0.80이며,
`--*-vllm-arg`로 덮어쓸 수 있습니다. 모델을 바꾸면 해당 모델 크기에 맞춰 메모리 비율도 조정하십시오.
준비 제한시간 기본값은 7,200초이며, vLLM 내부 timeout도 같은 값을 사용합니다
(`VLLM_ENGINE_READY_TIMEOUT_S`가 이미 설정되어 있으면 해당 값 우선).

```bash
# Local OCR + Anthropic API reasoning
export ANTHROPIC_API_KEY="..."
./experiments.sh \
  --ocr-mode local --ocr-model deepseek-ai/DeepSeek-OCR-2 --ocr-gpu 4 \
  --reason-mode api --reason-provider anthropic \
  --reason-model claude-sonnet-5 \
  --reason-api-key-env ANTHROPIC_API_KEY \
  /path/to/dxf_folder --overwrite

# OpenAI API OCR + Local vLLM reasoning
export OPENAI_API_KEY="..."
./experiments.sh \
  --ocr-mode api --ocr-provider openai --ocr-model gpt-4.1-mini \
  --ocr-base-url https://api.openai.com/v1 \
  --ocr-api-key-env OPENAI_API_KEY \
  --reason-mode local --reason-model Qwen/Qwen2.5-VL-72B-Instruct \
  --reason-gpu 5,6 \
  --reason-vllm-arg=--max-model-len=16384 \
  /path/to/dxf_folder --overwrite
```

두 역할을 모두 Local 또는 API로 지정할 수도 있습니다. Local/Local에서는 기본적으로 GPU ID가
겹치면 실행을 중단합니다. 작은 모델을 의도적으로 같은 GPU에 올릴 때만
`--allow-shared-gpus`를 사용하십시오. 전체 옵션은 `./experiments.sh --help`에서 확인합니다.

#### OCR 원문 → Reasoning 구조화 응답

DXF/이미지 어댑터는 OCR에 `Free OCR.`만 요청합니다. OCR에는 JSON Schema, 필드 목록,
좌표·종류를 포함한 출력 규격을 요구하지 않으며, 응답을 JSON으로 파싱하지 않습니다.
예를 들어 OCR은 다음과 같이 자유로운 원문 텍스트를 반환할 수 있습니다.

```text
PART NAME    BENT_SHEET
MATERIAL    SA516-70, 2t
SCALE    1/2    DIM    mm
DW'G NO    SYN-00007
```

`vlm.read_ocr_task()`가 이 원문 전체와 해당 이미지를 Reasoning 모델에 전달합니다.
이미지는 글자의 위치와 투상 기호를 확인하는 데 필요합니다. **Reasoning만**
`vlm_output.py`의 JSON 계약을 따릅니다. 같은 최상위 필드를 갖되, 작업에 해당하는
블록만 객체이고 나머지 세 블록은 `null`입니다.

| role | task | 사용하는 블록 |
|---|---|---|
| reason | text_extraction | text_extraction |
| reason | title_block | title_block |
| reason | view_labels | reasoning |
| reason | candidate_confirmation | confirmation |

OCR 원문을 받아 Reasoning이 생성한 표제란 응답 예시:

```json
{
  "schema_version": 1,
  "role": "reason",
  "task": "title_block",
  "text_extraction": null,
  "title_block": {
    "drawing_no": "SYN-00007",
    "part_name": "BENT_SHEET",
    "material": "SA516-70, 2t",
    "thickness_mm": 2.0,
    "scale": "1/2",
    "units": "mm",
    "projection": null,
    "weight_kg": null
  },
  "reasoning": null,
  "confirmation": null,
  "notes": "Projection and weight are not visible."
}
```

Reasoning 응답 예시 (뷰 하나만 있는 예시):

```json
{
  "schema_version": 1,
  "role": "reason",
  "task": "view_labels",
  "text_extraction": null,
  "title_block": null,
  "reasoning": {
    "projection": "third",
    "part_class": "bent_sheet",
    "part_class_scores": {
      "flat": 0, "cylinder": -2, "cone": -2,
      "press_formed": -1, "bent_sheet": 4, "other": -2
    },
    "reconstructable_from_views": false,
    "views": [{
      "id": 1, "type": "front", "confidence": 0.9,
      "reason": "Main front view; depth is not fully defined.",
      "overall_width_mm": 120, "overall_height_mm": 100
    }]
  },
  "confirmation": null,
  "notes": "Straight bend indicated; more views are needed for reconstruction."
}
```

`text_extraction` 블록은 `items` 배열을 갖고, 각 항목은 `text`, `bbox`([x0,y0,x1,y1],
타일 이미지의 좌상단 기준 픽셀 좌표), `kind`를 갖습니다. 좌표·종류는 OCR이 아니라
Reasoning이 원문과 이미지를 보고 생성합니다. 이미지 어댑터는 타일 경계를 벗어난 좌표를 버립니다.
`confirmation` 블록은 `pick`(1부터 시작하는 후보 번호 또는 null), `confidence`, `reason`,
`problems`(문자열 배열)을 갖습니다. 알 수 없는 수치/문자 정보는 null로 표현하며, 잘못된 타입,
클래스/뷰 종류, 비유한 수치(NaN/Infinity), 범위 밖 confidence를 거부합니다.
뷰 ID 존재 여부·중복 투상 방향 등 도면별 검증은 기존 어댑터가 이어서 수행합니다.

OCR 원문 전체는 `sheet_analysis.json` 및 배치 `prediction.json`의
`vlm_trace[]` 중 `role="ocr"`인 항목의 `raw`에 저장되며, `output_format="raw"`로 표시합니다.
성공한 Reasoning JSON 응답 전체는 `vlm_trace[].response`에 저장됩니다. 복원 후의 후보 비교 응답은
`provenance.json`의 `metadata.candidate_confirmation.response`에도 저장합니다.
Reasoning 항목의 `raw`는 모델 원문의 앞 4,000자이며, 기존의 납작한 JSON 응답을
공통 구조로 변환한 경우 `legacy_response=true`로 표시합니다(명시적 `prompt` 호환 모드에서만 허용).
형식 검증 실패나 빈 출력은
해당 단계의 `ok=false`, `response=null`, `error`로 기록하고 기존 결정론적 폴백을 사용합니다.
OCR이 성공하고 Reasoning이 실패하면 OCR은 `ok=true`, Reasoning만 `ok=false`입니다.
Reasoning이 미설정이거나 구조화에 실패하면 DXF는 정규식 값을 유지하고,
이미지의 텍스트·좌표 추출은 Tesseract로 폴백합니다. 원문만으로 좌표를 만들어내지 않습니다.
최종 `prediction`과 `title_block` 산출물의 기존 키는 유지합니다.

Reasoning의 기본 모드는 **`json_schema`**입니다. 단순히 프롬프트로 JSON을 부탁하는 것이 아니라,
서버에 JSON Schema를 전송하여 생성 단계에서 형식을 제한합니다. 로컬 vLLM을 실행하는
`experiments.sh`와 `experiments_local.sh`는 Reasoning 서버에 다음 옵션을 기본 추가합니다.

```bash
--structured-outputs-config.backend=xgrammar
```

XGrammar는 스키마를 문법으로 컴파일하고, 문법에 맞지 않는 토큰을 생성 후보에서 제외하는
라이브러리입니다. 클라이언트에 별도로 Outlines/Instructor를 겹쳐 넣지 않고 vLLM 내장 통합을
사용합니다. 서버 환경에 vLLM과 호환되는 XGrammar가 필요하며, 현재 vLLM 0.31.0의
의존성은 `xgrammar==0.2.7`입니다. 별도로 최신 XGrammar만 업그레이드하지 마십시오.
표제란·글자 구조화·뷰 분류·복원 후보 확인의 모든 Reasoning 작업에 적용합니다.

응답도 완전한 JSON과 전체 스키마로 엄격히 검증합니다. 설명문·Markdown 코드 블록·옛 납작한
JSON을 추출/보정하여 성공으로 처리하지 않습니다. `vlm_trace[].structured_output_requested=true`는
서버에 형식 제한을 요청했다는 뜻이며, 외부 서버의 내부 백엔드를 확인했다는 뜻은 아닙니다.
OCR은 항상 자유 텍스트이며, 예전 `CUTPLAN_OCR_OUTPUT_FORMAT=prompt|json_schema` 설정도
형식 제한 없이 처리합니다. 실행 스크립트에서는 이 값들을 `raw`로 정규화합니다.
이미지 타일과 표제란마다 Reasoning 구조화 호출이 추가되므로, 기존보다 Reasoning의
처리 시간/API 사용량이 늘어날 수 있습니다. 출력 형식 제한 제거는 생성 토큰 한도 제거를 뜻하지 않습니다.

```bash
# 기본값으로 OCR raw + Reasoning JSON Schema / 로컬 XGrammar 사용
bash experiments.sh --output-dir output/xgrammar_batch

# 예전 환경변수 설정이 남아 있어도 JSON Schema를 명시적으로 선택
bash experiments.sh --reason-output-format json_schema --output-dir output/xgrammar_batch

# main.py 또는 experiments_local.sh를 직접 사용할 때는 환경변수로 설정
export CUTPLAN_REASON_OUTPUT_FORMAT=json_schema
```

`json_schema` 모드는 OpenAI 호환/vLLM에 `response_format.json_schema`, Anthropic에
`output_config.format`을 전달합니다. Anthropic API는 제공자 자체의 structured output을 사용하며,
원격 API 내부에 XGrammar를 지정하는 것은 아닙니다. 미지원 서버/모델은 HTTP 오류와 응답 본문을
trace에 기록하고 해당 단계가 실패합니다. 제한 없는 요청으로 자동 재시도하지 않습니다.
지원하지 않는 서버를 계속 사용해야 한다면 `--reason-output-format prompt` 또는
`CUTPLAN_REASON_OUTPUT_FORMAT=prompt`로 호환 모드를 **명시적으로** 선택할 수 있으나,
이 모드에서는 생성 형식이 강제되지 않습니다. JSON 형식 강제는 판독 내용의 정확성을 보장하지 않습니다.
빈 응답은 `finish_reason`과 `reasoning_content` 존재 여부를 함께 기록하며, 모델의 thinking 내용을
도면 판독 결과로 대신 사용하지 않습니다.
thinking을 사용하는 모델은 모델에 맞는 vLLM reasoning parser를 설정하여 thinking과 최종
JSON을 분리해야 할 수 있습니다. 추가 서버 인자는 `--reason-vllm-arg=...`로 전달합니다.

공식 문서: [DeepSeek-OCR-2 사용 가이드 및 Free OCR. 예제](https://github.com/vllm-project/recipes/blob/main/DeepSeek/DeepSeek-OCR-2.md),
[vLLM Structured Outputs](https://docs.vllm.ai/en/v0.31.0/features/structured_outputs/),
[XGrammar 소스 및 사용 안내](https://github.com/mlc-ai/xgrammar),
[XGrammar 기술 논문](https://arxiv.org/abs/2411.15100),
[Anthropic Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

### 산출물

- `output/analysis/sheet.png`: 뷰 후보 박스와 라벨이 그려진 시트
- `output/analysis/sheet_labeled.png`, `title_block.png`: 모델에 보낸 이미지
- `output/analysis/sheet_analysis.json`: 프레임, 표제란, 클러스터, 라벨·신뢰도·근거, 판재 목록, 모델 호출 기록, 검토 항목
- 정투영 시트는 이어서 `provenance.json`, `report.md`, `reconstruction.step`, `parameters.json`

레거시 `FRONT/TOP/RIGHT` 레이어 계약은 `--dxf-mode layers`로 계속 쓸 수 있습니다.

## 전개도 단계: class → 치수 → 전개 (v3)

v3는 Reasoning VLM이 판단할 때 프로젝트의 `../skills/` 도메인 문서를 시스템 프롬프트로 불러옵니다
(`knowledge.py`의 `load_domain_prompt(topic)`. topic은 md 파일 이름이고, 루트는 `CUTPLAN_SKILLS_DIR`로 바꿀 수 있습니다).
불러온 문서의 경로와 sha256은 `vlm_trace[].skills`에 기록됩니다.

| 순서 | 담당 | 읽는 skill (`knowledge.STAGE_TOPICS`) | 결과 |
|---|---|---|---|
| 1. class 결정 | 추론 VLM `view_labels` | `unfold_rules`, `unfold_extract` | `part_class` (flat / bent_sheet / cylinder / cone / press_formed / other) |
| 2. 치수 추출 | 추론 VLM `unfold_params` | `unfold_extract`, `unfold_rules`, `drawing_conventions_kr` | skill 필드명 그대로: `inner_dia`(안지름), `length`, `large_inner_dia`, `small_inner_dia`, `cone_height`, `segments`/`bend_angles`/`bend_radii`, `outline`, `straight_flange` … |
| 3. 전개 계산 | 코드 (`unfold.develop`) | `unfold_rules.md`, `unfold_pipeline_tools.md` §3 공식 | 원통 L = π(ID+t), 원뿔대 R1/R2/θ (중립 지름), 절곡 Σ(외측−setback)+ΣBA (K는 R/t 표), 헤드 블랭크 ≈ 1.275·ID + 2·SF, 평판은 윤곽 그대로 |
| 4. 출력 | `unfold.export_flat_pattern` | - | `flat_pattern.json`, `flat_pattern.dxf` (R12, layer BLANK/BEND/INFO), `flat_pattern.png` |

class 이름은 skill의 part_type으로 매핑됩니다: cone → `cone_frustum`, press_formed → `head`.
모델이 비워 둔 필드는 뷰의 전체 치수(외경 기준)를 `ID = OD − 2t`로 환산해 채우고, `sources`에 `overall_dimensions`로 표시합니다.
class가 `other`이거나 결정되지 않았으면(`--no-vlm`) 전개 단계는 `skipped`가 됩니다. `--no-unfold`를 주면 이 단계를 끕니다.
배치 실행은 `flat_patterns.json`과 `flat_patterns.md`를 만들고, 옆에 `label.json`이 있으면 추론이 끝난 뒤 `flat_pattern`과의 상대오차를 기록합니다.

## 현재 구현 범위와 확장 위치

현재 와이어프레임 후보는 뷰의 선분 끝점을 공유 축으로 결합하고, 모든 투영이
원본 선분으로 지지되는 최소 모서리 그래프입니다. 일반 도면의 모든 대응 조합이나
모든 가능한 입체를 열거하지 않습니다. `CandidateGenerator`에 탐색/분기 전략을 추가할 수 있습니다.

원형 관측은 깊이나 관통 여부를 알 수 없으므로 특징 가설로 저장합니다. STEP에는
선분 와이어프레임만 출력하며, 면·솔리드·실제 홀을 생성하지 않습니다. CAD 커널을
연결해 이 부분을 확장할 수 있습니다. PDF/이미지 입력은 `DrawingInterpreter.segment_views`
앞에 벡터화·뷰 분할 어댑터를 연결해야 합니다.

검사 상태는 `pass`, `fail`, `unknown`을 구분합니다. 연결성과 판 두께의 기본 조건은
검사하지만 체적, 충돌, 절곡, 전개, 공구 접근은 솔리드가 필요하므로 `unknown`입니다.
점수는 수행 가능한 검사의 적합도이며 제작 가능성의 인증이 아닙니다. 미확인 조건은
`AmbiguityResolver`의 검토 요청에 남깁니다. 유효 후보가 없으면 보고서/근거만 출력하고
종료 코드 2를 반환합니다. 입력 오류는 종료 코드 1입니다.

같은 출력 폴더에 기존 생성 파일이 있으면 기본적으로 덮어쓰기를 거부합니다.
`--overwrite`를 명시하면 생성 파일을 교체하며, 유효 후보가 없는 실행에서는
이전 `reconstruction.step`과 `parameters.json`을 제거하여 오래된 결과의 재사용을 방지합니다.

## API 사용

```python
from drawing_io import load_drawing
from pipeline import ReconstructionPipeline
from step6 import ReconstructionExporter

result = ReconstructionPipeline(tolerance=0.01).run(load_drawing("examples/box.json"))
valid_ids = {evaluation.candidate_id for evaluation in result.evaluations if evaluation.valid}
candidate = next((c for c in result.candidates if c.id in valid_ids), None)
if candidate is not None:
    ReconstructionExporter().export_step(candidate, "output/model.step")
```

기존 초안의 오타 `DrawingInterprete`는 `DrawingInterpreter`의 별칭으로 유지합니다.

## 여러 DXF 폴더 일괄 예측·복원

입력 경로가 폴더이거나 여러 개인 경우 배치 모드가 자동으로 활성화됩니다. 각 폴더를 재귀적으로
탐색해 DXF마다 독립적으로 형상 분류와 Reconstruction을 실행하고, 마지막에 결과를 종합합니다.

```bash
python main.py \
  /path/to/dxf_folder_a \
  /path/to/dxf_folder_b \
  --batch \
  --input-mode dxf \
  --output-dir output/batch_run
```

Claude API 설정 스크립트로 여러 폴더를 넘길 수도 있습니다. API 키는 파일에 저장하지 않습니다.

```bash
export ANTHROPIC_API_KEY="..."
CUTPLAN_BATCH_OUTPUT=output/claude_batch \
  ./experiments_claude.sh /path/to/dxf_folder_a /path/to/dxf_folder_b
```

하위 폴더를 탐색하지 않으려면 `--no-recursive`, 기존 결과를 교체하려면 `--overwrite`, VLM 없이
결정론적 폴백만 검증하려면 `--no-vlm`을 사용합니다.

```text
output/batch_run/
├── predictions.json          # 모든 도면의 PREDICTION 종합
├── reconstruction.json       # 모든 개별 Reconstruction의 상태·후보·산출물 색인
├── accuracy.md               # label.json이 있는 샘플의 클래스별 정확도 표
└── <DXF 이름>/
    ├── prediction.json       # 해당 DXF의 예측과 상태
    ├── analysis/
    │   └── sheet_analysis.json
    ├── provenance.json
    ├── report.md
    ├── parameters.json       # 유효 후보가 있을 때
    └── reconstruction.step   # 유효 후보가 있을 때
```

서로 다른 DXF는 원점과 좌표계가 독립적이므로 하나의 STEP 형상으로 결합하지 않습니다.
`reconstruction.json`은 각 도면별 복원 결과를 하나의 manifest로 종합합니다.

각 prediction에는 `final_part_class`와 여섯 클래스의 `part_class_probabilities`가 포함됩니다.
Anthropic Messages API가 내부 logits를 제공하지 않으므로, reasoning VLM이 보고한 상대 점수에
수치적으로 안정적인 softmax를 적용한 추정값이며 `part_class_probability_source`에 그 출처를 기록합니다.
동일 폴더의 `label.json.class`는 예측이 끝난 뒤에만 읽어 `accuracy.md`와
`predictions.json.accuracy`의 `label / 개수 / 실제 맞춘 횟수 / accuracy` 표를 계산합니다.

## 형식 참고

- [ezdxf LWPOLYLINE 공식 문서](https://ezdxf.readthedocs.io/en/stable/dxfentities/lwpolyline.html)
- [STEP Tools wireframe representation 정의](https://www.steptools.com/docs/stp_aim/html/t_geometrically_bounded_wireframe_shape_representation.html)
- [STEP Tools geometric_curve_set 정의](https://www.steptools.com/docs/stp_aim/html/t_geometric_curve_set.html)
