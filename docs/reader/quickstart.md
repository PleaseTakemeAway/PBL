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
| 11 | reconstruct | (기본 꺼짐) 3D 후보 만들기 |
| 12 | confirm | (기본 꺼짐) **[추론 모델]** 3D 후보 고르기 |
| 13 | export | (기본 꺼짐) `report.md`, STEP 쓰기 |

11~13 은 3D 단계라 기본으로 돌지 않고 `skipped` 파일만 남는다. 돌리려면 `--with-3d` 를 준다 ([stages.md](stages.md)).

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

### 30장 전체를 돌리고 단계별로 채점하기

서버(0절)가 떠 있어야 한다. 도면을 3묶음으로 나눠 동시에 돌린다. `mlic` 에서 30장에 약 20분 걸린다 (2026-10-27).

```zsh
experiments/batch_parallel.sh data_v3/generated runs/reader/gen1027/local_new 3
uv run python scripts/reader/score_synthetic.py runs/reader/gen1027/local_new   # → score.md, score.json
```

- `batch_parallel.sh <데이터> <출력> [묶음 수] [main.py 옵션 ...]`: 묶음마다 `main.py --batch` 를 따로 띄운다. 출력은 `<출력>/shardK/<도면>/` 이고 로그는 `<출력>/shardK.log` 다. 묶음별 `accuracy.md` 는 그 묶음만의 점수라서 전체 점수는 `score_synthetic.py` 로 본다.
- 묶음 수를 3 보다 늘리면 Qwen3.6-27B 서버의 KV 캐시가 차서 전체가 오히려 느려졌다 (10묶음에서 생성 속도 25 → 4.5 tok/s).
- 동시에 돌리면 요청이 서버에서 기다리므로 기본 제한 시간 120초를 넘긴다. 그래서 스크립트가 `CUTPLAN_OCR_TIMEOUT`, `CUTPLAN_REASON_TIMEOUT` 을 900초로 둔다. 넘기면 그 모델 단계가 `done` 인데 결과가 비고, `trace` 에 `ReadTimeout` 이 남는다.
- 서버 정보는 `runs/vllm/ocr.env`·`reason.env` 에서 읽는다. `CUTPLAN_SERVE_DIR=<폴더>` 를 주면 그 폴더에서 읽는다. GPU 가 넉넉하면 `serve.sh --serve-dir <폴더>` 로 서버 쌍을 여러 개 (포트를 다르게) 띄우고 실험마다 다른 쌍을 붙여 동시에 돌린다 (예: `docs/v3_upgrade.md` 3.4.6).
- 모델 없이: `experiments/batch_parallel.sh data_v3/generated <출력> 3 --no-vlm` (몇 초).
- 판단 모델 답의 자유 서술 칸(`reason`, `notes`, `problems`)은 스키마에서 200자로 묶인다. `CUTPLAN_REASON_PROSE_LIMIT=0` 이면 제한이 없고 (이전 동작), `CUTPLAN_REASON_VIEW_REASON=off` 면 06 이 뷰마다 `reason` 을 받지 않는다. 이 셸에서 export 한 뒤 `batch_parallel.sh` 를 돌리면 적용된다. 이유와 비교 방법은 [../v3_upgrade.md](../v3_upgrade.md) 3.4절.
- `score_synthetic.py` 의 항목은 [../v3_upgrade.md](../v3_upgrade.md) 2절 기준이다. 단계(01~10 모두 `done`), 표제란(도면 번호·축척·재질·두께), 뷰 이름, 형상, 치수(09 의 전개 파라미터. 정답 외경을 안지름 = 외경 − 2t 로 바꿔 0.5 mm 또는 0.5% 안), 전개(1% 이내). 도면별 표에 틀린 이유가 나온다.

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
| 모델 단계가 `done` 인데 결과가 비어 있다 | 서버가 꺼졌거나 응답하지 않는다. `trace` 에 `ReadTimeout` 이면 제한 시간(기본 120초)을 넘긴 것이다: `export CUTPLAN_REASON_TIMEOUT=900` (OCR 은 `CUTPLAN_OCR_TIMEOUT`). `show_stages.py $W <단계>` 의 모델 호출 줄에 오류가 나온다. 0절의 `curl` 로 확인 |
| `01(read) 을 돌리려면 --dxf <도면.dxf> 를 주거나 ...` | 새 작업 폴더에서는 01 에 `--dxf $DXF` 를 주거나, DWG 는 `0 --drawing "$DWG"` 로 00 을 먼저 돌린다 |
| `00 convert: failed` ... `ezdxf cannot open` 또는 `empty model space` | LibreDWG 가 이 DWG 를 읽지 못했다 (D-1203 의 DWG 6개). AutoCAD 에서 저장한 DXF 를 받거나 같은 이름의 PDF 를 쓴다 |
| 도면 경로에 공백·괄호가 있어 명령이 깨진다 | `DWG="..."` 처럼 따옴표로 담고 `"$DWG"` 로 쓴다 |
| `runs/vllm/ocr.env: no such file` | 서버가 안 떠 있다 (0절) |
| 다음 단계가 `종료 코드 2` 로 멈춘다 | 앞 단계 파일이 없거나 `failed` 다. 앞 단계부터 다시 |
| 끝까지 `done` 인데 `flat_pattern.*` 이 없다 (09·10 `skipped`) | 06 에서 형상(`part_class`)이 없거나 `other` 다. 모델 없이(`--no-vlm`) 돌리면 늘 없다. 모델을 붙여도 실도면은 한 장에 부품이 여럿이라 `other` 가 나온다 (S-2120 DWG-003: `other` 0.9998). 13 의 `no_valid_candidate` 도 같은 이유다. `show_stages.py $W 6` 으로 모델 답을 본다 |
| 00 을 다시 돌렸더니 01–13 결과가 사라졌다 | 00 을 저장하면 01–13 파일을 지운다 (다른 단계도 저장하면 뒤 단계를 지운다). 결과를 남기려면 새 작업 폴더에서 돌린다. 지워졌으면 `run_stages.py $W 1-13` 으로 다시 만든다 (모델 답은 실행마다 같다, [stages.md](stages.md) 6절) |
| `08 document: failed`, `11 reconstruct: failed` (실도면) | 고장이 아니라 reader 의 한계다. 한 장에 부품이 여러 개인 도면은 뷰를 front/top/right 하나씩으로 나누지 못한다 |

