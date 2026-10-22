# 도면 판독 단계별 실행 요약

복사해서 붙여 넣을 명령만 모았다. 단계마다 무엇을 읽고 남기는지는 [stages.md](stages.md) 에 있다.

모든 명령은 레포 루트(`~/developer/pbl`)에서 실행한다. bash 와 zsh 에서 똑같이 된다.

## 0. 모델 서버 (한 번만, 따로 띄워 둔다)

```zsh
# tmux 같은 다른 창에서. Ctrl-C 로 끈다. Qwen3.6-27B 는 뜨는 데 몇 분 걸린다
./experiments/serve.sh --vllm-bin ~/venvs/vllm-0.31/bin/vllm
```

떴는지 확인:

```zsh
curl -s http://127.0.0.1:8000/v1/models   # OCR (DeepSeek-OCR-2)
curl -s http://127.0.0.1:8001/v1/models   # 추론 (Qwen3.6-27B)
```

## 1. 새 터미널마다 한 번

```zsh
cd ~/developer/pbl
export PYTHONPATH=.                              # 없으면 No module named 'cutplan_agent'
. runs/vllm/ocr.env; . runs/vllm/reason.env      # 없으면 모델 단계가 skipped 로 끝난다
echo $CUTPLAN_OCR_MODEL $CUTPLAN_REASON_MODEL    # 모델 이름 두 개가 나오면 된다
```

`. 파일` 은 `source 파일` 과 같다. 파일 안의 `export` 줄을 지금 셸에 적용한다. 이 파일들은 서버가 뜨면 생기고 서버가 꺼지면 지워진다.

모델 없이 코드만으로 돌려 보려면 env 를 source 하지 않은 새 셸에서 돌린다.

## 2. 판독할 도면 고르기

```zsh
# 합성 도면 (옆에 정답 label.json 이 있다). 30개: ls data_v3/synthetic
DXF=data_v3/synthetic/cone_0019/cone_0019.dxf
W=runs/reader/check/cone_0019                    # 결과를 쓸 작업 폴더
```

실도면은 DWG 다. 00 단계(convert)가 DXF 로 바꾸고 열리는지 검사한다. 01 부터는 바꾼 DXF 를 읽으므로 `--dxf` 가 필요 없다.

```zsh
DWG="test_data/cases/S-2120/input_drawings/VP-S-2120-DWG-003_R0 (DETAIL OF MANHOLE).dwg"
W=runs/reader/cases/S-2120/DWG-003
uv run python scripts/reader/run_stages.py $W 0 --drawing "$DWG" --show   # 00 → $W/input/*.dxf
```

- reader 는 DXF 만 읽는다. DWG 는 AutoCAD 전용 바이너리 형식이라 도면을 읽는 파이썬 라이브러리(ezdxf)가 열지 못한다. DXF 는 같은 내용을 공개된 텍스트 형식으로 쓴 것이다. (v2 의 `ingest_drawing` 은 안에서 같은 `dwg2dxf` 로 바꾼다.)
- AutoCAD 에서 저장한 DXF 가 있으면 그것이 가장 정확하다. 원본 프로그램이 썼으니 빠지거나 깨지는 것이 없다. `--drawing` 에 DXF 를 주면 바꾸지 않고 그대로 쓴다. DWG 만 받았으면 회사에 DXF 로 달라고 하는 것이 가장 좋다 ([company_questions.md](../domain/company_questions.md) Q12).
- DWG 는 GNU LibreDWG `dwg2dxf` 로 바꾼다 (`~/.local/bin/dwg2dxf`, 없으면 `scripts/install_libredwg.sh`). LibreDWG 는 DWG 형식을 역설계한 오픈소스라, R2007 DWG 일부를 읽지 못하면서도 종료 코드 0 으로 빈 DXF 를 쓰고, 일부 도면에서는 글자 뒤에 실행마다 다른 바이트를 붙인다 ([AGENTS.md](../../AGENTS.md) 6절). 그래서 00 은 바꾼 DXF 를 ezdxf 로 열어 보고 모델 공간이 비지 않았는지 검사한다. 일부 DWG 는 LibreDWG 가 읽지 못한다. 그러면 00 이 failed 로 남고 01 은 돌지 않는다 (D-1203 의 DWG 6개가 그렇다). 이때는 AutoCAD DXF 를 받거나 PDF 를 쓴다.

