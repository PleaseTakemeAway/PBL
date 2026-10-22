# 데이터와 스크립트

이 프로젝트가 쓰는 데이터가 어디에 있고, 어떤 스크립트가 무엇을 읽어 무엇을 만들며, 어느 코드가 그것을 쓰는지 정리했다. 2026-10-22 서버의 실제 폴더 기준이다.

데이터는 전부 git 에서 빠져 있다 (`.gitignore`). 이 레포는 public 이라 데이터, 고객 도면, 판독 기록을 커밋하지 않는다. 데이터는 팀 공유 압축본(노바투스2026.zip)과 동료 서버에서 받는다.

## 1. 데이터 지도

| 경로 | 무엇 | 만드는 곳 | 쓰는 곳 |
|---|---|---|---|
| `Data/20YY년 cutting plan/` | KDM 연도별 커팅플랜 원본 `*_CP.dwg` (2023·2024·2025). `images/` 에 PNG 와 DXF(`images/_dxf/`) 변환본 | 압축본 | `build_dataset.py`, `extract_part_unfolds.py` |
| `Data/KD_CP_파일목록.xlsx` | 커팅플랜 파일 목록 | 압축본 | `build_dataset.py` |
| `Data/_dataset/` | 이전 세션 툴킷이 커팅플랜에서 뽑은 정답 표. `sheets.csv` (판재 936장), `parts.csv` (부품 13,388개의 판 위 위치), `part_tags.csv` (부품표 838행), `scorecard.csv` (도면별 추출 품질), `nesting_dataset.json` (판·부품 좌표), `SUMMARY.txt` (집계) | 툴킷 (압축본) | `build_dataset.py`, `extract_part_unfolds.py`, `build_part_class_dataset.py`, `cutplan_agent/unfold.py --validate` |
| `Data/data_v2/` | 현대건설기계(HCE) 판금 샘플 76K3-40022: 스캔 PDF, BOM xlsx, 고객 정답 전개 DXF, TruTops 네스팅(TAF) | 압축본 | `build_dataset.py` |
| `Data/drive/8. Data/` | Google Drive 원본을 푸는 자리. 아직 없다 | 사람 | `ingest_drive_inputs.py` |
| `Data/dataset/` | 워크오더 단위로 모은 데이터셋. 구조는 [dataset_structure.md](dataset_structure.md) | 스크립트 ①②③ | v2 `orchestrator.py` (`input/drawings`), `compare_with_gt` (`gt/sheets.csv`), `build_test_data.py` |
| `Data/part_class_dataset/` | 부품 전개 이미지(512px PNG 1,789장) ↔ 형상 class 5종. 규칙은 [part_class_rules.md](part_class_rules.md) | 스크립트 ④ | 코드에서 읽는 곳은 아직 없다 (분류 학습·평가용) |
| `test_data/` | 입력 도면·전개도·커팅플랜이 모두 있는 워크오더 39개 (KDM 38, HCE 1). `index.csv` 에 제외된 32개와 사유도 있다 | 스크립트 ⑤⑥ | v2 `eval/run_experiments.py`, `eval/compare_outputs.py`, `eval/manual_vlm_run.py` |
| `data_v3/synthetic/` | 합성 도면 30장. 형상 5종(flat, bent_sheet, cylinder, cone, press_formed) × 6장. 폴더마다 `<id>.dxf`, `<id>.png`, `label.json` (class, 치수, 구멍) | 동료 서버에서 rsync. 생성기는 레포에 없다 | v3 `experiments/experiments.sh` 의 기본 입력, `reader/main.py --batch` |
| `tests/fixtures/` | reader 단위 테스트 입력: `box.json`, `KD23041_CP.dxf`, HCE 스캔 `hce_*.png`. 고객 도면이 들어 있다 | 압축본 | `tests/` |
| `runs/` | 실행 결과. v2 는 `runs/<job>/`, v3 는 `runs/reader/` (동료의 기준 결과 `deepseek_ocr_qwen_reasoning_skills` 등 포함) | 실행 | `eval/status.py`, `eval/compare_outputs.py`, 기준선 비교 |
| `tools/dwg2png/` | 이전 세션 툴킷. 이 서버에는 없다 | 동료 | Windows 의 `dwg2dxf.exe` 만 코드가 쓴다 |

경로의 기준은 `cutplan_agent/config.py` 의 `ROOT` 다. 기본은 레포 루트이고 `CUTPLAN_ROOT` 로 바꿀 수 있다.

## 2. 데이터가 만들어지는 순서

```
압축본: Data/20YY년 cutting plan/, Data/_dataset/, Data/data_v2/        Drive: Data/drive/8. Data/
        │                                                                      │
        ▼ ① build_dataset.py                                                   │
Data/dataset/KDM/<year>/<wo>/{cutting_plan, gt}, HCE/76K3-40022/, manifest.csv │
        │                                                                      │
        ▼ ② extract_part_unfolds.py                                            ▼ ③ ingest_drive_inputs.py
Data/dataset/KDM/<year>/<wo>/unfold/*.dxf               Data/dataset/KDM/<year>/<wo>/input/{drawings, calculation, por}
        │
        ├─▶ ④ build_part_class_dataset.py ─▶ Data/part_class_dataset/
        │
        └─▶ ⑤ build_test_data.py ─▶ test_data/ ─▶ ⑥ build_test_data_html.py ─▶ test_data/README.html
```

