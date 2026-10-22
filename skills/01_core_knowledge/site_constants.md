# 현장 상수 — `cutplan_agent/config.py` 정리

출처: `cutplan_agent/config.py` (KDM 배치툴 발표자료 08 슬라이드의 설정값을 기본으로 둠). 2026-10-18 기준, 1절은 2026-10-23 에 고쳤다.
코드가 바뀌면 이 문서도 갱신할 것. 값을 고칠 때는 **config.py 가 원본**이고 이 문서는 사본이다.

## 1. 물성·중량

| 상수 | 값 | 단위 | 쓰임 |
|---|---|---|---|
| DENSITY_STEEL | 7.85e-6 | kg/mm³ | 탄소강. POR 중량 = t × W × L × 밀도. 검증: KD25038 `10 × 2438 × 9150` → 1,751 kg (실제 POR 일치) |
| DENSITY_SUS | 7.93e-6 | kg/mm³ | 스테인리스 (재질이 SA240, A240, SUS, STS, 304, 316 으로 시작). 회사 담당자 계산 문서 6절 (`shell_cone_head_unfold.md`) |
| HEAD_TRIM | 30 | mm | 헤드 원판에 더하는 트림 여유. 계산 문서: 제작사마다 다르며 보통 20~50, 예시 30 |

## 2. 커팅 여유·판 가장자리

| 상수 | 값 (mm) | 설명 |
|---|---|---|
| KERF_MARGIN["gas"] | 20 | 가스 절단 시 조각 간 간격. **기본값** (DEFAULT_CUT = "gas") |
| KERF_MARGIN["plasma"] | 10 | 플라즈마 |
| KERF_MARGIN["laser"] | 5 | 레이저 |
| EDGE_MARGIN | 10 | 판 가장자리에서 조각까지 최소 거리 |

검증 규칙: 조각 간 거리 < 커팅 여유 → 충돌, 가장자리 < 10 → 위반. (nesting_rules.md 와 동일)

## 3. 판재 규격

| 상수 | 값 | 설명 |
|---|---|---|
| TRANSPORT_MAX | (12000, 3050) mm | 운반 상한 (길이, 폭). 전개 형상이 이를 넘으면 분할 |
| SNAP | 100 mm | 맞춤 판재 길이 반올림 단위 (예: 9,137 → 9,200) |
| STD_WIDTHS | 1219 · 1524 · 1829 · 2000 · 2134 · 2438 · 2500 · 2670 · 3048 | 폭 후보. 밀 표준폭 + sheets.csv 상위 규격 |
| STD_LENGTHS | 2438 · 3048 · 4000 · 5000 · 6000 · 6096 · 7000 · 8000 · 9000 · 10000 · 12000 | 길이 후보 (맞춤 길이 쓸 때는 SNAP 단위) |

실제 사람 커팅플랜(sheets.csv 936장) 최빈 규격: 3048×8250, 2438×6000, 2438×5600, 3048×13905, 2670×7910.
13905 처럼 운반 상한 12000 을 넘는 길이도 실데이터에 있으므로 TRANSPORT_MAX 는 절대 제한이 아니라 기본 상한이다.

## 4. 전개 판정 키워드 (UNFOLD_CLASS)

BOM PART NAME 에 아래 키워드가 들어 있으면 해당 유형으로 1차 판정. 전개구분표(unfold_classification_table.md)와
part_class_rules.md 의 정규화 규칙이 이보다 세밀하다.

| 유형 | 키워드 | 전개 |
|---|---|---|
| cylinder | SHELL, CHANNEL, L/SHELL, LARGE SHELL, SMALL SHELL, NECK, NOZZLE NECK, DAVIT | 원통 → 직사각형 L = π(ID+t) |
| cone_frustum | CONE, REDUCER, BTM.CONE, BTM CONE | 원뿔대 → 환형 부채꼴 |
| head | HEAD, ELLIP, DISH | 블랭크 원판 |
| pad_ring | REINF. PAD, REINF PAD, RE-PAD, REPAD, PAD | 평판 링 (OD/ID) |
| flat | PLATE, BAFFLE, RIB, LUG, STRIP, SCREEN, EQUATOR, BRACKET, CLIP, PARTITION, TEMPLATE, BASE, WEB, COVER, SUPPORT PLATE, TUBESHEET | 평판 윤곽 그대로 |

주의: `PAD` 키워드는 SADDLE PAD(직사각 평판)도 잡는다. 코드 순서상 pad_ring 이 flat 보다 먼저 검사되므로 SADDLE PAD 가 링으로 오판될 수 있다. size 가 `WxL` 이면 flat 으로 보정할 것 (part_class_rules.md §4).

## 5. 모델·입력 처리

| 상수 | 값 | 설명 |
|---|---|---|
| MODEL | claude-opus-5-5 | VLM 판독·관계 추론 모델 |
| MAX_TOKENS | 16000 | 응답 상한 |
| VLM_MAX_PX | 2576 px | 이미지 긴 변 상한. 이보다 크면 서버가 축소하므로 렌더 dpi 를 역산해 맞춘다 |

## 6. 경로

| 상수 | 값 |
|---|---|
| ROOT | `D:\노바투스2026` |
| DATASET | `Data/dataset` |
| TOOLKIT | `tools/dwg2png` (libredwg, unfold 엔진, cp_extract) |
| DWG2DXF | `tools/dwg2png/libredwg/dwg2dxf.exe` |
| KNOWLEDGE_DIR | `cutplan_agent/knowledge` |
| RUNS_DIR | `runs` |
