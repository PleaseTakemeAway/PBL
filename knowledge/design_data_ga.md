# GA 도면 DESIGN DATA 표 — 무엇을 읽고 어디에 쓰는가

GA(GENERAL ASSEMBLY) 우상단 표. 열이 SHELL SIDE / TUBE SIDE 로 나뉜다.

| 항목 | 예 (KD24032) | 용도 |
|---|---|---|
| CODE | ASME SEC.VIII DIV.1 2023 + TEMA | 계산 규칙 |
| DESIGN PRESSURE (kg/cm²) | 7.0 / 10.5 | 패드·넥 두께 계산, 쉘 소요두께 |
| DESIGN TEMPERATURE (℃) | 343 / 295 | 허용응력 |
| CORR. ALLOW. (mm) | 3.0 / 3.0 | 소요두께에 가산 |
| JOINT EFFICIENCY | 0.85 / 1.0 | 쉘 소요두께 |
| RADIOGRAPHY | SPOT / FULL | |
| M.D.M.T (℃) | −18 | 재질 N 조건 판단 |
| WEIGHT (EMPTY/OPERATING/BUNDLE) | | BOM 중량 cross-check |

MATERIAL SPECIFICATION 표: SHELL / HEAD / CHANNEL / TUBESHEET / BAFFLE / NOZZLE FLANGE / REINF. PAD 의 재질. BOM 에 재질이 빠져 있을 때 여기서 보충.
NOZZLE LIST 표: 노즐 마크(S1, T1, N2 …), 수량, SIZE(인치), 플랜지 등급, **REINF. PAD 유무와 OD**. 보강패드 지름의 1차 출처.

KDM 발표자료 결론: 노즐 보강패드는 BOM 에 `t13` 두께만 적히고 지름이 없다. 실제 치수는 **쉘의 압력/온도/부식여유** 로 계산되며 그 값은 GA 데이터시트에만 있다. 따라서
1. NOZZLE LIST 에 패드 OD 가 있으면 그것을 쓴다.
2. 없으면 관례(패드 OD ≈ 2 × 노즐 OD, ID = 노즐 OD + 간격) 로 추정하고 confidence=estimated, HITL H2 로 넘긴다.
3. 강도계산서(CAL, 'NOZZLE' 장) 가 있으면 그 값이 최종.