## 8. 회사 전달용 단계별 시각화 뽑기 (2026-10-28)

`run_stages.py`는 판독을 실행하고, `show_stages.py`는 이미 저장된 결과를 표·PNG·HTML로 시각화한다. **이미 실행한 결과를 보여 주기만 할 때는 모델 서버가 필요 없고 모델을 다시 호출하지 않는다.** 현재 v3 설명 범위는 01~10(전개까지)이며 DWG는 앞에 00 변환이 붙는다. 11~13은 기본 비활성화된 3D 단계다.

### 8.1 기존 결과를 그림으로 만들기

레포 루트에서 다음을 실행한다. 아래 두 폴더는 이 서버에 남은 과거 실행 예시다. 최신 코드·데이터로 다시 판독한 결과가 아니라는 점을 표시한다.

```bash
cd /home/gwanwoo/developer/pbl
export PYTHONPATH=.

# 합성 도면: 2026-10-27 실행 예시
uv run python scripts/reader/show_stages.py \
  runs/reader/gen1027/local_new/shard0/cone_0019 --dpi 180

# 실제 설비 도면: 2026-10-23 실행 예시
uv run python scripts/reader/show_stages.py \
  runs/reader/real_drawings_vlm/merged/VP-S-2120-DWG-001 --dpi 180
```

출력은 각 작업 폴더의 `figures/index.html`, `figures/NN_단계.png`다. HTML에는 단계가 직접 만든 `analysis/*.png`와 `flat_pattern.png`도 들어간다. `failed`·`skipped` 단계는 상태와 표는 나오지만 새 그림이 없을 수 있다. `done`도 정답이라는 뜻은 아니다.

