# PBL 미팅 발표 자료 계획 (2026-10-30 발표)

중간보고 뒤 PBL 미팅에서 발표할 자료의 계획이다. 2026-10-29 에 썼다. 청중은 교수님과 PBL 회사 사람들이다. 자료 안에서는 과목·회사 이름 대신 "PBL" 이라고 쓴다.

슬라이드는 다른 덱처럼 `presentation/` 의 스크립트로 만든다 ([presentation.md](presentation.md)). 이 문서는 무엇을 왜 넣는지, 필요한 실행과 그 명령, 남은 결정을 적는다. 만든 뒤에는 숫자의 출처를 [presentation.md](presentation.md) 에 다른 덱처럼 표로 옮긴다.

## 1. 전할 것

1. **3D 를 뺀 범위(도면 → 전개도)에서 reader 가 어떻게 좋아졌나.** 세 단계 변천사(2절)를 단계별 그림으로 before → after 로 보인다.
2. **하네스가 어떻게 동작하나.** reader 의 10단계를 코드 대신 모식도로 보인다. 어느 단계를 AI 가 하고 어느 단계를 코드가 하는지, AI 의 답을 어떻게 검사하고 다시 묻는지를 그린다.
3. **추가 실험 두 가지.** JSON 답이 길이 제한에서 잘리던 문제의 처리(다른 세션에서 병렬로 작업)와, 하네스는 그대로 두고 모델만 바꿔 낀 결과(4절).
4. **다음 단계 v4.** v3 고도화로 목표를 바꾸면서 뺀 실제 도면 작업(`git show c71cca0:docs/v4.md`)을 v4 로 다시 잡는다.

분량은 정하지 않고 다 만든다. 지난 발표와 겹치는 슬라이드는 발표 때 건너뛴다.

## 2. 세 단계 변천사

