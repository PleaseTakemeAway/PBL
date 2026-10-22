# 도면 판독기를 단계별로 돌려 보기

`cutplan_agent/reader/stages/` 의 단계 스크립트로 도면 1장을 한 단계씩 돌리고, 단계마다 결과를 눈으로 확인하는 방법이다. 2026-10-22 기준.

`main.py` 는 이 단계들을 순서대로 부르는 진입점이다 (`stages/sequence.py`). 단계를 하나씩 돌린 결과와 `main.py` 를 한 번 돌린 결과는 파일 단위로 같다 (`tests/test_stages.py`).

## 1. 단계

DXF 를 엔티티로 읽는 경우(`--input-mode dxf`)의 순서다. 각 단계는 앞 단계가 작업 폴더에 남긴 파일을 읽고 자기 파일을 쓴다. 작업 폴더는 `<output-dir>/analysis/` 이고, 최종 산출물은 `<output-dir>/` 에 둔다.

| # | 단계 | 하는 일 | 모델 | 읽는 파일 | 쓰는 파일 |
|---|---|---|---|---|---|
| 1 | `read` | DXF 의 모든 엔티티를 레이어와 상관없이 읽는다 | 없음 | DXF | `entities.json` |
| 2 | `title` | 표제란. 정규식으로 먼저 읽고, 못 채운 필드가 있을 때만 OCR 모델이 `title_block.png` 를 읽고 추론 모델이 구조화한다 | OCR, 추론 | `entities.json` | `title.json`, `title_block.png` |
| 3 | `segment` | 도면 틀·표제란·표를 빼고 형상을 뷰 후보로 묶는다. 도면 종류(정투상 / 네스팅 / 불명)를 정한다 | 없음 | `entities.json` | `views.json` |
| 4 | `label` | 뷰 종류, 투상법, 형상(part_class), 뷰만으로 복원 가능한지. 위치 기반 판단이 먼저 있고 추론 모델이 `sheet_labeled.png` 를 보고 정한다 | 추론 | 1~3 의 파일 | `sheet_analysis.json`, `sheet_labeled.png`, `sheet.png` |
| 5 | `document` | 정면·평면·우측 뷰를 3D 복원용 문서로 바꾸고, 표제란 척도를 도면 크기와 대조한다 | 없음 | `entities.json`, `views.json`, `sheet_analysis.json` | `document.json` |
| 6 | `unfold` | 형상별 전개 파라미터를 추론 모델이 읽고, 빈 값은 전체 치수로 채운 뒤 코드가 전개도를 계산한다 | 추론 | `document.json` (없으면 `sheet_analysis.json`) | `unfold.json`, 최종 `flat_pattern.json/.dxf/.png` |
| 7 | `reconstruct` | 3D 와이어프레임 후보를 만들고 평가한다. 추론 모델이 재투영 그림 `candidates.png` 를 보고 후보를 확인한다 | 추론 | `document.json` | `reconstruct.json`, `candidates.png`, 최종 `provenance.json`, `report.md`, `reconstruction.step`, `parameters.json` |

- 모델이 꺼져 있으면 모든 모델 단계는 결정적 폴백으로 끝까지 간다. 이때 `title_block.png`, `sheet_labeled.png`, `candidates.png` 는 생기지 않고, 형상이 정해지지 않아 6단계는 `skipped` 다.
- 네스팅(커팅플랜) 도면이면 5단계가 종료 코드 3으로 멈춘다. 판 목록은 `sheet_analysis.json` 의 `plates` 에 있다.
- 이미지·PDF 입력과 `--input-mode vision` 은 아직 단계로 나누지 않았다. 5단계 `document` 가 입력을 받아 한 번에 판독하고 (`vision_adapter.analyze_image`), 6·7단계는 같다. JSON 계약 입력과 `--dxf-mode layers` 도 5단계에서 바로 읽는다.

## 2. 명령

레포 루트에서 실행한다. 아래 함수를 한 번 정의해 두면 편하다 (bash, zsh).

```bash
st() { local s=$1; shift; PYTHONPATH=. uv run --with requests --with opencv-python-headless --with pytesseract python cutplan_agent/reader/stages/$s.py "$@"; }
```

모델 없이 (GPU 불필요):

```bash
D=runs/reader/check/cone_0019
st read data_v3/synthetic/cone_0019/cone_0019.dxf --output-dir $D
for s in title segment label document unfold reconstruct; do st $s --output-dir $D --no-vlm; done
```

모델을 붙일 때는 서버를 띄워 둔다. `experiments/experiments.sh` 는 배치가 끝나면 서버를 끄므로, 단계를 하나씩 볼 때는 서버를 따로 띄운다. 옵션은 `experiments.sh` 와 같다.

```bash
CUDA_VISIBLE_DEVICES=0 vllm serve deepseek-ai/DeepSeek-OCR-2 --host 127.0.0.1 --port 8000 \
  --max-model-len=8192 --max-num-seqs=16 --gpu-memory-utilization=0.20
CUDA_VISIBLE_DEVICES=1 vllm serve <추론 모델> --host 127.0.0.1 --port 8001 \
  --max-model-len=16384 --gpu-memory-utilization=0.80 --structured-outputs-config.backend=xgrammar
```