평소에는 압축본의 `Data/` 를 그대로 두고 ⑤ 만 실행하면 된다. `Data/` 를 처음부터 다시 만들 때만 ①~⑥ 을 차례로 실행한다. 모두 레포 루트에서 `PYTHONPATH=. uv run python scripts/<이름>.py` 로 실행하고, 원본 폴더는 복사만 하고 고치지 않는다.

| | 스크립트 | 읽는 것 | 만드는 것 | 참고 |
|---|---|---|---|---|
| ① | [`build_dataset.py`](../../scripts/build_dataset.py) | `Data/20YY년 cutting plan/` (dwg, `images/` 의 png·dxf), `Data/_dataset/` 의 `sheets`·`parts`·`part_tags`·`scorecard` CSV, `KD_CP_파일목록.xlsx`, `Data/data_v2/` | `Data/dataset/` 의 `KDM/<year>/<wo>/cutting_plan/`, `gt/`, `HCE/`, `manifest.csv`, `README.md` | `gt/` 는 워크오더별로 잘라낸 정답 CSV 와 `scorecard.json` |
| ② | [`extract_part_unfolds.py`](../../scripts/extract_part_unfolds.py) | 커팅플랜 DXF (`images/_dxf/`), `nesting_dataset.json` | `unfold/*.dxf` (부품마다 하나), `unfold/index.csv` | 부품 bbox 안의 기하만 잘라낸다. `match` 열이 `ok` 인 행만 평가에 쓴다 |
| ③ | [`ingest_drive_inputs.py`](../../scripts/ingest_drive_inputs.py) | `Data/drive/8. Data/` (기술부 도면·계산서, 구매부 POR) | `input/drawings`, `input/calculation`, `input/por`, `input/index.csv`, `_third_party_index.csv`, `manifest.csv` 갱신 | 여러 번 실행해도 안전하다. 절차서는 용량 때문에 복사하지 않고 목록만 남긴다 |
| ④ | [`build_part_class_dataset.py`](../../scripts/build_part_class_dataset.py) | `part_tags.csv`, `nesting_dataset.json`, `unfold/*.dxf` | `Data/part_class_dataset/` (`part_tags_labeled.csv`, `dataset.csv`, `images/<class>/*.png`, `summary.json`) | `--dry` 는 CSV 만, `--only-ok` 는 `match=ok` 만 렌더 |
| ⑤ | [`build_test_data.py`](../../scripts/build_test_data.py) | `Data/dataset/` | `test_data/<wo>/{input_drawings, output_unfold, output_cutting_plan}`, `index.csv`, `README.md` | 3종이 모두 있는 워크오더만 넣는다. `--link` 는 복사 대신 하드링크 |
| ⑥ | [`build_test_data_html.py`](../../scripts/build_test_data_html.py) | `test_data/` | `test_data/README.html` | 썸네일이 들어간 한 파일짜리 개요. 브라우저로 연다 |

## 3. 정답 데이터와 평가

| 평가 | 정답 | 쓰는 코드 |
|---|---|---|
| v2 워크오더 결과 (판 수·중량) | `Data/dataset/.../gt/sheets.csv` | `skills/l4_verify.compare_with_gt` (`orchestrator.py --eval`, `eval/run_eval.py`) |
| v2 분할·네스팅 엔진 (E1, E2) | `test_data/<wo>/output_cutting_plan/*.csv`, `output_unfold/*.dxf` | `eval/run_experiments.py` |
| v2 원통 전개 공식 | `Data/_dataset/part_tags.csv` | `cutplan_agent/unfold.py --validate` |
| v3 형상 분류와 전개도 | `data_v3/synthetic/*/label.json` | `reader/batch.py`. 추론이 끝난 뒤에만 읽는다 |

정답을 쓸 때 주의할 점이다 (자세한 내용은 [dataset_structure.md](dataset_structure.md)).

- `unfold/index.csv` 의 `match` 가 `ok` 인 부품만 평가에 쓴다. `diff`·`none` 은 이웃 부품이 섞였거나 곡선이 잘렸을 수 있다.
- `sheets.csv` 의 `quality = chain_path` 판재는 부품을 나눌 수 없어 네스팅 평가에서 뺀다.
- 입력 도면이 없는 워크오더가 많다. `test_data/index.csv` 기준 제외 32개 중 24개가 Drive 압축 파트를 아직 못 받아 입력 도면이 없는 경우다.
- `data_v3/synthetic` 의 생성기는 레포에 없어서, 라벨을 어떤 규칙으로 계산했는지 코드로 확인할 수 없다.