## 3. 한 단계씩 실행하고 보기

단계는 번호(6), 이름(view_labels), 범위(6-9)로 고른다. 처음에는 01 부터 (DWG 는 00 부터) 순서대로 돌린다. 각 단계는 앞 단계가 남긴 파일을 읽고, 한 단계를 다시 돌리면 그 뒤 단계 파일은 지워진다.

```zsh
uv run python scripts/reader/run_stages.py $W 1 --dxf $DXF   # 01 도면 읽기 (처음 한 번만 --dxf, 00 을 돌렸으면 생략)
uv run python scripts/reader/show_stages.py $W 1             # 01 결과: 표 출력 + 그림

uv run python scripts/reader/run_stages.py $W 2              # 02
uv run python scripts/reader/show_stages.py $W 2

uv run python scripts/reader/run_stages.py $W 3 --show       # 돌리고 바로 표 + 그림
uv run python scripts/reader/run_stages.py $W 4-6 --show     # 여러 단계를 한 번에
```

**`--dxf` 를 처음 한 번만 주는 이유.** 도면 파일을 직접 여는 단계는 01(read) 하나다. 01 은 DXF 의 엔티티·글자·위치를 모두 읽어 `$W/stages/01_read.json` 에 쓰고, 원본 경로와 sha256 도 적는다. 02–13 은 DXF 를 다시 열지 않고 작업 폴더의 앞 단계 파일만 읽는다. 그래서 새 작업 폴더에서 01 을 처음 돌릴 때만 `--dxf` 가 필요하다. 합성 도면이든 실도면이든 같다. 01 을 다시 돌릴 때 `--dxf` 를 빼면 `01_read.json` 에 적힌 도면을 다시 읽고, 다른 도면으로 바꾸려면 `--dxf` 를 새로 주거나 새 작업 폴더를 쓴다. 00 을 돌린 작업 폴더에서는 01 이 00 이 만든 DXF 를 읽는다.

| # | 단계 | 하는 일 |
|---|---|---|
| 0 | convert | (DWG 만, 선택) DWG → DXF, 열리는지 검사. DXF 는 그대로 |
| 1 | read | DXF 요소 모두 읽기 |
| 2 | title_regex | 표제란 찾기 + 정규식 |
| 3 | title_ocr | **[OCR 모델]** 표제란 받아쓰기 |
| 4 | title_fields | **[추론 모델]** 받아쓴 글자 → 필드 |
| 5 | views | 뷰 후보 나누기, 도면 종류 |
| 6 | view_labels | **[추론 모델]** 뷰 이름, 형상(part_class) |
| 7 | sheet | 1–6 합치기 → `analysis/sheet.png` |
| 8 | document | 3D 복원용 front/top/right 정리 |
| 9 | unfold_params | **[추론 모델]** 전개 파라미터 |
| 10 | develop | 전개 계산 → `flat_pattern.*` |
| 11 | reconstruct | 3D 후보 만들기 |
| 12 | confirm | **[추론 모델]** 3D 후보 고르기 |
| 13 | export | `report.md`, STEP 쓰기 |

단계 파일을 직접 실행해도 같다: `uv run python cutplan_agent/reader/stages/<단계 이름>.py $W` (01 은 `read.py $DXF $W`).

## 4. 결과 보기 옵션

```zsh
uv run python scripts/reader/show_stages.py $W              # 있는 단계 전부
uv run python scripts/reader/show_stages.py $W 6-9          # 범위
uv run python scripts/reader/show_stages.py $W 9 --raw      # 모델 원문 응답까지
uv run python scripts/reader/show_stages.py $W 1 --limit 0  # 긴 목록도 자르지 않고
uv run python scripts/reader/show_stages.py $W --no-figures # 표만 (그림 안 그림)
```

