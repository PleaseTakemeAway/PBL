# 동료 서버로 옮겨 이어 하기 (2026-10-27)

이 문서는 동료(황예찬)의 GPU 서버에서 이 레포 작업을 이어받는 에이전트와 사람을 위한 인수인계다. 규칙은 루트 `AGENTS.md` 를 먼저 읽는다. 지금 목표와 진행 상황은 [v3_upgrade.md](v3_upgrade.md) 에 있다.

## 1. 왜 옮기나

동료는 로컬 모델(DeepSeek-OCR-2 + Qwen3.6-27B)로 형상 분류 29/30 을 얻었다고 한다. 우리 v3 reader 는 같은 로컬 모델로 26/30 이다 (v3_upgrade.md 3.1절, 새 데이터 기준). 동료가 돌린 서버에서 동료 계정으로 그 실행을 그대로 다시 돌려 29/30 이 나오는지 확인한다. 나오면 v3 와 무엇이 다른지 찾아 v3 하네스로 옮긴다.

## 2. 29/30 이 무엇인지 (2026-10-27, `mlic` 에서 확인)

사용자가 동료 서버에서 받은 `cutplan_v2_transfer.tar.gz` 를 열어 보고 확인했다. 이 파일은 동료 서버의 에이전트가 "이 파일만 옮기면 된다"고 만든 것이다. 크기는 32,775,801 바이트, sha256 은 `5bd4a6438d9d4d3d5f7a1ef2b47fbe81ffa9a4758fe28c0bd957693168cfed88` 이다.

| 항목 | 값 | 근거 |
|---|---|---|
| 결과 파일 | `cutplan_agent_v2/output/xgrammar_batch/accuracy.md`: `Overall: 29/30` | tar 안 |
| 실행 시각 | 2026-10-15 11:04 UTC | `predictions.json` 의 `generated_at` |
| 입력 | `/home/hwang/yechanhwang/PBL_2026/data_v3/synthetic`. **합성 30장이고 실제 도면이 아니다** | `predictions.json` 의 `inputs` |
| 입력 데이터 | 이 레포의 옛 `data_v3/synthetic` 과 같다. 90개 파일의 sha256 이 모두 일치 | tar 의 `data_v3/synthetic` 과 비교 |
| 재는 것 | 형상(part class) 분류만. 전개 치수는 재지 않는다 | `accuracy.md` 표 |
| 틀린 1장 | flat 1장 (5/6). 나머지 4형상은 6/6 | 같은 표 |
| 코드 | `cutplan_agent_v2/` (`main.py`, `step1.py`~`step6.py`, `pipeline.py`). 이 레포의 `cutplan_agent/reader/` (v3) 와 다른 코드다 | tar 안 |
| 모델 | `experiments_local.sh` 기본값: OCR `deepseek-ai/DeepSeek-OCR-2` (포트 8000), 판단 `Qwen/Qwen3.6-27B` (포트 8001), 판단 서버에 `--structured-outputs-config.backend=xgrammar` | tar 안 |
| 3D 복원 | 18장 `reconstructed`, 12장 `no_valid_candidate` (cone 6, press 4, flat 2). 복원에 실패해도 형상은 점수에 들어간다 | `predictions.json` 의 `status_counts` |
| 비전 방식 | 같은 tar 의 `vision_classification_batch` 는 0/30 | `accuracy.md` |

- 그러니 "실제 데이터에서 29/30" 이 아니라 **옛 합성 30장에서 형상 분류 29/30** 이다. 동료의 v3 결과 27/30 (`runs/reader/deepseek_ocr_qwen_reasoning_skills`) 도 같은 데이터다.
- tar 의 `data_v3/real/` 은 HCE 스캔 3장(`hce_74K4-60241_cover`, `hce_76K3-40220_support`, `hce_76K3-42510_plate`)이다. PNG 만 있고 DXF 는 없다. `data_v3/README.md` 는 정답을 "partial, unverified — manual reading of the sheet" 라고 적었다. 29/30 에는 들어가지 않는다.
- 판단 서버의 xgrammar 는 이 레포의 `experiments/vllm_common.sh` 도 이미 켠다. 그러므로 29/30 과 26/30 의 차이는 서버 설정이 아니라 코드(프롬프트, 형상을 정하는 방식, 토큰 제한 등)에서 찾아야 한다.
- **옛 생성기의 이름이 나왔다.** tar 의 `data_v3/README.md` 에 `python tools\make_data_v3.py --out data_v3 --per-class 6 --seed 3` 과 `python tools\eval_data_v3.py --data data_v3 --no-vlm --paths dxf,vision` 이 적혀 있다. 두 파일은 tar 에 없다. v3_upgrade.md 3절에 "생성기를 찾지 못했다"고 적은 것이 이 파일이다.