**과거 결과와 현재 정답을 섞지 않는다.** `show_stages.py`는 01에 기록된 입력 경로 옆의 현재 `label.json`을 읽어 정답을 표시한다. 그 경로의 데이터가 실행 후 재생성됐다면 과거 판독 결과에 최신 정답이 붙는다. 현재 데이터 변경을 설명하는 회사 자료는 아래처럼 새 작업 폴더에서 재실행한 결과를 쓰는 편이 명확하다.

### 8.2 최신 합성 도면 1장과 현업자 도면 3건을 새로 실행

0~1절대로 모델 서버를 띄우고 새 셸에서 서버 설정을 적용한 뒤 실행한다. 기존 결과를 덮어쓰지 않게 실행마다 새 출력 폴더를 만든다.

```bash
cd /home/gwanwoo/developer/pbl
export PYTHONPATH=.
. runs/vllm/ocr.env
. runs/vllm/reason.env
export CUTPLAN_OCR_TIMEOUT=900
export CUTPLAN_REASON_TIMEOUT=900
OUT="runs/reader/company_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
printf '결과 폴더: %s\n' "$OUT"

# 최신 개발 세트에서 예시 1장. 옛 기준선은 data_v3/synthetic이고 최신 개발 세트는 generated다.
uv run python scripts/reader/run_stages.py "$OUT/synthetic/cone_0019" 1-10 \
  --dxf data_v3/generated/cone_0019/cone_0019.dxf
uv run python scripts/reader/show_stages.py "$OUT/synthetic/cone_0019" --dpi 180

# 현업자 시험 도면 3건. '전개도 정답.dwg'는 입력하지 않는다.
for part in SHELL CONE HEAD; do
  uv run python scripts/reader/run_stages.py "$OUT/real/$part" 0-10 \
    --drawing "data_v3/20261027example/$part.dwg"
  uv run python scripts/reader/show_stages.py "$OUT/real/$part" --dpi 180
done
```

`OUT`은 위 명령을 실행한 셸에서 유지된다. 다른 셸에서는 출력된 폴더를 다시 지정한다. 시험 도면이 그 서버에 없으면 먼저 [데이터 이관 문서](../data/transfer.md)대로 옮긴다. DWG 변환에는 `dwg2dxf`가 필요하다. 실패해도 실패 상태를 시각화해 전달할 수 있으며, 성공할 때까지 기존 시험 기록을 덮어쓰지 않는다. 실설비 도면을 보려면 `--drawing`을 `test_data/cases/...`의 입력 DWG 경로로 바꾼다.

현재 알려진 현업자 HEAD의 직선부·지름 오독은 [v3_upgrade.md](../v3_upgrade.md) 5.5절 및 [회사 전달용 변경 설명서](../data/synthetic_changes_company.md) 6절에 있다. 이 3건은 최초 시험 결과를 보존하고, 이를 본 뒤 개선한 결과는 별도 실행으로 표시한다. `score_synthetic.py`는 합성 `label.json`용이므로 현업자 도면 3건을 같은 방식으로 자동 채점할 수 있는 상태는 아니다.

### 8.3 합성 30장 전부 실행·채점·시각화

모델 서버가 준비된 셸에서 실행한다. 위의 `OUT`을 그대로 쓰면 같은 전달 묶음에 들어간다.

```bash
experiments/batch_parallel.sh data_v3/generated "$OUT/synthetic_all" 3
uv run python scripts/reader/score_synthetic.py "$OUT/synthetic_all"

for stage_file in "$OUT"/synthetic_all/shard*/*/stages/01_read.json; do
  work="${stage_file%/stages/01_read.json}"
  uv run python scripts/reader/show_stages.py "$work" --dpi 180
done
```

채점표는 `$OUT/synthetic_all/score.md`와 `score.json`, 개별 HTML은 `$OUT/synthetic_all/shardK/<id>/figures/index.html`이다. 모델 응답에 따라 실행 시간은 달라지며, 30장의 그림 생성도 추가 시간이 걸린다.

### 8.4 무엇을 전달하고 PPT에 넣나