- 표는 화면에 나오고, 그림은 `$W/figures/NN_<단계>.png` 에 생긴다. 단계마다 그림 경로를 출력한다. VSCode 탐색기에서 바로 연다.
- `$W/figures/index.html` 은 모든 단계의 그림과 표를 한 페이지에 묶는다. 브라우저로 보려면:
  ```zsh
  uv run python -m http.server 8765 -d $W    # → http://localhost:8765/figures/index.html (VSCode 가 포트를 넘겨 준다)
  ```

## 5. 한 번에 돌리기

```zsh
uv run python scripts/reader/run_stages.py $W --dxf $DXF            # 01–13 전부
uv run python scripts/reader/run_stages.py $W --drawing "$DWG"      # DWG: 00–13 전부
uv run python scripts/reader/run_stages.py $W --dxf $DXF --no-vlm   # 모델 없이
uv run python scripts/reader/run_stages.py $W 6-13                  # 06 부터 끝까지 다시
```

## 6. 무엇이 어디에 남나

| 위치 | 내용 |
|---|---|
| `$W/stages/NN_<단계>.json` | 단계 결과. 모델 단계(03, 04, 06, 09, 12)는 `trace` 에 모델 원문 응답이 있다 |
| `$W/analysis/` | 단계가 그린 그림: `title_block.png`(03), `sheet_labeled.png`(06), `sheet.png`(07), `candidates.png`(12) |
| `$W/flat_pattern.*` | 전개도 (10) |
| `$W/figures/` | `show_stages.py` 가 그린 그림과 `index.html` |
| `data_v3/synthetic/<도면>/label.json` | 합성 도면의 정답 |
| `runs/reader/deepseek_ocr_qwen_reasoning_skills/<도면>/` | 동료의 2026-10-18 실행 결과 (비교 기준) |
| `runs/vllm/*_vllm.log` | 모델 서버 로그 |

## 7. 자주 나는 문제

| 증상 | 원인과 해결 |
|---|---|
| `ModuleNotFoundError: No module named 'cutplan_agent'` | `export PYTHONPATH=.` 를 안 했다 (1절) |
| 모델 단계가 `skipped (no OCR model configured)` | env 를 source 하지 않았다 (1절) |
| 모델 단계가 `done` 인데 결과가 비어 있다 | 서버가 꺼졌거나 응답하지 않는다. `show_stages.py $W <단계>` 의 모델 호출 줄에 오류가 나온다. 0절의 `curl` 로 확인 |
| `01(read) 을 돌리려면 --dxf <도면.dxf> 를 주거나 ...` | 새 작업 폴더에서는 01 에 `--dxf $DXF` 를 주거나, DWG 는 `0 --drawing "$DWG"` 로 00 을 먼저 돌린다 |
| `00 convert: failed` ... `ezdxf cannot open` 또는 `empty model space` | LibreDWG 가 이 DWG 를 읽지 못했다 (D-1203 의 DWG 6개). AutoCAD 에서 저장한 DXF 를 받거나 같은 이름의 PDF 를 쓴다 |
| 도면 경로에 공백·괄호가 있어 명령이 깨진다 | `DWG="..."` 처럼 따옴표로 담고 `"$DWG"` 로 쓴다 |
| `runs/vllm/ocr.env: no such file` | 서버가 안 떠 있다 (0절) |
| 다음 단계가 `종료 코드 2` 로 멈춘다 | 앞 단계 파일이 없거나 `failed` 다. 앞 단계부터 다시 |
| `08 document: failed`, `11 reconstruct: failed` (실도면) | 고장이 아니라 reader 의 한계다. 한 장에 부품이 여러 개인 도면은 뷰를 front/top/right 하나씩으로 나누지 못한다 |
