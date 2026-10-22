# 도면 판독 단계별 실행

DXF 도면 1장을 13단계로 나눠 한 단계씩 돌리고, 단계마다 결과를 파일로 확인하는 방법이다. 2026-10-22 에 `reader-stages` 브랜치에서 만들었다.

- 단계마다 파이썬 파일이 하나씩 있고 ([`cutplan_agent/reader/stages/`](../../cutplan_agent/reader/stages/)), 각각 따로 실행된다.
- `main.py --batch --input-mode dxf` 도 이 단계들을 차례로 부른다. 그래서 한 번에 돌린 결과와 단계별로 손으로 돌린 결과가 같다 (`tests/test_stages.py` 가 확인한다).
- 단계는 앞 단계가 남긴 파일만 읽는다. 앞 단계를 다시 돌리지 않고 한 단계만 다른 모델로 다시 돌릴 수 있다.

적용 범위는 DXF 입력(`--input-mode dxf`, 기본 `--dxf-mode auto`)이다. 이미지·PDF 입력(`--input-mode vision`), `--dxf-mode layers`, `--batch` 없이 도면 1장을 주는 실행은 아직 예전처럼 한 번에 돈다.

## 1. 작업 폴더

도면 1장마다 작업 폴더가 하나 있다. `main.py --batch` 에서는 `<출력 폴더>/<도면 이름>/` 이다.

```
<work>/
  stages/01_read.json … 13_export.json   단계마다 하나. 이번에 새로 생긴 것
  analysis/                               그림과 sheet_analysis.json (예전과 같은 위치·내용)
    title_block.png      ③ OCR 에 넣은 표제란 그림
    sheet_labeled.png    ⑥ 추론 모델에 넣은 그림 (빨간 번호 상자 = 뷰 후보)
    sheet.png            ⑦ 최종 라벨을 그린 시트
    sheet_analysis.json  ⑦ 판독 결과 전체
    candidates.png       ⑫ 원래 뷰와 복원 후보 투영을 나란히 그린 그림
  flat_pattern.json/.dxf/.png             ⑩ 전개도
  provenance.json, report.md, reconstruction.step, parameters.json   ⑬ 3D 복원 결과
  prediction.json                         --batch 만: 예측 요약과 정답 비교
```

단계 파일의 공통 필드:

| 필드 | 뜻 |
|---|---|
| `stage`, `step` | 단계 이름과 번호 |
| `status` | `done`, `skipped` (이유는 `reason`), `failed` (오류는 `error`) |
| `inputs` | 이 단계가 읽은 파일 (작업 폴더 기준 경로) |
| `trace` | 모델 단계만. 모델 호출 기록: 모델 이름, 입력 그림, 원문 응답(`raw`), 검증된 응답(`response`), 오류, 걸린 시간, 붙인 skill 문서와 sha256 |

## 2. 단계

모델 열이 비어 있으면 모델 없이 코드만으로 도는 단계다. 코드 열은 단계가 부르는 함수다.

| # | 단계 | 하는 일 | 모델 | 읽는 것 | 남기는 것 | 코드 |
|---|---|---|---|---|---|---|
| 01 | `read` | DXF 엔티티를 레이어와 상관없이 모두 읽는다 | | DXF | 엔티티 목록, 파일 단위, 원본 sha256 | `dxf_reader.read_dxf` |
| 02 | `title_regex` | 표제란 위치를 찾고 정규식으로 필드를 읽는다 | | 01 | 표제란 영역, 필드와 출처, 못 읽은 필드(`missing`) | `dxf_adapter.find_title_region`, `regex_title_block` |
| 03 | `title_ocr` | 표제란 그림을 OCR 모델이 받아쓴다 | OCR | 01, 02 | 받아쓴 원문(`text`), `title_block.png` | `dxf_adapter.render_title_block`, `vlm.ocr_text` |
| 04 | `title_fields` | 추론 모델이 OCR 원문을 표제란 필드로 정리하고, 02 가 못 읽은 필드만 채운다 | 추론 | 02, 03 | 모델 답(`fields`), 최종 표제란 | `vlm.structure_ocr_text`, `dxf_adapter.apply_title_fields` |
| 05 | `views` | 도면 틀, 제외 영역(표제란·표), 뷰 후보(공간 군집), 도면 종류(정투상/네스팅/기타) | | 01, 02 | 뷰 후보와 각 뷰의 엔티티, 도면 종류와 근거 | `dxf_adapter.find_views` |
| 06 | `view_labels` | 위치로 먼저 라벨을 붙이고, 추론 모델이 뷰 종류·투상법·형상(part_class)·복원 가능 여부를 정한다. 둘이 다르면 review 에 남긴다. 네스팅 도면은 판 목록을 만든다 | 추론 (skill 문서 2개) | 01, 04, 05 | 뷰 라벨, 모델 답 전체(`decision.raw` 포함), review, `sheet_labeled.png` | `dxf_adapter.label_sheet`, `label_with_vlm` |
| 07 | `sheet` | 01~06 을 합쳐 `sheet_analysis.json` 과 `sheet.png` 를 쓴다 | | 01~06 | `analysis/sheet_analysis.json` (`vlm_trace` 는 03·04·06 의 호출) | `dxf_adapter.write_sheet_analysis` |
| 08 | `document` | 라벨 붙은 뷰를 3D 복원용 front/top/right 계약으로 바꾼다 (호 분할, left/bottom/back 미러, 치수 부착, 축척 검사). 네스팅 도면은 여기서 멈춘다 | | 01, 06, 07 | `DrawingDocument` 전체 | `dxf_adapter.build_document` |
| 09 | `unfold_params` | 정해진 형상의 전개 파라미터를 읽는다. 모델이 비운 값은 전체 치수로 채운다 | 추론 (skill 문서 3개) | 07, 08 | 파라미터와 필드별 출처(`sources`), 모델 호출 | `unfold.read_unfold_params` |
| 10 | `develop` | 전개 공식을 코드로 계산하고 전개도를 쓴다 | | 09 | 블랭크 값, `flat_pattern.*` | `unfold.develop_unfold` |
| 11 | `reconstruct` | 3D 와이어프레임 후보를 만들고 검증기로 순위를 매긴다. 06 에서 복원 불가로 판단하면 건너뛴다 | | 07, 08 | 후보, 검증 결과, review 요청 전체 | `reconstruct/pipeline.py` |
| 12 | `confirm` | 추론 모델이 원래 뷰와 후보 투영을 비교해 하나를 고른다. 검증기 순위가 우선이고, 다르면 review 에 남긴다 | 추론 | 11 | 고른 후보, 바뀐 review 요청, `candidates.png` | `vision_adapter.confirm_candidates` |
| 13 | `export` | `provenance.json`, `report.md`, 유효 후보가 있으면 `reconstruction.step`, `parameters.json` | | 11, 12 | 결과 요약 | `reconstruct/step6.py` |

