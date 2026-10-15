# 전개(development) 규칙 — 계산은 L3 코드가 한다. 여기서는 파라미터를 어떻게 읽을지만 정한다.

## 전개 판정표 (툴킷 전개구분표, KD 도면 67개 라벨 779건 분류)
| 부품 | 전개 | 전개 형상 | 비고 |
|---|---|---|---|
| SHELL / CHANNEL / L.SHELL | 필요 | 원통 → 직사각형 L = π(ID+t), H = 코스 길이 | 44건 역산 검증: 중립축 = 평균지름(K=0.5) |
| CONE / REDUCER | 필요 | 원뿔대 → 환형 부채꼴 | θ>360° 면 분할 |
| NOZZLE NECK (판 롤링) | 필요 | 원통 + 쉘 상관선 | 파이프 넥이면 구매품, 전개 없음 |
| HEAD (2:1 ELLIP, TORISPH) | 조건부 | 블랭크 원판 지름 | 성형품. 블랭크 ≈ 1.25~1.30×ID (실측 역산 2건, 경험계수). 직선부(SF)·두께 보정은 제작처 표준을 따른다. 정답 치수를 맞추려고 SF 를 조작하지 말 것 |
| REINF. PAD / RE-PAD | 조건부 | 평판 링(OD/ID) | 쉘 곡률로 성형하지만 블랭크는 평판 링 |
| BAFFLE, RIB, LUG, BASE/WEB PLATE, PARTITION, STRIP, SCREEN, BRACKET | 불필요 | 평판 윤곽 그대로 | 전체의 약 71% |
| 프레스 성형품 (NOTE 에 "성형해석 DATA 제출") | 불가 | FEA 필요 | 굽힘여유 공식 성립 안 함 |

## 파라미터 읽기 규칙
- cylinder: `inner_dia` 는 **안지름**. OD 로 적혀 있으면 ID = OD − 2t, 평균지름이면 ID = Dm − t 로 환산하고 notes 에 기록. `length` 는 코스 길이 (TL 기준 전체 길이를 코스 수로 나눈 것이 아니라 도면의 코스별 치수).
- cone_frustum: 큰쪽/작은쪽 **안지름** 과 **수직 높이**. 모선 길이만 있으면 높이로 환산.
- head: ID, t, 종류(2:1 ELLIP / TORISPHERICAL / HEMI), 직선부 SF. 블랭크 = 코드가 계산.
- pad_ring: OD, ID. BOM 이 `t13` 만 주면 노즐표의 노즐 OD 와 보강 계산이 필요 → `resolve_missing_spec` 또는 HITL(H2).
- bent_sheet (판금): 외측 구간 길이, 굽힘각, **내측** R. `len(segments) == len(bend_angles)+1`.
- flat: 치수로 좌표를 계산한 윤곽. 눈대중 금지.

## 공식 (참고, 코드에 구현됨)
- 원통: L = π × (ID + t). ID/t < 20 이면 후육 경고.
- 원뿔대: D1m = ID1 + t, D2m = ID2 + t, s = √(h² + ((D1m−D2m)/2)²), R1 = s·D1m/(D1m−D2m), R2 = R1 − s, θ = π·D1m/R1.
- 절곡: BA = θ(R + K·t), K = 0.33 (R/t<1) / 0.40 (1~3) / 0.50 (≥3). 전개 = Σ(외측구간 − setback) + ΣBA, setback = (R+t)·tan(θ/2).
- 헤드 블랭크(2:1 ellip): D_blank ≈ k × ID + 2 × SF_extra, k = 1.25~1.30. 데이터로 보정 예정.

## 자기검증 (출력 전 확인)
1. part_type 에 필요한 필드가 모두 채워졌는가. 0 이 있으면 전개 불가.
2. ID 에 OD 를 넣지 않았는가. cone_height 에 모선을 넣지 않았는가.
3. 두께가 BOM 재질 표기와 일치하는가.
4. 확신 없으면 값을 지어내지 말고 confidence 를 낮추고 notes 에 적어라. 지름 10mm 오차 = 원주 31mm 오차 = 판 폐기.
