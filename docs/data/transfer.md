# 데이터 옮기기: 새 서버에서 같은 결과를 내려면

코드는 git 으로 받고 데이터는 사람이 옮긴다. 이 문서는 새 서버(또는 새 clone)에 어떤 데이터를 어느 경로에 두는지, 무엇은 옮기지 않고 만드는지, 옮긴 뒤 원본과 같은지 어떻게 확인하는지 적는다. 데이터마다 무엇이 들어 있는지는 [overview.md](overview.md). 2026-10-28 에 썼다.

경로는 모두 **레포 루트 기준**이다 (`cutplan_agent/config.py` 의 `ROOT`, `CUTPLAN_ROOT` 로 바꿀 수 있다). 2026-10-28 기준 레포 루트는 다음과 같다.

| 서버 | 레포 루트 | 비고 |
|---|---|---|
| workstation1 (`mlic`, RTX A5000 ×4) | `~/developer/pbl` | 2026-10-27 까지 작업한 곳. `Data/`, `test_data/`, `runs/` 원본이 여기에 있다 |
| 동료 서버 (호스트 이름도 `mlic`, RTX PRO 6000 ×8, 계정 `hwang`) | `~/gwanwoo/pbl` | 2026-10-27 부터 작업하는 곳. 동료 폴더 `/home/hwang/yechanhwang/PBL_2026/` 는 읽기만 한다 ([../server_handoff.md](../server_handoff.md)) |

## 1. 무엇을 옮기고 무엇을 만드나

| 레포 루트 기준 경로 | 할 일 | 원본 위치 | 필요한 작업 |
|---|---|---|---|
| `data_v3/synthetic/` | **옮긴다** (다시 만들 수 없다. 옛 생성기 `make_data_v3.py` 는 어디에도 없다) | 동료 서버 `/home/hwang/yechanhwang/PBL_2026/data_v3/synthetic/`, workstation1 `~/developer/pbl/data_v3/synthetic/` (같은 파일) | 중간보고 형상 분류 29/30, reader 기본 입력, 실험 스크립트 기본 입력 |
| `data_v3/generated/` | **만든다** (2절) | `scripts/build_synthetic.py` | 회사 기준 정답으로 다시 만든 합성 30장 ([synthetic.md](synthetic.md)) |
| `data_v3/20261027example/` | **옮긴다** (900K) | workstation1 `~/developer/pbl/data_v3/20261027example/` (사용자가 2026-10-27 에 받아 둔 곳, 여기에만 있다) | 시험 세트: 현업자가 그린 도면 3건과 정답 전개도 ([../v3_upgrade.md](../v3_upgrade.md) 5절) |
| `tests/fixtures/` | **옮긴다** | 동료 서버 `/home/hwang/yechanhwang/PBL_2026/cutplan_agent_v3/examples/`, 팀 압축본의 `cutplan_agent_v3/examples/` | v3 단위 테스트 (없으면 17건 실패) |
| `Data/` | **옮긴다** (1.4G) | workstation1 `~/developer/pbl/Data/`, 팀 압축본(노바투스2026.zip)의 `Data/` | 레포 v2 (`cutplan_agent/`) smoke test, `scripts/` 의 데이터셋 만들기, 실도면 작업 |
| `test_data/` | **옮긴다** (729M). `test_data/cases/` 포함 | workstation1 `~/developer/pbl/test_data/` | v2 평가, 실도면 테스트셋 `test_data/cases/` (설비 S-2120, D-1203. [cutplan_cases.md](cutplan_cases.md)) |
| `runs/reader/` 의 기준 실행 | 필요하면 옮긴다 | workstation1 `~/developer/pbl/runs/reader/`, 동료 서버 `/home/hwang/yechanhwang/PBL_2026/cutplan_agent_v3/output/` | 예전 결과와 나란히 볼 때만. 코드는 읽지 않는다 |
| `tools/dwg2png/` | 옮기지 않아도 된다 | workstation1 `~/dwg2png` (레포 밖) | Windows 의 `dwg2dxf.exe` 만 쓴다. Linux 는 `scripts/install_libredwg.sh` |

- `test_data/` 는 `Data/dataset/` 이 있으면 `scripts/build_test_data.py` 로 다시 만들 수 있다. 그러나 `test_data/cases/` 는 회사 담당자에게 받은 원본(`test_data/cutting_plan/`, 지금은 없다)의 유일한 사본이라 반드시 옮긴다.
- `runs/` 는 실행 산출물이다. 새 서버에서 다시 돌려 만든다.
- 고객 도면이 든 데이터(`Data/`, `test_data/`, `tests/fixtures/`)는 public 레포에 넣지 않는다 (`.gitignore`).

## 2. 옮기기

새 서버의 레포 루트에서 실행한다. 원본 서버에 SSH 로 접속할 수 있다고 본다 (`<원본>` 은 `~/.ssh/config` 의 호스트 이름).