## 3. 서버에서 처음 할 일

동료 계정이므로 동료의 파일을 바꾸지 않는다. `/home/hwang/yechanhwang/PBL_2026/` 아래(`cutplan_agent_v2`, `cutplan_agent_v3`, `data_v3`, `skills`, `pbl`)는 읽기만 하고, 이 레포는 새 폴더에 받는다.

```bash
nvidia-smi                                   # 누가 어느 GPU 를 쓰는지. 동료는 GPU 4, 5 (90GB 급)를 썼다
ls /home/hwang/yechanhwang/PBL_2026/
find /home/hwang -name 'make_data_v3.py' -o -name 'eval_data_v3.py' 2>/dev/null   # 2절의 옛 생성기
```

- 동료 계정의 `.env`, `~/.ssh/`, 토큰 파일은 열지 않는다 (AGENTS.md 1절). 동료의 Claude API 키로 실행하지 않는다. 이번 목표는 로컬 모델이다.
- 커밋 작성자를 동료로 남기지 않는다. 받은 레포 안에서만 `git config user.name gwanwoochoi` 와 `git config user.email <사용자 메일>` 을 설정한다 (`--global` 금지).
- 이 레포는 public 이다. 동료 서버의 도면·정답·실행 기록을 커밋하지 않는다.
- push 권한(GitHub 인증)이 동료 계정에 있는지 모른다. 없으면 사용자에게 묻는다. 동료 계정의 키를 찾아보지 않는다.

레포 받기와 환경:

```bash
mkdir -p ~/gwanwoo && cd ~/gwanwoo
git clone https://github.com/PleaseTakemeAway/pbl.git && cd pbl
git switch synthetic-generator
uv --version || echo "uv 없음: 사용자에게 설치해도 되는지 묻는다"
uv sync
ln -s /home/hwang/yechanhwang/PBL_2026/data_v3 data_v3              # 옛 합성 30장 (git 제외 데이터)
PYTHONPATH=. uv run python scripts/build_synthetic.py --compare data_v3/synthetic   # 새 합성 30장 → data_v3/generated
```

- 위 `ln -s` 는 `data_v3/` 가 없을 때만 한다. 새 데이터를 `data_v3/generated` 에 쓰므로, 동료 폴더에 쓰게 되는 것이 싫으면 링크 대신 `mkdir data_v3 && ln -s /home/hwang/yechanhwang/PBL_2026/data_v3/synthetic data_v3/synthetic` 로 한다.
- `build_synthetic.py` 는 실행마다 바이트까지 같은 파일을 만든다. `mlic` 의 `data_v3/generated` 와 같아야 한다.
- 레포는 Python 3.12 이상이다. 동료의 vllm 가상환경 `PBL_2026/pbl` 은 Python 3.10 이라 레포 코드를 돌리는 데 쓰지 않고, vLLM 서버를 띄우는 데만 쓴다 (`--vllm-bin`).
- 단위 테스트: `PYTHONPATH=. uv run python -m unittest discover -s tests`. `mlic` 에서는 120건 중 17건이 실패한다 (`tests/fixtures/` 와 tesseract 가 없어서, AGENTS.md 7절). 이 레포에서 쓴 테스트는 모두 통과해야 한다.

## 4. 재현과 비교 순서