단계별 skill 문서는 [`reader/knowledge.py`](../../cutplan_agent/reader/knowledge.py) 의 `STAGE_TOPICS` 에 고정돼 있다 (06: `unfold_rules`, `unfold_extract` / 09: 여기에 `drawing_conventions_kr` 추가).

예전에는 09 의 모델 원문이 어디에도 남지 않았다 (`sheet_analysis.json` 의 `vlm_trace` 를 07 에서 쓰기 때문). 이제 `stages/09_unfold_params.json` 의 `trace` 에 남는다.

## 3. 실행

모든 명령은 레포 루트에서 실행한다. v3 의존성은 아직 uv 환경에 없어서 `--with` 로 붙인다. 아래에서는 줄여서 `$PY` 로 쓴다.

```bash
PY="uv run --with requests --with opencv-python-headless --with pytesseract python"
DXF=data_v3/synthetic/cone_0019/cone_0019.dxf
W=runs/reader/check/cone_0019
```

모델은 `main.py` 와 같은 옵션(`--ocr-model`, `--ocr-base-url`, `--reason-model`, `--reason-base-url`, `--*-provider`)이나 환경변수 `CUTPLAN_OCR_*`, `CUTPLAN_REASON_*` 로 정한다 ([`reader/vlm.py`](../../cutplan_agent/reader/vlm.py) 머리말). 둘 다 없으면 모델 단계는 `skipped` 가 된다.

### 3.1 한 번에

```bash
# 배치 (도면 1장도 된다). 결과는 runs/reader/check/cone_0019/ 와 집계 파일
PYTHONPATH=. $PY cutplan_agent/reader/main.py --batch --input-mode dxf \
  --reason-model <추론 모델> --reason-base-url http://127.0.0.1:8001/v1 \
  --ocr-model deepseek-ai/DeepSeek-OCR-2 --ocr-base-url http://127.0.0.1:8000/v1 \
  --output-dir runs/reader/check $DXF

# 도면 1장, 단계마다 한 줄씩 결과를 출력한다. 집계 파일과 prediction.json 은 만들지 않는다
PYTHONPATH=. $PY cutplan_agent/reader/stages/run.py $DXF $W --no-vlm
PYTHONPATH=. $PY cutplan_agent/reader/stages/run.py $DXF $W --to sheet <모델 옵션>   # 07 까지만
```

`run.py` 는 `main.py --batch` 의 `--analyze-only`, `--no-unfold`, `--no-confirm`, `--units`, `--tolerance`, `--max-candidates`, `--projection` 을 그대로 받는다. 옵션으로 건너뛴 단계도 `skipped` 파일을 남긴다.

### 3.2 한 단계씩