```bash
cd ~/gwanwoo/pbl                       # 새 서버의 레포 루트

# workstation1 에서 가져올 것
rsync -a --info=progress2 <원본>:developer/pbl/Data/      Data/
rsync -a --info=progress2 <원본>:developer/pbl/test_data/ test_data/
rsync -a --info=progress2 <원본>:developer/pbl/data_v3/20261027example/ data_v3/20261027example/

# 동료 서버에서는 복사하지 않고 링크로 둔다 (같은 기계, 동료 폴더는 읽기만)
mkdir -p data_v3
ln -s /home/hwang/yechanhwang/PBL_2026/data_v3/synthetic data_v3/synthetic
ln -s /home/hwang/yechanhwang/PBL_2026/cutplan_agent_v3/examples tests/fixtures
# 다른 서버라면 대신 복사한다
#   rsync -a <원본>:developer/pbl/data_v3/synthetic/ data_v3/synthetic/
#   rsync -a <원본>:developer/pbl/tests/fixtures/    tests/fixtures/

# 만드는 것 (옛 합성 도면이 있으면 --compare 로 옛 정답과의 차이표도 쓴다)
PYTHONPATH=. uv run python scripts/build_synthetic.py --compare data_v3/synthetic
```

- rsync 의 원본 경로 끝 `/` 는 "폴더 안의 내용" 이라는 뜻이다. 빼면 `Data/Data/` 가 생긴다.
- 레포 루트가 아닌 곳에 데이터를 두려면 `CUTPLAN_ROOT=<폴더>` 를 쓴다. 그 폴더 아래에 같은 이름(`Data/`, `test_data/`, `runs/`)으로 둔다. `data_v3/`, `tests/fixtures/` 는 레포 루트에 있어야 한다 (`experiments/*.sh`, `tests/` 가 레포 루트 기준으로 찾는다).

## 3. 확인

```bash
PYTHONPATH=. uv run python scripts/check_data.py
```

데이터마다 한 줄씩 `OK`, `없음`, `다름`, `기준 없음` 을 출력한다. `다름` 이 하나라도 있으면 종료 코드가 1 이다. 2026-10-28 동료 서버의 출력:

```
OK     data_v3/synthetic    파일 90개 일치
OK     data_v3/generated    파일 91개 일치
OK     tests/fixtures       파일 5개 일치
없음     Data                 옮긴다
없음     test_data            옮긴다
```

- 기준 파일은 `scripts/data_manifests/` 에 있다. 합성 도면과 fixture 는 파일별 sha256 (`*.sha256`), 고객 데이터인 `Data/`·`test_data/` 는 파일 이름을 남기지 않는 요약(`*.digest`: 파일 수, 바이트, 전체 해시 하나)이다.
- `data_v3/synthetic` 의 기준은 동료 서버의 원본에서 만들었다. 동료가 보낸 `cutplan_v2_transfer.tar.gz` 안의 같은 폴더, workstation1 의 사본과도 90개 sha256 이 모두 같다 ([../server_handoff.md](../server_handoff.md) 2절).
- `data_v3/generated` 는 `compare.md` 를 빼고 비교한다 (`--compare` 를 줄 때만 생긴다). 생성기나 정답 식을 일부러 바꿨으면 `--write data_v3/generated` 로 기준을 다시 쓰고 같은 커밋에 넣는다.
- `Data/`, `test_data/`, `data_v3/20261027example/` 의 기준은 2026-10-28 에 원본이 있는 workstation1 에서 `--write` 로 만들었다. `test_data/` 는 workstation1 의 2026-10-21 판이다 (AGENTS.md 7절). 옮긴 서버에서 `check_data.py` 가 `OK` 를 내면 같은 데이터다. 같은 날 workstation1 의 출력:
  ```
  OK     data_v3/synthetic        파일 90개 일치
  OK     data_v3/generated        파일 91개 일치
  OK     tests/fixtures           파일 5개 일치
  OK     data_v3/20261027example  파일 12개 일치
  OK     Data                     파일 14875개 일치
  OK     test_data                파일 9546개 일치
  ```
- workstation1 의 `tests/fixtures/` 는 레포 루트의 `fixtures/` 에 잘못 놓여 있었다. 5개 파일의 sha256 이 기준과 같아 2026-10-28 에 `tests/fixtures/` 로 옮겼다.

## 4. 옮긴 뒤 돌려 볼 것

| 확인 | 명령 | 기대 결과 |
|---|---|---|
| 단위 테스트 | `PYTHONPATH=. uv run python -m unittest discover -s tests` | `tests/fixtures/` 가 있고 tesseract 가 없으면 11건 실패 (AGENTS.md 7절의 목록) |
| 모델 없는 판독 | `PYTHONPATH=. uv run python cutplan_agent/reader/main.py --batch --input-mode dxf --no-vlm --output-dir runs/reader/novlm data_v3/generated` 후 `uv run python scripts/reader/score_synthetic.py runs/reader/novlm` | 표제란 30/30, 뷰 18/30, 나머지 0 |
| 로컬 모델 판독 | [../reader/quickstart.md](../reader/quickstart.md) 5절 | 형상 30/30 ([../v3_upgrade.md](../v3_upgrade.md) 3.1절) |
| 레포 v2 smoke test (`Data/` 필요) | `PYTHONPATH=. uv run python cutplan_agent/eval/smoke_kd25038.py` | 22/22 배치, 총 6132.2 kg |