1. **동료 코드를 그대로 다시 돌린다.** `PBL_2026/cutplan_agent_v2` 에서 `experiments_local.sh` 를 쓰되, 출력은 기존 `output/xgrammar_batch` 를 덮지 않게 새 폴더로 준다 (`CUTPLAN_BATCH_OUTPUT`). GPU 는 비어 있는 것을 고른다.
   ```bash
   cd /home/hwang/yechanhwang/PBL_2026/cutplan_agent_v2
   ./experiments_local.sh --help
   CUTPLAN_BATCH_OUTPUT=~/gwanwoo/runs/v2_rerun_old CUTPLAN_VLLM_BIN=../pbl/bin/vllm \
     ./experiments_local.sh --ocr-gpu 4 --reason-gpu 5 ../data_v3/synthetic
   ```
   `accuracy.md` 가 29/30 인지 본다. 동료 폴더 안에 파일이 생기는지(로그, 캐시) 확인하고, 생기면 사용자에게 알린다.
2. **같은 동료 코드를 새 합성 30장에 돌린다.** 입력만 `~/gwanwoo/pbl/data_v3/generated` 로 바꾼다. 새 도면은 경판 모양과 치수 표기가 다르다 ([data/synthetic.md](data/synthetic.md) 5절).
3. **이 레포의 v3 를 같은 서버·같은 GPU 에서 돌린다.** 서버는 `serve.sh` 로 띄운다. 기본 GPU 는 `mlic` 용(0 / 1,2,3)이므로 바꾼다.
   ```bash
   cd ~/gwanwoo/pbl
   ./experiments/serve.sh --vllm-bin /home/hwang/yechanhwang/PBL_2026/pbl/bin/vllm \
     --ocr-gpu 4 --reason-gpu 5 --reason-parallel tensor
   # 다른 셸에서
   experiments/batch_parallel.sh data_v3/synthetic runs/reader/hwang_old 3
   experiments/batch_parallel.sh data_v3/generated runs/reader/hwang_new 3
   uv run python scripts/reader/score_synthetic.py runs/reader/hwang_new
   ```
   `score_synthetic.py` 는 새 정답(`data_v3/generated`)에 맞춘 채점이다. 옛 데이터 결과는 각 묶음의 `accuracy.md` 의 형상 점수만 본다.
4. **차이를 찾는다.** 형상 분류에서 v2 가 맞히고 v3 가 틀린 도면을 골라, v2 의 `step*.py` 프롬프트와 출력(`output/<실행>/<도면>/`)을 v3 의 06 `classify` 단계 기록(`stages/06_*`)과 나란히 본다. `mlic` 기준선에서 v3 가 형상을 못 낸 4장(cylinder_0013·0016·0017, flat_0002)은 모델 답이 잘려 JSON 이 깨진 경우다 (v3_upgrade.md 4절 #13). v2 도 flat 1장을 틀렸는데, 동료 서버 에이전트는 이것을 flat_0002 로 분석했다고 했다.
5. **기록한다.** 결과 표와 원인은 v3_upgrade.md 3.1절과 4절에 더한다. 옛 생성기를 찾으면 경로와 sha256 을 v3_upgrade.md 3절에 적는다. 코드는 사용자에게 묻기 전에 커밋하지 않는다.

## 5. 이 브랜치의 상태 (`synthetic-generator`, 2026-10-27)

- 목표: 합성 도면에서 v3 를 완벽하게 (v3_upgrade.md 2절의 기준). 3D 단계(11~13)는 실행에서 뺐다. `--with-3d` 로만 돈다 (같은 문서 1.1절).
- 새 생성기 `scripts/build_synthetic.py`. 정답은 회사 계산 문서(`skills/01_core_knowledge/shell_cone_head_unfold.md`) 식이다. 옛 정답이 틀린 곳(콘 114~200%, 경판 16~25%)과 이유는 [data/synthetic.md](data/synthetic.md) 5절.
- reader 의 경판 원판 식을 회사 식(2:1 경판 1.2 × Dm + 2SF)으로 바꿨다 (`cutplan_agent/reader/unfold.py`).
- 새 데이터 기준선 (`mlic`, 로컬 모델): 형상 26/30, 전개 13/30, 전부 8/30. 남은 문제는 v3_upgrade.md 4절 #11~#18.
- 브랜치 `synthetic` 은 이 브랜치의 앞부분이다 (생성기 전, 목표 문서만).
- 사용자가 아직 정하지 않은 것: 4절 #9 (굽힘판 바깥 모서리 원호) 확인, reader·실험의 기본 입력을 `data_v3/generated` 로 바꿀지.
