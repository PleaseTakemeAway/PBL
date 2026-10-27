# 중간보고: 합성 도면 형상 분류

2026-10-28 에 동료와 정한 중간보고의 범위와 내용이다. 보고 자료를 만들 때 숫자와 문구는 이 문서를 따른다. 근거가 되는 실행 기록과 다시 돌리는 명령도 같이 적는다.

## 1. 합의 (2026-10-28)

1. 합성 데이터셋은 회사 도면에 흔한 쉬운 형상을 골라 만든 데이터셋이다.
2. 이 데이터셋에서 로컬 모델로 형상 분류 29/30 이 나왔다.
3. 실패한 1장은 출력 형식이 깨진 문제라서, 쉬운 형상은 잘 분류한다고 보고한다.
4. 중간보고는 1~3 만 한다.
5. 실제 도면을 읽는 일은 중간보고 뒤에 한다.

## 2. 보고할 내용

**데이터.** 회사 도면에 흔한 쉬운 형상 5종(평판, 굽힘판, 원통, 콘, 경판)을 골라 프로그램으로 그린 도면 30장이다. 형상마다 6장이고, 도면 1장에 부품 하나를 3면도와 표제란으로 그렸다. 형상 종류는 회사 도면에서 골랐고 도면 파일은 동료의 생성기가 그렸다. 회사 도면 파일을 그대로 가져온 것은 아니다 ([v3_upgrade.md](v3_upgrade.md) 3절). 폴더는 `data_v3/synthetic` 이다.

**모델.** 사내 GPU 서버에 띄운 로컬 모델 두 개를 쓴다. 글자 읽기는 DeepSeek-OCR-2, 판단은 Qwen3.6-27B 다. 도면은 외부 AI 서비스로 나가지 않는다.

**결과.** 형상 분류 29/30 이다 (동료 2026-10-15 실행).

| 형상 | 평판 | 굽힘판 | 원통 | 콘 | 경판 | 전체 |
|---|---:|---:|---:|---:|---:|---:|
| 맞힘 | 5/6 | 6/6 | 6/6 | 6/6 | 6/6 | **29/30** |

**실패 원인.** 못 맞힌 1장(flat_0002)은 판단 모델의 답이 길이 제한(1,500 토큰)에서 잘려 JSON 형식이 깨진 경우다. 형상을 답하지 못한 것이지, 다른 형상으로 잘못 답한 것이 아니다. 이 서버에서 지금까지 돌린 모든 실행(아래 표)에서 모델이 형상을 틀리게 답한 적은 한 번도 없다. 그래서 쉬운 형상은 잘 분류한다고 본다.

보고에서 덧붙일 수 있는 것: 답 잘림은 2026-10-28 에 고쳤다 (판단 서버가 JSON 사이 공백을 못 쓰게 하고, 잘리면 짧게 다시 묻는다). 고친 뒤 같은 30장을 두 번 돌려 두 번 모두 30/30 이다 ([v3_upgrade.md](v3_upgrade.md) 3.2절).

## 3. 숫자의 출처

모두 옛 합성 30장(`data_v3/synthetic`), 같은 두 모델이다. 실행 기록은 git 밖에 있다.

| 실행 | 코드 | 형상 | 못 맞힌 도면 (모두 답 잘림) | 기록 |
|---|---|---:|---|---|
| 동료 2026-10-15 (**보고하는 숫자**) | 동료 v2 (`archive/cutplan_v2`) | 29/30 | flat_0002 | 동료 서버 `/home/hwang/yechanhwang/PBL_2026/cutplan_agent_v2/output/xgrammar_batch/accuracy.md` |
| 동료 2026-10-18 | 동료 v3 (253020c) | 27/30 | cylinder_0013·0018, flat_0005 | 동료 서버 `cutplan_agent_v3/output/deepseek_ocr_qwen_reasoning_skills/` |
| 다시 돌림 2026-10-27 | `archive/cutplan_v2` 그대로 | 28/30 | flat_0002, cylinder_0016 | `~/gwanwoo/pbl/runs/reader/server1027/v2_old/` |
| 다시 돌림 2026-10-27 | 이 레포, #13 고치기 전 | 29/30 | flat_0002 | `runs/reader/server1027/v3_old/` |
| 다시 돌림 2026-10-28 ×2 | 이 레포, #13 고친 뒤 | 30/30, 30/30 | 없음 | `runs/reader/fix13/old_1`, `old_2` |

- 같은 코드라도 실행마다 어느 도면의 답이 잘리는지가 달라져 28~29/30 사이를 오갔다. 29/30 은 그중 동료가 처음 얻은 값이다. 차이가 코드가 아니라 답 잘림에서 온다는 근거는 [server_handoff.md](server_handoff.md) 6.3절.
- "실제 도면" 이나 "회사 실데이터" 결과가 아니다. 서버에 로컬 모델로 실제 도면을 읽은 실행은 없다 (같은 문서 6.1절).

## 4. 다시 돌리기

동료 서버, 레포 루트(`~/gwanwoo/pbl`)에서 실행한다. 데이터 준비는 [data/transfer.md](data/transfer.md).

```bash
# 창 1: 판단·OCR 서버 (GPU 4, 5). Ctrl-C 까지 떠 있다
./experiments/serve.sh --vllm-bin /home/hwang/yechanhwang/PBL_2026/pbl/bin/vllm --ocr-gpu 4 --reason-gpu 5

# 창 2: 이 레포의 판독기로 30장 (3묶음 동시, 약 12분). 묶음마다 accuracy.md 에 형상 점수가 나온다
experiments/batch_parallel.sh data_v3/synthetic runs/reader/interim 3
cat runs/reader/interim/shard*/accuracy.md | grep Overall

# 동료 v2 코드 그대로 (보고하는 29/30 을 낸 코드, 약 35분)
git worktree add --detach ~/gwanwoo/v2_archive archive/cutplan_v2
. runs/vllm/ocr.env; . runs/vllm/reason.env
(cd ~/gwanwoo/v2_archive && ~/gwanwoo/pbl/.venv/bin/python main.py ~/gwanwoo/pbl/data_v3/synthetic \
   --batch --input-mode dxf --output-dir ~/gwanwoo/pbl/runs/reader/interim_v2)
```

- 동료 v2 코드에는 #13 의 다시 묻기가 없다. 서버는 공백을 막은 채로 뜨므로 2026-10-15 와 조건이 같지 않다.

## 5. 보고하지 않는 것과 다음 순서

- 보고하지 않는다: 뷰 이름, 치수, 전개도 결과 ([v3_upgrade.md](v3_upgrade.md) 2절 기준, 3.1·3.2절 점수), 정답을 회사 계산 기준으로 다시 만든 새 합성 데이터(`data_v3/generated`)와 그 이유 ([data/synthetic.md](data/synthetic.md)). 회사 담당자용 자료 [company_brief.md](company_brief.md) 는 이것들을 다루는 10-27 자료다.
- 중간보고 뒤: 실제 도면 읽기. 회사에서 받은 설비 2건(S-2120, D-1203)의 도면과 커팅플랜(`test_data/cases/`, [data/cutplan_cases.md](data/cutplan_cases.md))부터 한다. 먼저 `Data/`, `test_data/` 를 이 서버로 옮긴다 ([data/transfer.md](data/transfer.md)). 실도면에 필요한 부품표 단계 계획은 `git show c71cca0:docs/v4.md` 에 있다.