- 회사에 보기 좋게 전달할 결과: 도면별 `figures/index.html`과 PNG, `analysis/`의 그림, `flat_pattern.*`, 합성 전체의 `score.md`.
- PPT 갱신에 필요한 근거: 위 그림과 함께 `stages/*.json`, `score.json`, 사용한 입력 세트·코드 커밋·모델 이름. 이 정보로 각 단계의 성공·실패·판독 값과 정답을 대조할 수 있다.
- HTML만 따로 보내면 그림이 깨진다. `figures/`뿐 아니라 작업 폴더 전체를 같은 구조로 전달한다. 상대경로로 연결되므로 받은 쪽에서는 압축을 푼 뒤 `figures/index.html`을 연다. 검토 가능한 표와 그림은 이미 HTML에 들어 있어 받는 쪽에서 Python이나 모델 서버를 띄울 필요가 없다.

예를 들어 8.2~8.3절의 결과 전체를 묶으려면:

```bash
uv run python - "$OUT" <<'PY'
import shutil
import sys
from pathlib import Path

folder = Path(sys.argv[1]).resolve()
archive = shutil.make_archive(str(folder), "zip", folder.parent, folder.name)
print(archive)
PY
```

담당자에게는 처음부터 30장 모두를 PPT로 보여 주기보다 합성 5형상에서 대표 1장씩, 현업자 3건을 골라 **01 원본 요소 → 02~04 표제란 → 05~06 뷰·형상 → 09 치수 → 10 전개**를 보여 주면 이해하기 쉽다. 07은 합쳐진 도면, 08은 구조화 단계라 필요할 때 보충한다. 기존 데이터 변경 설명 PPT는 변경 이유에 집중한 덱이다. 실제 실행 결과 중심 PPT로 갱신할 때는 위 결과 폴더를 기준으로 슬라이드 생성 스크립트를 수정한다.

### 8.5 시각화 범위·형상 분류·커팅플랜의 구분

모든 단계가 별도의 설명 그림을 새로 만드는 것은 아니다. HTML은 저장된 모든 단계의 상태·표를 보여 주고, 아래처럼 단계별 시각화 또는 그 단계가 남긴 그림을 함께 넣는다. `failed`·`skipped`에서는 그림이 없을 수 있다. 그림은 처리 결과를 설명하는 자료이며 내부 계산 과정을 전부 애니메이션으로 보여 주는 기능은 아니다.

| 단계 | 현재 보여 주는 것 |
|---|---|
| 00 convert | 변환·검사 상태와 표. 전용 단계 PNG 없음 |
| 01 read | 읽은 도면 요소 시각화 |
| 02 title_regex | 표제란 위치·추출 결과 |
| 03 title_ocr | 표제란 확대 이미지·OCR 결과 |
| 04 title_fields | 필드 추출 결과 시각화 |
| 05 views | 뷰 후보 영역 |
| 06 view_labels | 뷰 이름·형상 분류 결과·모델 점수의 softmax 막대그래프(값이 있을 때) |
| 07 sheet | 합쳐진 `analysis/sheet.png`. 별도 `07_sheet.png`는 만들지 않음 |
| 08 document | 구조화한 뷰 |
| 09 unfold_params | 전개에 선택한 파라미터 |
| 10 develop | 전개 형상·수치·정답 비교, `flat_pattern.png` |
| 11~13 | 기본 비활성화. 활성화 시 11 후보 그림, 12 후보 이미지, 13 상태·표. 13 전용 단계 PNG 없음 |

형상 분류는 JSON을 직접 열지 않아도 된다.

```bash
# W는 도면 한 장의 작업 폴더로 지정한다
uv run python scripts/reader/show_stages.py "$W" 6 --dpi 180
```

`$W/figures/06_view_labels.png`와 HTML의 06 항목에 도면의 뷰 표시, 선택한 형상(`flat`, `bent_sheet`, `cylinder`, `cone`, `press_formed` 등)이 나온다. 형상별 점수가 있으면 막대그래프도 나온다. 막대의 값은 모델이 준 점수에서 계산한 softmax이며 실제 정답률을 보장하는 값이 아니다. 06이 실패·건너뛰기면 새 단계 그림은 없고 HTML·터미널에서 상태를 확인한다.