모델 설정은 환경변수로 한 번 주면 모든 단계가 쓴다. 명령마다 `--ocr-model`, `--reason-model`, `--ocr-base-url`, `--reason-base-url` 로 줘도 된다. 모델을 쓰지 않는 단계는 이 옵션을 무시하므로 모든 단계에 같은 옵션을 줘도 된다.

```bash
export CUTPLAN_OCR_MODEL=deepseek-ai/DeepSeek-OCR-2 CUTPLAN_OCR_BASE_URL=http://127.0.0.1:8000/v1
export CUTPLAN_REASON_MODEL=<추론 모델> CUTPLAN_REASON_BASE_URL=http://127.0.0.1:8001/v1
st read data_v3/synthetic/cone_0019/cone_0019.dxf --output-dir $D
st title --output-dir $D        # 끝나면 title.json, title_block.png 를 본다
st segment --output-dir $D
st label --output-dir $D        # sheet_labeled.png, sheet_analysis.json
st document --output-dir $D
st unfold --output-dir $D       # flat_pattern.png
st reconstruct --output-dir $D  # candidates.png, report.md
```

각 단계는 끝나면 요약 JSON 을 표준출력에 찍는다. 종료 코드는 성공 0, 실패 1, 네스팅 도면 3 이다. 앞 단계 파일이 없으면 어느 단계를 먼저 돌려야 하는지 알려 주고 멈춘다.

## 3. 무엇을 볼까

| 단계 | 그림 | JSON 에서 볼 곳 |
|---|---|---|
| title | `title_block.png` (OCR 이 읽은 그림) | `title.json` 의 `title_block` 값과 필드별 출처 `sources` (`regex` 또는 `vlm_reason:…+vlm_ocr:…`), `trace` 의 OCR 원문 `raw` |
| segment | 아직 없다. 4단계의 `sheet_labeled.png` 가 3단계의 뷰 후보를 번호 상자로 그린다 | `views.json` 의 `sheet_type`, `views[].bbox`, `views[].counts`, `segmentation.dropped` |
| label | `sheet_labeled.png` (모델 입력), `sheet.png` (최종 라벨) | `sheet_analysis.json` 의 `views[].label/reason/source`, `part_class`, `part_class_probabilities`, `review` (위치 판단과 모델이 다른 곳) |
| document | 없다 | `document.json` 의 `metadata.dimensions`, `metadata.drawing_scale`, `metadata.review` |
| unfold | `flat_pattern.png` | `unfold.json` 의 `record.params` 와 필드별 출처 `record.sources` (`vlm_reason:…` 또는 `overall_dimensions`), `trace` |
| reconstruct | `candidates.png` | `report.md`, `reconstruct.json` 의 `candidate_confirmation`, `trace` |

단계 JSON 의 `trace` 에는 그 단계가 부른 모델 호출이 모두 남는다. 프롬프트에 붙인 skill 문서의 sha256, 원문 응답(`raw`, 추론 모델은 앞 4000자), 검증된 응답(`response`), 오류(`error`), 걸린 시간이 들어 있다. `sheet_analysis.json` 의 `vlm_trace` 는 1~4단계의 호출을 모은 것이다.

```bash
python3 - $D/analysis/title.json <<'EOF'
import json, sys
for t in json.load(open(sys.argv[1]))["trace"]:
    print("---", t["role"], t.get("task"), "ok=", t["ok"], t.get("error", ""))
    print(t.get("raw", ""))
EOF
```

## 4. 다시 돌리기와 고쳐서 이어 돌리기

- 한 단계를 다시 돌리면 그 단계와 이후 단계의 출력을 먼저 지운다. 그래서 작업 폴더에 서로 다른 실행의 결과가 섞이지 않는다. 지울 파일이 있으면 `--overwrite` 가 있어야 돌고, 없으면 지우지 않고 멈춘다. 동료의 기준 결과 폴더를 실수로 덮지 않게 하려는 것이다.
- `main.py` 와 `batch.py` 는 자기 출력 확인을 먼저 하고 단계에는 `--overwrite` 로 넘긴다.
- 사람이 판단을 고쳐서 이어 돌릴 수 있다. 예를 들어 `sheet_analysis.json` 에서 뷰 라벨이나 `part_class` 를 고치고 `st document --output-dir $D --overwrite` 부터 다시 돌리면, 5단계는 고친 라벨로, 6단계는 고친 형상으로 계산한다.

## 5. 파이썬에서 부르기

단계마다 `run(work_dir, ...)` 함수가 있고, 인자는 경로와 숫자·문자열이며 결과는 JSON 으로 바꿀 수 있는 dict 다. 나중에 모델이 조율할 때 tool 로 노출할 수 있는 형태다.

```python
from cutplan_agent.reader.stages import label
from cutplan_agent.reader.vlm import make_clients

summary = label.run(
    "runs/reader/check/cone_0019/analysis",
    clients=make_clients(),  # CUTPLAN_* 환경변수. disabled=True 면 모델 없이
    output_dir="runs/reader/check/cone_0019",
    overwrite=True,
)
```

단계 함수는 그 단계의 로직을 직접 갖지 않고 `dxf_adapter.py`, `unfold.py` 등 원래 모듈의 함수를 부른다. 단계 파일이 하는 일은 입력 파일을 읽고, 함수를 부르고, 결과와 모델 호출 기록을 파일로 남기는 것이다. 단계 사이 파일의 이름과 읽고 쓰는 방법은 `stages/workdir.py` 에 모여 있다.