```bash
PYTHONPATH=. $PY cutplan_agent/reader/stages/read.py $DXF $W
PYTHONPATH=. $PY cutplan_agent/reader/stages/title_regex.py $W
PYTHONPATH=. $PY cutplan_agent/reader/stages/title_ocr.py $W --ocr-model deepseek-ai/DeepSeek-OCR-2 --ocr-base-url http://127.0.0.1:8000/v1
PYTHONPATH=. $PY cutplan_agent/reader/stages/title_fields.py $W --reason-model <추론 모델> --reason-base-url http://127.0.0.1:8001/v1
PYTHONPATH=. $PY cutplan_agent/reader/stages/views.py $W
PYTHONPATH=. $PY cutplan_agent/reader/stages/view_labels.py $W --reason-model ... --reason-base-url ...
PYTHONPATH=. $PY cutplan_agent/reader/stages/sheet.py $W
PYTHONPATH=. $PY cutplan_agent/reader/stages/document.py $W
PYTHONPATH=. $PY cutplan_agent/reader/stages/unfold_params.py $W --reason-model ... --reason-base-url ...
PYTHONPATH=. $PY cutplan_agent/reader/stages/develop.py $W
PYTHONPATH=. $PY cutplan_agent/reader/stages/reconstruct.py $W
PYTHONPATH=. $PY cutplan_agent/reader/stages/confirm.py $W --reason-model ... --reason-base-url ...
PYTHONPATH=. $PY cutplan_agent/reader/stages/export.py $W
```

각 스크립트는 상태, 핵심 결과 몇 줄, 단계 파일 경로를 출력한다. 단계별 옵션은 `--help` 로 본다 (`views.py --gap-ratio`, `view_labels.py --projection`, `document.py --units`, `reconstruct.py --tolerance --max-candidates`).

### 3.3 한 단계만 다시

```bash
# OCR 모델만 바꿔서 03 을 다시 → 04 부터 다시
PYTHONPATH=. $PY cutplan_agent/reader/stages/title_ocr.py $W --ocr-model <다른 OCR 모델> --ocr-base-url ...
PYTHONPATH=. $PY cutplan_agent/reader/stages/run.py $W --from title_fields <모델 옵션>
```

`run.py <work> --from <단계>` 는 그 단계부터 끝까지(또는 `--to` 까지) 돈다. 앞 단계는 작업 폴더에 있는 파일을 그대로 쓰므로 DXF 경로를 주지 않아도 된다.

### 3.4 지켜지는 규칙

- 단계를 저장하면 그 뒤 단계의 `stages/` 파일을 지운다. `stages/` 에 파일이 있으면 지금 있는 앞 단계 파일로 계산한 결과다. `analysis/` 의 그림과 `flat_pattern.*`, `provenance.json` 같은 결과 파일은 지우지 않고, 그 단계를 다시 돌릴 때 덮어쓴다.
- 앞 단계 파일이 없거나 `failed` 이면 다음 단계는 돌지 않고 이유를 출력한다 (종료 코드 2).
- 단계에서 오류가 나면 `failed` 파일을 남기고 종료 코드 1 로 끝난다. `main.py --batch` 와 `run.py` 는 남은 단계를 `skipped` 로 남긴다.

## 4. 결과 보기

```bash
# 단계 상태 한눈에
python3 - $W <<'EOF'
import json, sys, pathlib
for f in sorted(pathlib.Path(sys.argv[1], "stages").glob("*.json")):
    d = json.loads(f.read_text())
    print(f.name, d["status"], d.get("reason") or d.get("error") or "")
EOF

# 모델 원문 (03, 04, 06, 09, 12)
python3 - $W/stages/09_unfold_params.json <<'EOF'
import json, sys
for role, calls in json.load(open(sys.argv[1])).get("trace", {}).items():
    for t in calls:
        print("---", role, t.get("task"), "ok=", t["ok"], t.get("error", ""))
        print(t.get("raw", ""))
EOF
```

그림은 `analysis/` 에서 연다. 동료의 기준 결과 `runs/reader/deepseek_ocr_qwen_reasoning_skills/<도면>/` 에는 `stages/` 가 없지만 `analysis/` 와 결과 파일은 같은 이름이라 나란히 비교할 수 있다.

## 5. 함수 단위로 부르기

단계 파일마다 `run(work, ...)` 함수가 있다. 작업 폴더 경로와 JSON 으로 표현되는 옵션(모델 클라이언트 제외)을 받고, 저장한 단계 기록(dict)을 돌려준다. 나중에 orchestrator 가 단계를 tool 로 부를 때 이 함수를 쓴다.

```python
from cutplan_agent.reader.stages import title_ocr, run
from cutplan_agent.reader.vlm import make_clients

ocr, reason = make_clients(ocr_model="...", ocr_base_url="...")
title_ocr.run("runs/reader/check/cone_0019", ocr=ocr)
run.run_drawing(dxf, work, (ocr, reason), last="sheet")   # 여러 단계
```

단계 안의 함수(`regex_title_block`, `find_views`, `label_with_vlm`, `read_unfold_params` 등)도 따로 import 해서 부를 수 있다. 단계 사이에 넘기는 객체를 JSON 으로 바꾸는 함수는 [`stages/workspace.py`](../../cutplan_agent/reader/stages/workspace.py) 에 있다.