**현재 v3 출력의 끝은 개별 부품의 전개도다.** `flat_pattern.png`는 여러 부품을 원자재 판에 배치한 최종 커팅플랜이 아니다. 합성 30장 전체 배치 실행도 도면 30장을 각각 판독한다는 뜻이며, 30장의 부품을 판재에 함께 네스팅하지 않는다. 재질·두께·수량·원자재 크기·분할·배치·간격 등을 반영하는 커팅플랜 기능은 기존 v2의 L3/L4에 있으나, 현재 v3 판독 결과에서 자동으로 이어지는 경로는 없다. 기존 smoke test의 커팅플랜은 직접 입력한 스펙의 결과이므로 v3가 도면에서 자동 생성한 결과로 표시하지 않는다. 관련 흐름은 [execution_flow.md](../execution_flow.md) 2절.

## 9. 전달용 HTML 대시보드 + ZIP 한 번에 만들기

터미널 출력을 보내지 않고 결과를 전달하려면 `export_report.py`를 쓴다. 기존 단계 시각화를 생성한 뒤 그림을 HTML에 내장하고, 도면 전체를 카드로 모은 첫 화면과 도면별 상세 페이지를 ZIP으로 묶는다. 모델은 다시 호출하지 않는다. 단일 작업 폴더, 합성 30장의 배치 폴더, 현업자 도면들이 모인 폴더 모두 입력할 수 있다. 결과물은 git에서 제외되는 `runs/`에 둔다.

```bash
cd /home/gwanwoo/developer/pbl
export PYTHONPATH=.

# OUT은 앞서 판독을 돌린 결과 폴더다. 다른 셸이면 실제 폴더 경로로 다시 지정한다.
REPORT="runs/reports/company_$(date +%Y%m%d_%H%M%S)"
uv run python scripts/reader/export_report.py "$OUT" \
  --out "$REPORT" --title "합성 30장 · v3 단계별 판독 결과"
```

- 출력: `$REPORT/index.html`, `$REPORT/drawings/001.html` 등, `$REPORT.zip`.
- 첫 화면: 도면 검색, 형상 분류(한국어), 뷰·형상 미리보기, 01~10 단계 상태, 전개도 미리보기, 상세 페이지 링크. 단계 색은 실행 상태이며 정답 여부가 아니다.
- 상세 화면: 기존 `show_stages.py`의 모든 단계 그림과 표. 그림을 HTML에 내장하므로 이미지 파일을 따로 보낼 필요가 없다.
- 전달: **ZIP 한 개를 보내고, 압축을 푼 뒤 `index.html`을 브라우저로 열도록 안내한다.** Python·모델 서버·인터넷 연결이 필요 없다. 개별 도면 HTML도 그림이 내장되어 있어 따로 열 수 있다(전체 목록 링크는 묶음 내부에서 동작).
- 기존 출력과 ZIP을 덮어쓰지 않으므로 새 `--out`을 지정한다. 옵션 `--dpi 180`으로 그림 해상도를 높일 수 있으며 크기·생성 시간이 늘어난다.
- 보고서 생성 중 특정 도면에서 오류가 나면 그 도면에 오류 페이지를 만들고 `export_errors.json`에 기록한다. 완료 후 오류가 있으면 종료 코드 1이다. 판독 단계의 `failed`와 보고서 생성 오류는 다르다.
- 기존 결과의 `figures/`를 다시 생성한다. 원본 단계 JSON과 모델 결과는 수정하지 않는다. 정답은 현재 입력 옆 `label.json`을 읽는다는 8.1절의 주의가 그대로 적용된다.
- ZIP에는 보고서 HTML과 생성 오류 목록만 넣는다. 원본 DWG·DXF와 단계 JSON은 넣지 않지만, 그림·표에 도면 내용과 경로가 표시될 수 있으므로 해당 회사에 전달할 자료 범위로 사용한다.