| 단계 | 데이터 | 코드 | 무엇이 바뀌었나 | 남아 있는 기록 |
|---|---|---|---|---|
| ① `synthetic` / `cutplan_v3` | `data_v3/synthetic` (옛 정답) | 동료 v3 253020c | 동료의 원래 상태. 한 번에 도는 판독기, 단계별 기록이 없다 | `runs/reader/deepseek_ocr_qwen_reasoning_skills` (동료, 2026-10-18): 형상 27/30, 전개 11/30 (`accuracy.md`, `flat_patterns.md`). 단계 파일이 없어 `score_synthetic.py` 로 채점하지 못한다 |
| ② `synthetic` / `reader` | 같음 | c71cca0 (2026-10-23 main) | 판독을 13단계로 나눴다 (단계마다 파일), DWG 변환 00, orchestrator. 회사 계산 문서 식을 v2 L3 에 넣었다 | 이 서버에는 없다 (동료 서버의 `runs/reader/server1027/v3_old` 가 비슷한 시점이다). 다시 돌린다 (3절 R2) |
| ③ `generated` / `reader+` | `data_v3/generated` (새 생성기, 현업자 기준 정답) | main | 3D 단계를 기본으로 끔, 생성기를 새로 쓰고 데이터 정답을 고침 (콘·경판·굽힘판 등 #1~#10), 경판·콘 식을 현업자 정답으로, 답 잘림 다시 묻기 (#13), 경판 직선부 측정 (#16) | `runs/reader/company_synthetic_20261028_042351` (10-28 04:23). 2807e44·f111ea8 (02:21·02:39) 뒤의 코드다 (3.3절에서 바로잡음). 2026-10-30 에 같은 코드로 다시 돌린 R4 가 `runs/reader/meeting1030/R4_generated_main` |

①→② 는 코드만 바뀌었고 ②→③ 은 코드와 데이터가 같이 바뀌었다. ②→③ 의 점수 차이를 코드 덕분이라고만 말하면 틀린다. 그래서 2×2 로 돌려 둘을 나눈다 (3절).

①→② 는 지난 발표(`build_v2_v3.py`)와 겹친다. 그대로 넣고 발표 때 건너뛴다.

### 2.1 ① 과 ② 는 무엇이 다른가 (2026-10-30 확인)

`git log 1ea7cc6..c71cca0` 에서 reader, `skills/`, `experiments/` 를 고친 커밋 26개를 읽었다. 판독 로직은 같고, 판독 로직을 둘러싼 것만 바뀌었다.

**같은 것.**

- 판독 계산: `dxf_adapter.py`, `vlm.py`, `unfold.py` 는 함수로 쪼개고(6f44e7f) 단계 스크립트로 감쌌다(4230d09). 두 커밋 모두 모의 OCR·판단 서버로 `main.py` 10가지 실행 방식을 돌려 출력 파일, stdout, stderr 가 시각만 빼고 바이트 단위로 같음을 확인했다 (커밋 메시지). 포맷(32b3c58)과 안 쓰는 코드 삭제(bfd50e1)도 출력이 같다.
- 경판 원판: v3 `unfold.py` 는 동료의 경험계수 `HEAD_BLANK_K = (1.25, 1.30)` 를 그대로 쓴다 (63e5829 은 주석만 고쳤다).
- 데이터와 정답: 옛 `data_v3/synthetic` 그대로다. 콘·경판·굽힘판 정답이 틀린 채다.
- 모델 호출: 같은 모델, `max_tokens` 1500, temperature 0, 잘린 답 다시 묻기 없음. 3D 단계(11~13)도 기본으로 돈다.
- 채점: `accuracy.md`(형상)와 `flat_patterns.md`(전개)뿐이다. 단계별 채점 `score_synthetic.py` 와 생성기 `build_synthetic.py` 는 c71cca0 에 없다 (10-27 에 생겼다).

**바뀐 것.**

| 무엇 | 커밋 | 판독 결과에 |
|---|---|---|
| 13단계 스크립트, 단계마다 `stages/NN_<단계>.json`. 09 의 모델 호출 기록이 처음으로 남는다 | 6f44e7f, 4230d09 | 같음 (확인함) |
| 00 `convert` (DWG → DXF), `tools.py`·`orchestrator.py` (모델이 단계를 고름), `show_stages.py`·`run_stages.py` | c8e4803, 96f14fc, ad6995f, 9097dc0 | 배치는 이 경로를 타지 않는다 |
| 실행 환경: A5000 4장 기본값 (OCR GPU 0, 판단 GPU 1~3 pipeline parallel), 메모리 비율, FlashInfer sampler 끔 | a660d59 | 같은 모델이지만 다른 기계 |
| **06·09 의 모델이 읽는 규칙 문서.** 06 은 `unfold_rules.md`, 09 는 `unfold_rules.md`·`drawing_conventions_kr.md` 를 시스템 지시 앞에 붙인다 (`knowledge.py` `STAGE_TOPICS`). `unfold_rules.md` 에 "회사 계산 문서와 다르면 그 문서를 따른다", 경판 원판 1.2·Dm + 2·SF 등 형식별 식, 편심 콘 행이 들어갔고, `drawing_conventions_kr.md` 에 부품표 행과 커팅플랜 라벨의 대응(실도면용)이 들어갔다 | 63e5829, e726d39 | 모델 입력이 바뀐다. 30장 전체로 잰 적은 없다 |
| 회사 계산 문서 식은 v2 (`cutplan_agent/skills/l3_rules.py`) 에 넣었다. v3 reader 에는 넣지 않았다 | 63e5829, a74d344 | v3 결과와 무관 |

**그래서 ② 의 문제.**

1. 모델에게 주는 규칙(회사 식)과 코드가 계산하는 식(경험계수 1.25~1.30)과 채점하는 정답(옛 생성기 값)이 서로 다르다.
2. 고친 것이 실도면(v4)을 향했다. DWG 변환, 부품표, 편심 콘, v2 L3 이다. 그런데 잰 데이터는 정답이 틀린 합성 30장이고, 그나마 30장 전체로는 돌리지 않았다 (a660d59: bent_sheet_0007 한 장 뒤 멈춤).
3. 단계 파일은 생겼지만 단계별 정답이 없어서, 무엇이 좋아졌는지 숫자로 말할 수 없다.

②를 30장으로 잰 결과는 3.1절 (R2) 이다. 그 전에 남아 있던 숫자: 2026-10-23 `mlic` 에서 ① 이 형상을 못 낸 cylinder_0013·0018, flat_0005 의 06 만 세 번씩 돌려 셋 다 맞혔다 ([reader/stages.md](reader/stages.md) 6절). 원인이 기계인지, vLLM 판인지, 고친 `unfold_rules.md` 인지는 가리지 않았다.

## 3. 돌릴 것

| | 옛 데이터 `data_v3/synthetic` | 새 데이터 `data_v3/generated` |
|---|---|---|
| 옛 코드 c71cca0 | **R2** (②) | **R3**: 데이터만 바꾼 효과 |
| 지금 코드 main | **R1**: 코드만 바꾼 효과 | **R4** (③) |

- 모두 로컬 모델 기본 구성(DeepSeek-OCR-2 + Qwen3.6-27B, `experiments/serve.sh`)으로 돌리고 `scripts/reader/score_synthetic.py` 로 채점한다. 채점 기준은 [v3_upgrade.md](v3_upgrade.md) 2절이다.
- 옛 데이터의 정답은 콘·경판·굽힘판이 틀려 있다 (v3_upgrade.md 4절). 그래서 R1·R2 의 전개 점수는 "옛 정답과 맞는가" 이고, 형상·표제란·뷰를 주로 본다. 전개는 R3·R4 로 말한다.
- c71cca0 은 3D 단계를 기본으로 돌린다. 채점은 01~10 만 보므로 결과에 영향이 없다. 시간만 더 든다.
- c71cca0 에는 `experiments/batch_parallel.sh` 가 없고 모델 요청 제한 시간이 120초로 고정이다. 3묶음 동시로 돌리면 시간 초과가 날 수 있어, 옛 코드는 1묶음으로 돌린다.

서버 (한 번 띄워 두고 네 번 돌린다):

```zsh
./experiments/serve.sh --vllm-bin ~/venvs/vllm-0.31/bin/vllm
```

다른 셸에서, 이 worktree 루트에서:

```zsh
# R4, R1: 지금 코드
experiments/batch_parallel.sh data_v3/generated runs/reader/meeting1030/R4_generated_main 3
experiments/batch_parallel.sh data_v3/synthetic runs/reader/meeting1030/R1_synthetic_main 3
uv run python scripts/reader/score_synthetic.py runs/reader/meeting1030/R4_generated_main
uv run python scripts/reader/score_synthetic.py runs/reader/meeting1030/R1_synthetic_main

# R2, R3: 옛 코드. 따로 받은 worktree 에서 지금의 batch_parallel.sh 를 1묶음으로 쓴다
git worktree add ../pbl-c71cca0 c71cca0
cp experiments/batch_parallel.sh ../pbl-c71cca0/experiments/
ln -s "$PWD/runs/vllm" ../pbl-c71cca0/runs/vllm   # 서버 주소 (ocr.env, reason.env)
(cd ../pbl-c71cca0 && experiments/batch_parallel.sh "$OLDPWD/data_v3/synthetic" "$OLDPWD/runs/reader/meeting1030/R2_synthetic_c71cca0" 1)
(cd ../pbl-c71cca0 && experiments/batch_parallel.sh "$OLDPWD/data_v3/generated" "$OLDPWD/runs/reader/meeting1030/R3_generated_c71cca0" 1)
uv run python scripts/reader/score_synthetic.py runs/reader/meeting1030/R2_synthetic_c71cca0
uv run python scripts/reader/score_synthetic.py runs/reader/meeting1030/R3_generated_c71cca0
```

이 worktree 는 git 밖 데이터(`data_v3/`, `runs/`)가 없으므로 원래 clone 의 폴더를 링크해 쓴다. 옛 코드가 지금의 `batch_parallel.sh` 와 맞는지(여러 DXF 를 한 번에 받는지)는 돌리기 전에 도면 1장으로 확인한다. 위 명령은 아직 돌려 보지 않았다. 돌린 뒤 실제 명령과 걸린 시간으로 고친다.

### 3.1 R2 를 돌렸다 (2026-10-30)

**조건.**

| | |
|---|---|
| 코드 | c71cca0 (2026-10-23 main). `git worktree add --detach ../pbl-c71cca0 c71cca0`, 그 안에서 `uv sync` |
| 서버 | c71cca0 의 `experiments/serve.sh` 로 띄웠다 (DeepSeek-OCR-2 GPU 0, Qwen3.6-27B GPU 1~3 pipeline). 지금 main 의 서버와 다른 점은 `--structured-outputs-config.disable_any_whitespace=true` 가 없는 것 하나다 (`--dry-run` 으로 비교). 이 옵션은 3cf2274 (#13) 에서 들어왔다 |
| 데이터 | 옛 `data_v3/synthetic` 30장, 옛 정답 |
| 실행 | `main.py --batch` 1묶음 순차. c71cca0 은 모델 요청 제한 시간이 120초로 고정이라 여러 묶음을 동시에 돌리지 않았다. 3D 단계(11~13)도 돈다 |
| 걸린 시간 | 1시간 0분 13초 (01:16 ~ 02:16) |
| 출력 | `runs/reader/meeting1030/R2_synthetic_c71cca0` (`score.md`, `score.json`, `accuracy.md`, `flat_patterns.md`) |

```zsh
cd ../pbl-c71cca0
./experiments/serve.sh --vllm-bin ~/venvs/vllm-0.31/bin/vllm      # 이 셸은 띄워 둔다
# 다른 셸, 같은 폴더에서
. runs/vllm/ocr.env; . runs/vllm/reason.env
PYTHONPATH=. uv run python cutplan_agent/reader/main.py --batch --input-mode dxf \
  --output-dir /home/gwanwoo/developer/pbl/runs/reader/meeting1030/R2_synthetic_c71cca0 \
  /home/gwanwoo/developer/pbl/data_v3/synthetic
```

채점: 지금의 `scripts/reader/score_synthetic.py` 는 새 정답의 파라미터 이름(`large_outer_diameter`, `outer_diameter`)을 읽는다. 옛 정답은 콘이 `large_diameter`·`small_diameter`, 경판이 `diameter` 라서 `KeyError` 로 멈춘다. 레포 코드는 고치지 않고 이름만 바꿔 넣는 래퍼로 채점했다. 규칙(허용 오차, 안지름 환산)은 그대로다. 레포 루트에서:

```zsh
cat > /tmp/score_old_labels.py <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "reader"))
import score_synthetic as sc

orig = sc.expected_params


def expected_params(label):
    p = dict(label.get("params", {}))
    if label.get("class") == "cone" and "large_diameter" in p:
        p["large_outer_diameter"] = p.pop("large_diameter")
        p["small_outer_diameter"] = p.pop("small_diameter")
    if label.get("class") == "press_formed" and "diameter" in p:
        p["outer_diameter"] = p.pop("diameter")
    return orig({**label, "params": p})


sc.expected_params = expected_params
sys.argv = ["score_synthetic.py", sys.argv[2]]
sc.main()
PY
uv run python -I /tmp/score_old_labels.py "$PWD" runs/reader/meeting1030/R2_synthetic_c71cca0
```

**결과 (옛 정답 기준).**

| 항목 | 전체 | 평판 | 굽힘판 | 원통 | 콘 | 경판 |
|---|---:|---:|---:|---:|---:|---:|
| 단계 | 27/30 | 5/6 | 6/6 | 4/6 | 6/6 | 6/6 |
| 표제란 | 30/30 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| 뷰 | 14/30 | 3/6 | 5/6 | 0/6 | 6/6 | 0/6 |
| 형상 | 27/30 | 5/6 | 6/6 | 4/6 | 6/6 | 6/6 |
| 치수 | 18/30 | 4/6 | 3/6 | 4/6 | 1/6 | 6/6 |
| 전개 | 11/30 | 4/6 | 3/6 | 4/6 | 0/6 | 0/6 |
| 전부 | 4/30 | 2/6 | 2/6 | 0/6 | 0/6 | 0/6 |

**왜 이렇게 나왔나.**

1. **형상 27/30, 전개 11/30 은 동료 실행(①)과 수가 같다.** 판독 계산이 같다는 2.1절과 맞는다. 다만 틀린 도면은 다르다. ① 은 cylinder_0013·0018, flat_0005, R2 는 cylinder_0016·0017, flat_0001 이다. 전개는 형상이 빠진 원통 · 평판 말고도 굽힘판 3장(0008·0010·0011)이 엇갈린다. 같은 코드라도 기계 · 서버가 바뀌면 모델 답이 달라진다 ([reader/stages.md](reader/stages.md) 6절).
2. **형상을 못 낸 3장은 06 판단 요청이 120초 제한에 걸린 것이다** (`06_view_labels.json` trace: `ReadTimeout … read timeout=120.0`, 원문 없음). 끝난 06 요청은 최장 66.5초 (cylinder_0013, 원문 3,009자), 가운데값 39.3초다. 이 서버의 Qwen 은 요청 하나에 초당 약 12.9 토큰을 쓴다 (`reason_vllm.log` 의 `Avg generation throughput`). 그래서 `max_tokens` 1,500 까지 가는 답은 생성에만 약 116초가 들고, 그림 입력 처리까지 더하면 120초를 넘는다. 원문이 남지 않아 직접 보지는 못했지만, 동료 서버에서 "길이 제한에서 잘림" 으로 나타나던 #13 과 같은 원인으로 본다. 빠른 GPU 에서는 잘려서 깨지고, 이 서버에서는 잘리기 전에 시간이 다 된다.
3. **콘 전개 0/6 은 정답이 틀려서다.** cone_0023 은 치수가 맞았는데 (안지름 142 · 72, 높이 150) 전개 오차가 114% 다. 판독기는 R1 321.3, θ 81.8° (θ = 360° · sin α) 를 냈고 옛 정답은 R1 330.06, θ 38.17° 다. 새 정답은 321.02, 81.8° 다 (슬라이드 '채점').
4. **경판 전개 0/6 은 기준이 갈려서다.** 치수는 6/6 맞았다. 전개 오차는 8~11% 다. press_formed_0028 (외경 300, t 6, SF 15) 에서 판독기는 경험계수로 1.275 × 288 + 2 × 15 = 397.2, 옛 정답은 432.5 다. 06 · 09 가 읽는 `unfold_rules.md` 는 회사 계산 문서의 1.2·Dm + 2·SF (Dm = 288 + 6 이므로 382.8, 여기에 트림 여유 30 mm 를 더하고 10 mm 로 올림) 를 적고 있다. 세 기준이 모두 다르다.
5. **뷰 14/30.** 원통 0/6, 경판 0/6 은 원만 있는 뷰를 뷰로 잡지 못한 것이다 (v3_upgrade.md #11, 후에도 남아 있다). 평판 3장은 top 대신 other · bottom 으로 이름을 붙였다.
6. **치수 18/30.** 콘 5장은 AI 가 큰 쪽 바깥지름(150, 300)을 안지름 칸에 그대로 넣었다. 작은 쪽은 AI 가 비워 코드가 외형 치수에서 맞게 채웠다 (`09_unfold_params.json` 의 `sources`). 후의 #14 와 같은 실패다. 굽힘판 3장은 폭과 다리를 바꿔 읽거나 굽힘 반경을 잘못 읽었다 (#17).

'전 (다시 잼)' 열의 숫자는 옛 정답 기준이라 후와 바로 견줄 수 없다. 특히 콘 · 경판 전개와 콘 치수는 정답 쪽 오류가 섞여 있다. 덱의 단계별 점수 노트에 같은 내용을 적었다.

### 3.2 R4 를 다른 서버에서 돌린다 (인계, 2026-10-30)

사용자가 R4 (지금 main · 새 합성 `data_v3/generated`) 를 다른 서버에서 돌린다. 이 문서는 `pbl-meeting` 브랜치에만 있다. main 을 받은 서버에서는 `git fetch origin && git show origin/pbl-meeting:docs/pbl_meeting.md` 로 읽는다. 덱의 '후' 숫자는 지금 RUN3 (`runs/reader/company_synthetic_20261028_042351`, 10-28 04:23) 이다. ~~그 뒤에 들어간 현업자 기준 식(2807e44 · 7005fa6)과 경판 직선부(f111ea8)가 빠져 있어서, R4 가 나오면 '후' 를 R4 로 바꾼다.~~ 이 전제는 틀렸다 (3.3절): 두 커밋은 RUN3 보다 먼저 들어갔다. 그래도 R4 를 지금 main 의 기록으로 '후' 에 쓴다. R1 · R3 은 하지 않기로 했다 (2×2 는 부록에 R2 와 R4 만).

**그 서버에서 할 일.**

1. 레포를 main 으로 받는다. 2026-10-30 의 main 은 60e0d26 이다. 15b5ef4 뒤의 커밋(577cc34 `--analyze-only` 를 07 에서 멈춤 등)은 기본 실행의 출력을 바꾸지 않는다 (커밋 메시지). 돌린 커밋 해시를 적어 둔다.
2. `data_v3/generated` 가 이 서버와 같은지 확인한다: `PYTHONPATH=. uv run python scripts/check_data.py` ([data/transfer.md](data/transfer.md)). 없으면 `PYTHONPATH=. uv run python scripts/build_synthetic.py` 로 만들고 같은 검사를 한다. 정답이 바뀌면 점수를 비교할 수 없다.
3. 서버를 띄우고 돌리고 채점하고 그림을 그린다. 레포 루트에서:

```zsh
./experiments/serve.sh --vllm-bin <vllm>          # GPU 배치가 다르면 --ocr-gpu, --reason-gpu (동료 서버: --ocr-gpu 4 --reason-gpu 5)
# 다른 셸에서
experiments/batch_parallel.sh data_v3/generated runs/reader/meeting1030/R4_generated_main 3
uv run python scripts/reader/score_synthetic.py runs/reader/meeting1030/R4_generated_main
for w in runs/reader/meeting1030/R4_generated_main/shard*/*/; do uv run python scripts/reader/show_stages.py "$w" >/dev/null; done
```

4. 서버, GPU, 커밋, 시작 · 끝 시각, `score.md` 의 표를 이 절 아래에 적는다. 3.1절(R2)과 같은 형식으로, 2026-10-28 RUN3 (단계 30, 표제란 30, 뷰 16, 형상 30, 치수 20, 전개 18, 전부 7) 과 무엇이 달라졌는지와 그 이유를 쓴다. 특히 경판 · 콘 전개(현업자 기준 식)와 경판 치수(직선부)를 본다.

**이 서버(`mlic`)로 가져올 것.** 실행 폴더 전체 `runs/reader/meeting1030/R4_generated_main/` (shard 폴더, `score.json`, `score.md`). 덱이 읽는 것은 `score.json`, 도면마다 `stages/*.json`, `analysis/sheet.png` · `title_block.png`, `figures/05_views.png` · `10_develop.png` 다. git 에 넣지 않는다 (runs/ 는 git 제외).

**덱 바꾸기.** `presentation/build_meeting.py` 의 `RUN3` 을 `RUNS / "meeting1030" / "R4_generated_main"` 으로 바꾸고 다시 만든다. 손으로 적은 값이 있어 확인할 곳:

- 하네스 덱 '채점' (`score_def_slide`): 정답 칸의 `SYN-00023 · 1/2 · SPHC · 4`, 안지름 141.8 · 71.8, `R 321.02 · 167.0, 81.8°` 는 손으로 적었다. 새 실행에서 cone_0023 이 모두 맞는지 (`score.md`) 본다. 아니면 예시 도면(`EXAMPLE`)을 바꾼다.
- `SHOWCASE` (형상마다 전 → 후 도면): 후에서 모두 맞은 도면을 골랐다. 새 실행의 `score.md` 도면별 표로 다시 고른다.
- 남은 실패 (`remaining_slides`): #11 · #14 · #15 · #17 의 예시 도면과 문장이 새 실행에서도 맞는지 본다. 경판 #15 는 현업자 기준 식으로 바뀌었을 수 있다.
- 다시 묻기 슬라이드 (`guard_retry_slide`) 노트의 잘림 건수 (10-28 은 4건 잘림, 모두 다시 물어 성공) 는 RUN3 의 단계 파일 trace 에서 셌다. 새 실행에서 다시 센다 (4.1절 표와 같은 방법).
- `RUN3` 이름과 머리말 docstring, [presentation.md](presentation.md) 8절의 '후' 행, 이 문서 8절.

### 3.3 R4 결과 (2026-10-30)

다른 세션이 돌리고 채점했다. 이 세션에서 `score.json` 의 항목별 수와 바뀐 도면, 커밋 시각, cone_0023 의 단계 값을 다시 확인했다.

| | |
|---|---|
| 코드 | main 60e0d26. worktree `../pbl-r4`, 브랜치 `r4-generated` (커밋 없음). `data_v3/`, `runs/` 는 원래 clone 을 링크 |
| 데이터 | `data_v3/generated`. `scripts/check_data.py` 로 91개 파일이 기준과 같음을 확인 |
| 서버 | `mlic` A5000 4장, 기본 구성 (DeepSeek-OCR-2 + Qwen3.6-27B), `experiments/batch_parallel.sh` 3묶음 |
| 시간 | 03:02:17 ~ 03:25:24 (23분) |
| 출력 | `runs/reader/meeting1030/R4_generated_main` (`score.md`, `score.json`). `figures/` 는 이 세션에서 `show_stages.py` 로 그렸다 (30장, 56초) |

| 항목 | RUN3 (10-28) | R4 (10-30) | 바뀐 도면 |
|---|---:|---:|---|
| 단계 | 30 | 29 | cylinder_0016 이 09 · 10 을 건너뜀 |
| 표제란 | 30 | 30 | |
| 뷰 | 16 | 16 | flat_0004 와 0005 가 서로 엇갈림 |
| 형상 | 30 | 29 | cylinder_0016 |
| 치수 | 20 | 21 | cone_0019 맞음 (cylinder_0016 은 RUN3 에서도 치수가 틀렸다) |
| 전개 | 18 | 18 | cone_0019 맞음, press_formed_0029 틀림 |
| 전부 | 7 | 8 | cone_0019 (+1), flat_0004 · 0005 엇갈림 |

**3.2절의 전제는 틀렸다.** 2807e44 (현업자 기준 식) 는 10-28 02:21, 7005fa6 · f111ea8 (콘 채점, 경판 직선부) 은 02:39 에 들어갔고, RUN3 은 04:23 에 시작했다. RUN3 의 2:1 경판 원판과 cone_0023 이 이미 새 정답과 맞는다. RUN3 과 R4 사이의 reader 커밋은 577cc34 (`--analyze-only`) 하나이고 기본 배치 실행을 바꾸지 않는다. 그래서 R4 는 같은 코드를 한 번 더 돌린 것이고, 두 실행의 차이(도면 4장)는 모델 답이 실행마다 흔들린 것이다. 같은 일이 '전' 에서도 있었다 (3.1절: ① 과 R2 는 수가 같고 틀린 도면이 다르다).

바뀐 도면의 원인:

- cone_0019 (맞음): RUN3 에서는 모델이 큰 쪽 지름 칸에 바깥지름 150 을 넣었고 R4 에서는 뺐다. 남은 콘 4장 (0020 · 0021 · 0022 · 0024) 은 아직 바깥지름을 안지름 칸에 넣는다 (#14).
- cylinder_0016 (단계 실패): 06 답이 잘렸고 다시 물어도 또 잘렸다 (`finish_reason: length`). 모델이 `reason` 칸에 "사각형은 100×300 인데 원은 300, 모순이다 …" 하는 혼잣말을 길게 쓰다 한도에 걸렸다.
- press_formed_0029 (전개 틀림): 경판 종류를 2:1 타원 대신 TORISPHERICAL 로 골라 원판이 174.25 (정답 186.08). R4 의 경판 전개 실패 넷이 모두 종류를 잘못 고른 것이다 (0026 FLAT FLANGED, 0027 · 0030 hemispherical, 0029 TORISPHERICAL). 치수는 6장 모두 맞고, 2:1 로 고른 0025 · 0028 은 정답과 0.01 mm 안에서 맞는다 (#15).
- 잘림: RUN3 은 4번 잘려 4번 모두 다시 물어 성공, R4 는 2번 잘려 1번 성공 (cylinder_0017), 1번 실패 (cylinder_0016).

**덱에 반영한 것.** `RUN3` 을 R4 로 바꾸고 10-28 실행은 `RUN3_1028` 로 남겼다.

- 단계별 점수 표: '후, 다시 묻기 전' 열을 빼고 '후 (10-28)' 과 '후 (10-30)' 을 나란히 둔다. 같은 코드라도 실행마다 1~2장씩 흔들린다는 근거다. 다시 묻기 전후 비교는 하네스 덱의 '다시 묻기' 장(10-27 대 10-28)에 그대로 있다.
- 남은 실패 #14 의 예시를 cone_0019 에서 cone_0020 (바깥지름 300) 으로 바꿨다. #15 는 경판 넷이 모두 종류 선택 실패라고 적었다.
- 실험 1 (답 잘림): R4 에서 다시 물어도 잘린 도면이 나왔다는 것을 문구와 노트에 넣었다.
- 손으로 적은 "형상 30/30" 두 곳을 고쳤다 ('남은 것은 모델보다 하네스와 코드', 하네스 덱 '형상').
- cone_0023 (하네스 덱의 예시 도면) 은 R4 에서도 모든 항목이 맞고, 단계 값 (안지름 141.79 · 71.79, R 321.02 · 167.0, 81.8°, 04 의 SYN-000) 이 RUN3 과 같다. 형상마다 전 → 후 도면 (`SHOWCASE`) 도 R4 에서 RUN3 과 같은 결과다.

## 4. 추가 실험

### 4.1 JSON 답 잘림

동료가 말한 실패(모델 답이 `max_tokens` 에서 잘려 JSON 이 깨짐, #13)의 로직 수정은 다른 worktree 에서 사용자가 한다. 이 worktree 는 코드를 고치지 않고, 그쪽 결과(커밋, 실행 폴더, 숫자)를 받아 전후 슬라이드로 넣는다.

**reader+ 에서도 잘림이 나는가 (2026-10-29, 이 서버의 단계 파일로 셌다).** 난다. 다시 묻기가 살릴 뿐이다.

| 실행 | 코드 | 판단 모델 호출 | 잘려서 실패 | 잘린 뒤 다시 물어 성공 |
|---|---|---:|---|---|
| `runs/reader/gen1027/local_new` (2026-10-27) | 다시 묻기 전 | 60 (06·09 각 30) | 7: 06 cylinder_0013·0016·0017, flat_0002 / 09 bent_sheet_0007, press_formed_0029, cone_0024 | |
| `runs/reader/company_synthetic_20261028_042351` (2026-10-28 04:23) | 3cf2274 뒤 | 60 | 0 | 4: 06 cylinder_0017, flat_0002 / 09 press_formed_0025·0027 |

- 실패 7건은 모두 `JSONDecodeError` 다 (닫히지 않은 문자열, 빠진 쉼표). 앞의 기준선 표(v3_upgrade.md 3.1절)의 "단계 26/30" 은 06 의 4건이 09·10 을 건너뛴 것이다. 09 에서 잘린 3건도 있었는데, 지금까지 문서에는 06 만 적혀 있었다.
- 잘린 답의 끝: 09 는 `reason` 문자열 안에 계산을 길게 풀어 쓰다 잘린다 (예: press_formed_0027 `"… If ID=200, OD=212. Depth of 2:1 ellip = 50. Total = 56. Still not 59. Let's"`). 06 의 flat_0002 는 줄바꿈과 공백을 반복하다 잘렸다. 이 실행의 판단 서버가 `disable_any_whitespace` 를 넣은 뒤에 뜬 서버인지는 기록이 없어 확인하지 못했다.
- 저장된 원문은 4000자에서 자른 것이라(`raw[:4000]`) 실제 답 길이는 모른다. 토큰 수(`usage`)는 기록에 남지 않는다.

**다른 worktree 에서 할 일 (제안).**

1. 재기: 단계별 잘림 횟수와 답의 토큰 수를 남긴다 (trace 에 `usage.completion_tokens`). 지금은 길이를 모른다.
2. 근본 처리 후보:
   - **답 양식 바꾸기**: 결정 칸(형상, 치수)을 앞에, `reason` 을 맨 뒤에 둔다. 잘려도 결정은 남는다. `reason` 에 `maxLength` 를 거는 방법도 있다 (xgrammar 가 문자열 길이 제한을 지키는지는 확인이 필요하다). 09 의 `reason` 이 계산 풀이 공간이 되지 않게 "계산하지 말라" 는 지시를 넣는다. 계산은 10 의 코드가 한다.
   - **이어 쓰기**: 잘린 답을 assistant 메시지로 넣고 이어서 쓰게 한다 (vLLM `continue_final_message`). 다만 스키마 제약 문법은 처음부터 다시 시작하므로, 이어 쓴 부분은 제약 없이 받고 나중에 검사해야 한다. 가장 복잡하다.
   - **`max_tokens` 올리기** (1500 → 예: 4096): 서버 길이 16384 안에 들어간다. 가장 쉽지만 공백 반복에서는 시간만 더 쓴다.
   - 지금의 "짧게 다시 묻기" 는 마지막 안전망으로 남긴다.
3. 평가: 같은 30장을 두 번 이상 돌려 잘림·다시 묻기 횟수, 걸린 시간, 단계별 점수를 전후로 비교한다. 결과 폴더와 커밋을 이 덱에 넘긴다.

### 4.2 모델 바꿔 끼우기

하네스(단계, 프롬프트, 검사, 계산 코드)는 그대로 두고 역할 하나의 모델만 바꿔 R4 와 같은 명령으로 잰다. 모델은 `experiments/models/<이름>.sh` 프로필로 고른다 (`--ocr-profile`, `--reason-profile`, [getting_started.md](getting_started.md) 3절). 프로필은 설정 파일이라 새 모델마다 하나씩 더한다. 비교는 단계별 점수표(형상, 표제란, 치수, 전개)와 30장에 걸린 시간이다.

후보를 고른 조건 (2026-10-29 조사):

- **VRAM:** OCR 은 GPU 0 한 장(24 GB), 판단은 GPU 1~3 (72 GB). BF16 가중치는 파라미터 1개에 2바이트다. 여기에 KV 캐시(요청이 쓰는 메모리)가 더 든다. 지금의 Qwen3.6-27B(55.6 GB)도 세 장에 나눠 마지막 장 0.95 를 써야 16k 요청이 들어갔다 (`experiments/models/qwen3.6-27b.sh`). 그래서 판단 모델은 BF16 로 약 28B 까지, 그보다 크면 FP8 가중치판을 쓴다. A5000 에는 FP8 연산기가 없어 vLLM 은 FP8 가중치를 16비트로 풀어 계산한다. 메모리는 줄지만 속도는 재 봐야 하고, 이 서버에서 FP8 을 돌린 적은 아직 없다.
- **context length:** 모델 사양으로 정해진다. 아래 판단 후보는 모두 128k~262k 다 (Hugging Face `config.json` 의 `max_position_embeddings`). 우리 요청은 서버에서 16,384 로 자른다 (`--max-model-len`). 그래서 사양이 걸림돌이 되지는 않는다. 실제로 걸리는 것은 KV 캐시를 담을 VRAM 이다. OCR 쪽은 DeepSeek-OCR-2 만 8,192 로 짧다.
- **vLLM 지원:** 아래 후보는 모두 이 서버 vLLM 0.31 의 지원 목록(`ModelRegistry.get_supported_archs()`)에 구조가 있다.
- **성능:** OCR 은 OmniDocBench (문서 OCR 벤치마크) 점수를 본다. 판(v1.5, v1.6)이 다르면 비교할 수 없다. 우리 03 은 CAD 표제란을 잘라 그린 그림이라 문서 벤치마크는 참고일 뿐이다.

**OCR 후보 (GPU 0 한 장, 모두 24 GB 에 여유 있게 들어간다)**

| 모델 | 파라미터 (BF16 크기) | context | OmniDocBench | 비고 |
|---|---:|---:|---|---|
| `deepseek-ai/DeepSeek-OCR-2` (지금) | 3.39B (6.8 GB) | 8,192 | v1.5 91.09 (다른 집계는 89.17), v1.6 90.25 (확인 못 함) | 2026-01 |
| `PaddlePaddle/PaddleOCR-VL-1.6` | 0.96B (1.9 GB) | 131,072 | v1.6 96.34 | 2026-05, Apache-2.0 |
| `zai-org/GLM-OCR` | 1.33B (2.7 GB) | 131,072 | v1.5 94.62, v1.6 95.22 | 2026-01, MIT |
| `opendatalab/MinerU2.5-Pro-2605-1.2B` | 1.16B (2.3 GB) | 8,192 | v1.6 95.75 | 2026-05, 상업 사용에 조건이 붙는 라이선스 |
| `ATH-MaaS/OvisOCR2` | 0.85B (1.7 GB) | 262,144 | v1.6 96.47 (집계 글 한 곳만, 원 출처 확인 못 함) | 2026-07. 후속 `OvisOCR3` 은 2026-10-21 공개라 점수가 없다 |
| `XingChen-AGI/TeleOCR` | 1.42B (2.8 GB) | 128,000 | v1.6 96.91 (집계 글 한 곳만, 확인 못 함) | 2026-08 |

- 제안: **PaddleOCR-VL-1.6** 과 **GLM-OCR**. 같은 판(v1.6)에서 지금보다 5점쯤 높고, 점수 출처가 여럿이며, 라이선스에 조건이 없다.
- 주의 1: 03 단계는 OCR 모델에 `"Free OCR."` 라는 지시를 고정으로 보낸다 (`reader/vlm.py` 의 `ocr_text`, DeepSeek-OCR 용 문구). 다른 OCR 모델은 저마다 정해진 지시문이 있다 (예: PaddleOCR-VL `OCR:`, GLM-OCR `Text Recognition:`). 모델마다 지시문을 바꾸려면 코드를 고쳐야 한다. 이 worktree 는 그대로 넣어 보고, 결과가 나쁘면 지시문 때문인지 따로 적는다.
- 주의 2: 합성 30장의 표제란 점수는 이미 30/30 이다. 정규식(02)이 먼저 읽고 OCR·판단(03·04)은 빈칸만 채우기 때문에, OCR 을 바꿔도 점수표가 움직이지 않을 수 있다. 그래서 03 의 받아쓴 원문을 정답 필드와 직접 대조해 본다 (세션 임시 폴더의 분석 스크립트, 레포 코드는 고치지 않는다). 표제란 글자가 다른 시험 도면 3건(부록)에서도 본다.

**판단(reasoning) 후보 (GPU 1~3, 72 GB)**

| 모델 | 파라미터 (BF16 크기) | 구조 | context | 72 GB 에 | 볼 것 |
|---|---:|---|---:|---|---|
| `Qwen/Qwen3.6-27B` (지금) | 27.8B (55.6 GB) | dense | 262,144 | BF16 | 기준 |
| `Qwen/Qwen3.8-27B` | 27.8B (55.6 GB) | dense, 같은 구조 | 262,144 | BF16 | 같은 크기의 새 판 (2026-08). 모델 판만 바꾼 효과 |
| `Qwen/Qwen3.8-27B-FP8` | 27.8B (약 30 GB) | dense | 262,144 | GPU 2장 | 양자화 효과. 지금 프로필 `qwen3.6-27b-fp8` 과 같은 방식 |
| `google/gemma-4-26B-A4B-it` | 25.8B (51.6 GB) | MoE (한 번에 약 4B 사용) | 262,144 | BF16 | 다른 계열 모델, 빠를 것 |
| `google/gemma-4-31B-it` | 31.3B (62.5 GB) | dense | 262,144 | FP8 판 필요 (`RedHatAI/gemma-4-31B-it-FP8-dynamic`) | 다른 계열의 큰 dense |
| `Qwen/Qwen3.6-35B-A3B` | 36.0B (71.9 GB) | MoE (약 3B 사용) | 262,144 | FP8 판 필요 (`Qwen/Qwen3.6-35B-A3B-FP8`) | 같은 계열 MoE |
| `Qwen/Qwen3-VL-32B-Instruct` | 33.4B (66.7 GB) | dense | 262,144 | FP8 판 필요 (`…-FP8`) | 한 세대 전 VL 전용 |
| `ATH-MaaS/Ovis2.6-30B-A3B` | 31.4B (62.8 GB) | MoE | 262,144 | 빠듯함 | OmniDocBench v1.6 93.70 (범용 모델 중 1위) |
| `google/gemma-4-12B-it` | 12.0B (23.9 GB) | dense | 262,144 | GPU 1~2장 | 작은 모델 |
| `zai-org/GLM-4.6V-Flash` | 10.3B (20.6 GB) | dense | 131,072 | GPU 1장 | 작은 모델 |
| `Qwen/Qwen3-VL-8B-Instruct` | 8.8B (17.5 GB) | dense | 262,144 | GPU 1장 | 작은 모델 |

- 제안 (발표 전에 돌릴 수 있는 만큼): **Qwen3.8-27B** (새 판), **gemma-4-26B-A4B** (다른 계열, BF16 로 들어간다), 작은 모델 하나 (**Qwen3-VL-8B** 또는 **gemma-4-12B**. "작은 모델 + 하네스" 가설을 직접 본다). 시간이 남으면 Qwen3.8-27B-FP8.
- 크기와 context 는 2026-10-29 에 Hugging Face API (`safetensors.total`, `config.json`)에서 읽었다. 점수는 [Roboflow 정리 (2026-08-03)](https://roboflow.com/blog/best-open-source-ocr-models), [CodeSOTA OmniDocBench (2026-05-21)](https://www.codesota.com/ocr/benchmark/omnidocbench), [Docsumo 정리](https://www.docsumo.com/blog/best-ocr-models) 에서 가져왔다.
- 받을 양: 제안한 판단 모델 셋과 OCR 둘을 합쳐 약 130 GB.
- 2026-10-29 기준 이 서버의 Hugging Face 캐시에는 DeepSeek-OCR-2 와 Qwen3.6-27B 만 있고, `/home` 은 759 GB 비어 있다.
- 동료의 Claude 실행(`runs/reader/data_v3_claude_batch_10141611`, 25/30)은 코드와 날짜가 달라 비교에 쓰지 않는다 ([presentation.md](presentation.md) 6절 참고). M4 를 하면 같은 코드로 다시 잰다.
- "작은 로컬 모델이라도 하네스가 받쳐 주면 쓸 만하다" 는 가설([harness_engineering.md](harness_engineering.md) 1절)을 보이는 실험이다. 결과가 나빠도 그대로 싣는다.

## 5. 슬라이드 구성

파트마다 스크립트 하나(`presentation/build_meeting_<파트>.py`)로 나눌지, 한 파일로 할지는 만들면서 정한다. 그림은 빌드할 때 실행 폴더에서 읽어 `presentation/build/assets/` 에 그린다. 실행 결과가 없으면 회색 상자로 둔다.

### A. 도입

1. 표지
2. 한 장 요약: 세 단계의 형상·전개 점수와 이번에 한 일
3. 지난 미팅 뒤 바뀐 것: 실도면(v4) 대신 합성 도면 완주(v3 고도화)로 목표를 바꾼 이유 ([v3_upgrade.md](v3_upgrade.md) 1절)
4. 범위: 도면 → 전개도. 3D 를 뺀 이유와 뺀 단계 (1.1절)

### B. 배경 (지난 발표와 겹친다)

5. 하려는 일: 도면 → 전개도 → 커팅플랜
6. v2 → v3 한 장 요약
7. 합성 도면 5형상 (그림 5장)
8. 로컬 모델 두 개와 GPU 서버

### C. 하네스 동작 (reader 를 모식도로)

9. 전체 흐름 한 장: 10단계를 상자로, 코드 단계와 AI 단계(03·04·06·09)를 색으로 나눈다
10. 규칙 셋: 단계마다 파일 하나, 앞 단계 파일만 읽는다, 한 단계만 다시 돌릴 수 있다
11. 단계 파일 속 모습: `status`, `inputs`, `trace` (모델 이름, 입력 그림, 원문, 검증된 답)
12. 01 읽기: DXF 의 선·글자를 목록으로
13. 02~04 표제란: 정규식이 먼저 읽고 → OCR 이 받아쓰고 → AI 는 정규식이 못 읽은 칸만 채운다
14. 05 뷰: 선 덩어리를 묶어 정면·평면·측면 후보를 찾는다
15. 06 형상: AI 에게 번호 붙은 그림 + 참고 문서(skill) + 답 양식을 준다. 위치로 붙인 라벨과 AI 라벨이 다르면 review 에 남긴다
16. 07~08 합치기: 판독 결과를 한 파일로
17. 09 치수: AI 가 형상별 파라미터를 읽고, 비운 칸은 도면 전체 치수로 코드가 채운다 (어디서 온 값인지 `sources` 에 남는다)
18. 10 전개: 공식은 코드가 계산한다. AI 는 계산하지 않는다
19. 하네스 장치 1: 답 양식 강제와 검사 (양식이 틀리면 버린다)
20. 하네스 장치 2: 잘리면 짧게 다시 묻기 (#13)
21. 하네스 장치 3: 기록 (skill 문서 sha256, 모델 원문, 걸린 시간) → 틀린 원인을 단계로 짚는다
22. 같은 단계를 AI 가 도구로 고르게 하면: orchestrator 모식 (지난 발표와 겹친다)

### D. Before → After

23. 변천사 지도: ① → ② → ③ (2절 표를 그림으로)
24. ① → ②: 코드를 단계로 나눈 것만으로 얻은 것 (기록, 단계별 채점이 가능해짐). 겹치는 내용
25. 저울이 틀려 있었다: 옛 정답의 콘·경판·굽힘판 오류 (#2~#4)
26~29. 데이터 before → after: 콘, 경판(직선부 포함), 굽힘판, 제도 정비(숨은선, Ø, 중심선). `build_synthetic_changes_company.py` 의 모식도를 다시 쓴다
30. 현업자 정답을 기준으로 삼은 이유 (경판 −1.35%, 콘 −0.3%, v3_upgrade.md 5.4절)
31. 2×2 표: 코드 효과와 데이터 효과를 나눈 점수 (R1~R4)
32. 단계별 점수표 ② vs ③ (단계, 표제란, 뷰, 형상, 치수, 전개, 전부)
33~42. 형상마다 대표 도면 하나를 단계별로 따라가기 (5형상 × 2장): 그림 `title_block.png` → `sheet_labeled.png` → `sheet.png` → `flat_pattern.png` 을 ② 와 ③ 으로 나란히. `scripts/reader/show_stages.py` 의 출력을 쓴다
43. 고친 것 요약 (#1~#10 데이터, #13 하네스, #16 코드)
44~47. 남은 실패를 그림으로: #11 원만 있는 뷰를 놓침, #14 콘 대경을 외경으로, #15 2:1 경판을 반구로, #17 굽힘판 폭·다리 바꿔 읽음
48. 남은 실패를 고칠 곳: 모델이 아니라 하네스(외형 치수와 대조)와 코드

### E. 추가 실험

49~51. JSON 답 잘림 전후 (4.1절, 다른 세션 결과)
52. 모델 바꿔 끼우기: 무엇을 같게 두고 무엇을 바꿨나
53~55. 모델별 단계 점수와 시간 (M0~M4)
56. 읽을거리: 하네스가 받쳐 주는 곳과 모델 크기가 드러나는 곳

### G. 다음 단계 v4

60. v4 는 무엇인가: v3 고도화에서 뺀 실제 도면 작업
61. 실제 도면이 지금 안 되는 이유: "시트 1장 = 부품 1개" 전제, 정답 22종 중 1개 (v4.md 4절)
62. 부품표부터 읽는다: 모식도 (v4.md 5절)
63. 손으로 확인한 기댓값: 정답 품번 22/22, 재질·두께 21/22 (v4.md 5.2절)
64. 계획 3단계: 부품표 읽기 → 부품 목록 → 채점 (v4.md 8절)
65. 하네스 로드맵에서의 위치 ([harness_engineering.md](harness_engineering.md) 3절)
66. 회사에 부탁할 것: 계산 문서와 현업자 정답이 다른 곳, 실제 도면 세트

### H. 마무리

67. 정리
68. 질문

부록:

- 현업자가 그린 시험 도면 3건 (발표 전에 돌린다): 개발 세트와 시험 세트를 나눈 이유 ([v3_upgrade.md](v3_upgrade.md) 5.1절), 3건의 형상과 정답 전개 (5.2절 표), 결과. DWG 라 00 `convert` 부터 돌린다. `score_synthetic.py` 는 `label.json` 을 읽는데 이 3건에는 없으므로 (5.3절 5) 단계 파일의 형상·전개 값을 정답 전개도와 손으로 대조해 표로 싣는다
- 도면별 점수표 R1~R4, 모델별 점수표, 실행 명령 (숨김)

고객 도면은 지난 덱처럼 집계 숫자만 쓰고 도면 그림이나 파일 이름은 싣지 않는다.

## 6. 순서

1. 이 문서 (2026-10-29)
2. 서버를 띄우고 R4 → R1 → R2 → R3 (각 약 12~25분, 옛 코드는 1묶음이라 더 걸린다)
3. 그 사이 C 파트(모식도)를 만든다. 실행 결과가 필요 없다
4. 실행이 끝나면 D 파트의 표와 그림
5. 모델을 정하면 M1~M4. 가중치 받기와 서버 재기동이 필요하다
6. E·F·G, 미리보기(`presentation/render.py`)로 넘침 확인, 숫자 출처 대조
7. [presentation.md](presentation.md) 에 숫자 출처 표

## 7. 정할 것

- 4.2절의 제안 모델로 할지, Claude API 상한선을 넣을지
- ①→② 슬라이드를 새로 만들지, 지난 덱(`build_v2_v3.py`)의 슬라이드를 그대로 가져올지

정한 것 (2026-10-29):

- 시험 도면 3건은 발표 전에 돌려 부록에 넣는다.
- JSON 잘림의 로직 수정(4.1절)과 모델 바꿔 끼우기(4.2절)는 사용자가 다른 세션·worktree 에서 한다. 4절은 그 작업의 맥락으로 남기고, 결과가 나오면 슬라이드에 반영한다.
- 이 worktree(`pbl-meeting` 브랜치)는 레포 코드를 고치지 않는다. 실행, 집계, 슬라이드 스크립트(`presentation/`)만 한다.
- 슬라이드는 이미 있는 실행 기록으로 먼저 만든다 (8절). R1~R4 와 시험 도면은 GPU 를 쓰므로 다른 세션의 실험과 겹치지 않게 사용자와 정한 뒤 돌린다.

## 8. 만든 것 (2026-10-29)

- 덱: `presentation/build_meeting.py` → `presentation/meeting.pptx` (69장). 만드는 명령과 숫자 출처는 [presentation.md](presentation.md) 1 · 8절.
- 이미 있는 실행 기록으로 만들었다. ① 은 동료 실행, ③ 은 2026-10-28 04:23 실행이다. ② 와 2×2 는 실행 뒤 채운다.
- 5절 계획과 다른 점: 시험 세트는 부록으로 옮겼다. 형상별 전 → 후 는 판독(① `sheet_labeled.png` 대 ③ `sheet.png`)과 전개(① `flat_pattern.png` 대 ③ 계산 · 정답 겹친 그림) 두 장씩이다. 남은 실패 #15 의 예시 press_formed_0026 은 반구가 아니라 FLAT FLANGED 로 읽은 경우라 "경판 종류를 잘못 고름" 으로 적었다.
- 남은 일: R1~R4 와 시험 도면 실행 (GPU 를 다른 세션과 나눠 쓰는 것을 정한 뒤), 실험 1 · 2 결과 반영, 지금 main 으로 다시 돈 ③ 으로 그림 · 점수 바꾸기.

### 8.1 구성을 바꿨다 (2026-10-29)

사용자 피드백: 지난 미팅에 없던 회사 사람들도 온다. 지난주 내용을 안다고 보고 글로 넘어가면 안 되고, 용어부터 글과 그림으로 정의한 뒤 진행한다. "저울" 같은 비유는 정의 없이 쓰지 않는다.

순서 (83장):

1. 용어: 하려는 일(도면 → 전개도 → 커팅플랜, 실제 그림), 설계 도면(뷰 · 치수 · 표제란을 도면 위에 표시), 형상 5종, 전개(원통 → 직사각형, 콘 → 부채꼴 모식과 실제 전개도), 합성 도면과 정답(label.json), reader 와 로컬 AI, 하네스, 채점 항목(cone_0023 의 정답 대 reader 값)
2. 판독 과정: cone_0023 한 장을 넣으면 01 ~ 10 단계마다 무엇이 나오나
3. 지난주: 범위, 성능(형상 27/30, 전개 11/30), 성공 사례(cylinder_0014), 실패 사례(cylinder_0013 답 잘림, 콘 · 경판 전개), 실제 도면 5장, 드러난 문제, 그래서 v3 고도화, 범위(3D 뺌)
4. 하네스 장치: 규칙, 단계 파일, 답 양식, 다시 묻기, 기록, orchestrator
5. 전 → 후: 이번 결과 한 장 요약, 변천사, 정답이 틀려 있었다, 데이터 전후, 2×2, 점수, 형상별 전후, 남은 실패
6. 실험 · 7. v4 · 마무리 · 부록

### 8.2 입력 → 처리 → 출력, AI 를 부르는 법 (2026-10-29)

사용자 피드백: 단계마다 입력과 출력이 무엇인지 확실히 보여야 한다. 청중은 AI 와 로컬 LLM 을 써 본 적이 없으니 판단 모델에게 지시를 어떻게 주고 규칙을 어떻게 주는지, VLMClient 가 어떻게 도는지 설명해야 한다.

- 판독 과정: 단계 슬라이드 9장(01, 02, 03, 04, 05, 06, 07·08, 09, 10)을 같은 틀로 바꿨다. 입력 칸(그림 · 글자 · 표), 처리 칸(누가: 코드는 청록, AI 는 주황, 무엇을), 출력 칸(그 단계 파일의 실제 값), 아래에 핵심 한 줄. 전체 흐름 슬라이드의 상자도 "입력 → 출력" 으로 적었다.
- 용어 파트에 'AI 를 부르는 법' 5장: 1 메시지 한 통(시스템 지시 · 질문 · 그림 → 서버 → JSON 답, temperature 0, 1,500 토큰, OCR 은 "Free OCR."), 2 06 단계의 실제 지시문(영어 원문과 한국어 뜻), 3 규칙 문서(skill)를 시스템 지시에 붙이는 법과 단계별 문서, 4 답 양식(OUTPUT CONTRACT, 서버 제약, 코드 검사), 5 VLMClient 한 번의 호출 8단계(AI 가 하는 일은 '보내기' 하나).
- 덱은 90장이다.

### 8.3 하네스 파트: JSON 과 tool calling (2026-10-29)

사용자 피드백: 하네스 엔지니어링이 PBL 전체를 관통하는 핵심 주제다. JSON 을 "파일 형식" 으로만 설명하고 넘어가면 안 되고, Qwen 이 함수를 직접 실행하지 않고 "어느 도구를 어떤 인자로" JSON 으로 답하면 Python 이 실행하고 결과를 다시 대화에 넣는 반복 구조가 들어가야 한다. 그 전 덱에는 orchestrator 한 장(도구 이름 상자)뿐이었다.

하네스 파트 (4장, 39~51장):

1. 하네스 엔지니어링: PBL 의 핵심 주제 (단계 나누기, JSON 약속, 검사 · 다시 묻기, 기록, 도구 호출 반복을 이 덱의 장과 연결)
2. JSON: AI 와 코드 사이의 약속 (자유 문장 대 JSON, 쓰이는 세 곳)
3. 장치 1: 양식 강제 (제약 디코딩. 다음 글자 후보를 서버가 지우는 그림)
4. 장치 2: 잘리면 다시 묻기, 규칙 셋, 단계 파일, 장치 3: 기록
5. tool calling: AI 는 함수를 실행하지 않는다 (시연의 실제 두 번째 답 JSON → ReaderTools.call → 결과를 대화에 붙여 다시 묻기)
6. 도구 목록 (tools.py: Tool 의 네 부분, 실제 도구 설명, call 의 에러 처리)
7. 대화 반복 (orchestrator.py orchestrate 의 반복을 줄인 코드와 순환 그림)
8. 도구를 알려주는 세 가지 방법 (tools · schema · Claude, schema 의 anyOf)
9. 시연: cone_0019 실제 대화 (턴별 Qwen 의 선택과 Python 의 결과, thought)

### 8.4 부록: tool calling 코드 해설 (2026-10-29)

사용자 피드백: orchestrator.py 의 클래스들이 하네스 엔지니어링의 기초인데 설명이 없다. 본편에서 코드를 읽을 수는 없으니 부록에 넣는다.

부록 '코드 1~8' (96~103장): 1 부품 지도 (두 파일이 나눠 맡는 일), 2 Call · Turn · Tool (세 공급자의 답을 같은 그릇에 담아 반복 코드가 하나), 3 backend 의 약속 start · next · add_results 와 세 방식 비교표, 4 OpenAISchema (anyOf 양식, finish, invalid_reply, thought), 5 system_prompt (역할 · 순서 · 의존 · 효율 · 금지 · 보고), 6 orchestrate() 와 Log (40턴 제한, 깨진 답 · 도구 에러를 결과로 돌려주기, 기록), 7 ReaderTools (_build, _stage_caller, 모델 고정, 작은 결과, 폴더 제한, call), 8 main · make_backend (명령에서 반복까지). 덱은 104장이다.

8.4 의 첫 판은 클래스 · 메서드 이름과 칸을 장마다 나열해 코드 리뷰처럼 읽혔다. 사용자가 더 추상적으로 설명해야 한다고 해서 '부록 · 하네스 구조 1~5' (96~100장)로 바꿨다. 장마다 개념 하나와 그림 하나를 두고, 코드 이름은 상자 밑의 작은 회색 '코드:' 글자와 발표자 노트에만 남겼다.

| 장 | 개념 | 코드 (노트에만) |
|---|---|---|
| 1 다섯 부품 | 모델은 한 부품이고, 지시문 · 진행 · 도구 상자 · 기록이 그것을 둘러싼다. 나눈 이유 | system_prompt, orchestrate, backend, ReaderTools · Tool, Log |
| 2 도구 상자 | 모델에게 보이는 것(도구 이름 · 설명 · 인자 양식)과 보이지 않는 것(실행, 단계 모델, 폴더, 요약) | Tool, ReaderTools._build · _stage_caller · workspace |
| 3 모델 연결부 | 모델마다 다른 답 형식을 공통 형식으로 바꿔서 모델을 바꿔 끼운다 | OpenAITools · OpenAISchema · AnthropicTools, Turn · Call |
| 4 규칙을 거는 두 방법 | 글로 부탁(지시문)과 구조로 강제(도구 목록, 인자 검사, 폴더, 답 양식, 턴 제한) | system_prompt, ReaderTools.call, response_format, max_turns |
| 5 실패와 기록 | 실패는 에러 결과로 모델에게 돌려주고, 명령 · 턴 · 대화 · 보고를 파일로 남긴다 | invalid_reply, ReaderTools.call, Log |

덱은 101장이다.

### 8.5 덱 두 개, 전 → 후 (2026-10-30)

사용자 결정: 내용이 "지금 판독기가 어떻게 도는가" 와 "무엇이 문제였고 무엇을 고쳤나" 둘로 나뉘므로 덱도 둘로 나눈다. 세 단계 변천사(① → ② → ③)는 쓰지 않는다. ① → ② 의 단계 파일 · 기록은 사람이 보고 이해하라고 한 정리이지 문제를 푼 변경이 아니다 (2.1절: 판독 계산이 같다). 그래서 ① 과 ② 를 묶어 '전', ③ 을 '후' 로 한다. 전의 문제는 "틀린 정답으로 쟀고, 그마저 다 재지 않았다" 로 정리하고, 후에서는 고친 것과 점수가 어떻게 달라졌는지를 말한다.

- 스크립트는 `presentation/build_meeting.py` 하나로 두고 인자로 덱을 고른다 (`harness`, `change`, 없으면 둘 다). 두 덱이 그림 · 표 함수를 같이 쓰기 때문이다. 슬라이드 함수는 `PARTS` 번호로 자기 파트를 적고, 덱마다 `DECKS` 의 파트 목록이 오른쪽 위 진행 표시를 정한다. 섹션 번호는 덱 안의 순서로 매긴다.
- `meeting_harness.pptx` (49장): 표지 · 목차 → 용어 14장 → 판독 과정 (흐름 + 단계 9장) → 하네스 장치 13장 → 정리 · 질문 → 부록 하네스 구조 1~5 · 실행 명령.
- `meeting_change.pptx` (59장): 표지 · 목차 · 정답 · 채점 정의 → 전 (전은 무엇인가, 범위, 성능, 성공 · 실패 사례, 전의 문제, 정답이 틀려 있었다, 목표를 바꾼 이유, 범위) → 후 (고친 것, 콘 · 경판 · 제도 · 현업자 기준, 결과 요약, 단계별 점수 전 → 후, 형상별, 형상마다 판독 · 전개 전 → 후, 남은 실패) → 실험 → 정리 · 질문 → 부록 (2×2, 시험 도면, 도면별 결과, 실행 명령). v4 파트는 8.7절에서 뺐다.
- 새로 만든 장: '전' 은 무엇인가, 전의 문제, 전 → 후: 고친 것 (문제 넷과 고친 것을 짝지음), 하네스 덱의 정리. 결과 요약은 전 · 후 두 칸, 단계별 점수 표에는 '전 (다시 잼)' 열(R2)을 더했다. 2×2 는 R2 만 돌렸으므로 부록으로 옮겼다.
- 지운 장: 변천사 세 단계, ① → ②: 단계로 나눈 것.
- 2026-10-30 사용자 결정: '전' 에서 회사 실제 도면 이야기는 뺀다. '실제 회사 도면 5장' 슬라이드(`lastweek_real_slide`)를 지우고, '지난주까지의 범위' 에서 실제 도면 5장을 뺐다. 실제 도면은 v4 파트에서만 다룬다.

### 8.6 도면 고침을 항목마다 전 → 후 그림으로 (2026-10-30)

사용자 요청: '도면 자체도 고쳤습니다' 의 각 항목을 문제가 된 옛 도면과 고친 새 도면으로 비교한다. 표 슬라이드 뒤에 항목마다 한 장씩 6장을 더했다 (덱 65장). 같은 도면 번호는 옛 · 새 데이터에서 치수와 뷰 배치가 같아, 같은 좌표로 잘라 나란히 놓는다.

| # | 도면 | 자른 곳 | 표시 |
|---|---|---|---|
| 1 | press_formed_0027 | 정면도 오른쪽 끝 | 꺾이는 점 / TL |
| 6 | flat_0001 | 우측면도 구멍 자리 | 옛 도면의 두 번 들어간 숨은선 (주황) |
| 7 | flat_0001 | 구멍 주기 글자 | `2-Ã˜13` / `2-Ø13` |
| 8 | cone_0019 | 정면도 + 평면도 | 안쪽 선, 위쪽 안쪽 원 |
| 9 | bent_sheet_0008 (t 6, R 0) | 정면도 굽힘부 | 각진 모서리 / 반지름 6 의 호 |
| 10 | flat_0001 | 우측면도 구멍 자리 | 빠진 중심선 / 새 중심선 (주황) |

- #6 의 72개는 옛 30장의 같은 레이어 · 같은 좌표 LINE 을 세어 다시 확인했다 (10장, 2+16+8+10+2+8+8+8+2+8).

**새로 찾은 결함 (아직 고치지 않음).** 새 생성기의 도면은 숨은선이 실선으로 그려진다. `scripts/build_synthetic.py` 의 `new_document` 가 HIDDEN 레이어에 선 종류 `HIDDEN` 을 주는데, `ezdxf.new(setup=True)` 의 기본 선 종류에는 `HIDDEN` 이 없다 (`DASHED`, `CENTER`, `PHANTOM2` 등은 있다). 그래서 새 30장 모두 HIDDEN 레이어가 정의되지 않은 선 종류를 가리킨다. 판독기는 선 종류 이름에 `HIDDEN` 이 있는지로 숨은선을 가리므로 (`dxf_adapter._line_type`) 계산은 그대로지만, AI 에게 보이는 그림(`analysis/sheet_labeled.png`)에서도 숨은선이 실선이다. 옛 도면에는 `HIDDEN` 선 종류가 정의돼 있다. 고치려면 생성기에서 `HIDDEN` 선 종류를 정의하고 30장을 다시 만들어야 하므로 main 에서 따로 한다. 덱의 #6 · #10 노트에 적었다.

### 8.7 v4 파트를 뺐다 (2026-10-30)

사용자 결정: 앞으로 무엇을 할지는 들어가야 하지만, 슬라이드로 정하지 않고 미팅 현장에서 논의한다. 그래서 전 → 후 덱에서 v4 파트 7장(섹션 표지, 실제 도면은 왜 아직 안 되나, 부품표부터 읽는다, 손으로 확인한 기댓값, v4 계획, 하네스 로드맵, 회사에 부탁드릴 것)을 지웠다 (58장). 목차의 v4 줄과 오른쪽 위 진행 표시의 v4 를 뺐고, 정리의 '다음' 은 "답 잘림 · 모델 비교 실험을 마무리. 그다음 할 일은 오늘 함께 논의" 로 바꿨다. '목표를 바꿨습니다' 슬라이드는 지난주 계획이 실제 도면이었다는 사실만 남긴다. 지운 슬라이드는 31be1c0 의 `build_meeting.py` 에 있다. 회사에 확인을 부탁할 것 중 계산 기준(경판 원판, 콘 평균지름)은 '기준: 현업자가 그린 정답' 장에, 굽힘판 바깥 모서리는 '도면 고침 #9' 장에 남아 있다.
