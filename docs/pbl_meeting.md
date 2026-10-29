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
| ③ `generated` / `reader+` | `data_v3/generated` (새 생성기, 현업자 기준 정답) | main | 3D 단계를 기본으로 끔, 생성기를 새로 쓰고 데이터 정답을 고침 (콘·경판·굽힘판 등 #1~#10), 경판·콘 식을 현업자 정답으로, 답 잘림 다시 묻기 (#13), 경판 직선부 측정 (#16) | `runs/reader/company_synthetic_20261028_042351` 이 있지만 2807e44·f111ea8 (현업자 기준 식, 경판 직선부) 전이다. 다시 돌린다 (3절 R4) |

①→② 는 코드만 바뀌었고 ②→③ 은 코드와 데이터가 같이 바뀌었다. ②→③ 의 점수 차이를 코드 덕분이라고만 말하면 틀린다. 그래서 2×2 로 돌려 둘을 나눈다 (3절).

①→② 는 지난 발표(`build_v2_v3.py`)와 겹친다. 그대로 넣고 발표 때 건너뛴다.

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