과거 합성 실행 1건으로 기능을 확인한 예시:

```bash
uv run python scripts/reader/export_report.py \
  runs/reader/gen1027/local_new/shard0/cone_0019 \
  --out runs/reports/company_demo_20261028 \
  --title "합성 도면 판독 예시 · 과거 실행"
```

이 예시는 최신 코드·데이터의 AI 재실행 성능을 보여 주는 자료가 아니다. 최신 결과는 새 판독 출력 폴더를 입력으로 사용한다.

### 9.1 19장만 보이는 보고서와 shard의 의미 (2026-10-28 확인)

`batch_parallel.sh ... 3`은 입력 30장을 `shard0`, `shard1`, `shard2`에 10장씩 나누어 동시에 실행한다. shard는 형상이나 판독 단계가 아니라 작업 묶음이다. 전체 보고서와 채점은 shard 하나가 아닌 세 폴더의 공통 부모를 입력한다.

`runs/reader/company_synthetic_20261028_042351`은 최종적으로 30장 모두 `prediction.json`과 10단계 `done`을 남겼다. 그러나 `runs/reports/company_20261028_043701` 보고서는 19건이다. HTML 저장 시각은 한국 시각 04:37:27, 마지막 판독 결과 저장은 04:46:39로, 보고서를 먼저 내보낸 동안 판독이 계속되고 있었다. 보고서는 생성 시점의 목록을 고정하므로 나중에 완료된 도면이 자동 추가되지 않는다. 배치 명령의 `done:` 출력과 세 shard 로그의 완료를 확인하고 새 `--out`에 보고서를 다시 만든다. 판독을 다시 할 필요는 없다.

이 실행을 재채점한 결과: 단계 30/30, 표제란 30/30, 뷰 16/30, 형상 30/30, 치수 20/30, 전개 18/30, 전 항목 일치 7/30. 상세는 실행 폴더의 `score.md`와 `score.json`. 처리 완료와 판독 정답을 구분한다.

### 9.2 실제 도면 3건을 판독하고 같은 ZIP 보고서 만들기

실제 데이터는 생성기가 만드는 합성 데이터가 아니라 회사에서 받은 원본이다. 우선 비교하기 쉬운 현업자 시험 도면 `data_v3/20261027example/{SHELL,CONE,HEAD}.dwg` 3건을 사용한다. 더 복잡한 실제 설비 입력은 `test_data/cases/S-2120/input_drawings/`와 `test_data/cases/D-1203/input_drawings/`에 있다. `output_cutting_plan/`과 `전개도 정답.dwg`는 정답이며 판독 입력이 아니다.

모델 서버(0절)가 실행 중인 상태에서 다음을 실행한다. 새 출력 폴더를 써 최초 시험 결과를 보존한다.

```bash
cd /home/gwanwoo/developer/pbl
export PYTHONPATH=.
. runs/vllm/ocr.env
. runs/vllm/reason.env
export CUTPLAN_OCR_TIMEOUT=900
export CUTPLAN_REASON_TIMEOUT=900
REAL_OUT="runs/reader/company_real_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$REAL_OUT"

for part in SHELL CONE HEAD; do
  uv run python scripts/reader/run_stages.py "$REAL_OUT/$part" 0-10 \
    --drawing "data_v3/20261027example/$part.dwg"
done

# 세 도면의 실행이 끝난 다음 보고서를 만든다.
REAL_REPORT="runs/reports/company_real_$(date +%Y%m%d_%H%M%S)"
uv run python scripts/reader/export_report.py "$REAL_OUT" \
  --out "$REAL_REPORT" --title "현업자 도면 3건 · v3 판독 결과"
```

`$REAL_REPORT.zip`을 전달한다. 이 스크립트는 시각화까지 수행하므로 별도로 `show_stages.py`를 돌릴 필요가 없다. DWG 변환에서 실패한 도면도 00 기록이 있으면 보고서에 포함된다. 실제 도면 3건은 합성 `label.json`이 아직 없으므로 합성처럼 정답 비교가 자동으로 붙는 것은 아니다.
