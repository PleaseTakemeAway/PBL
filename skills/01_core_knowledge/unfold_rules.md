# 전개(development) 규칙 — 계산은 L3 코드가 한다. 여기서는 파라미터를 어떻게 읽을지만 정한다.

공식과 전개에 필요한 수치의 원본은 회사 담당자에게 받은 계산 문서 `shell_cone_head_unfold.md` 다 (2026-10-22). 이 문서와 다르면 그 문서를 따른다. 모든 전개는 평균지름 Dm = ID + t 기준이다.

## 전개 판정표 (툴킷 전개구분표, KD 도면 67개 라벨 779건 분류)
| 부품 | 전개 | 전개 형상 | 비고 |
|---|---|---|---|
| SHELL / CHANNEL / L.SHELL | 필요 | 원통 → 직사각형 L = π(ID+t), H = 코스 길이 | 44건 역산 검증: 중립축 = 평균지름(K=0.5) |
| CONE / REDUCER | 필요 | 원뿔대 → 환형 부채꼴 | 부채꼴이 철판에 안 들어가면 2~4분할 (코드가 판 크기에 맞춰 나눈다) |
| ECCENTRIC CONE / ECC. REDUCER | 필요 | 사원추 → 삼각분할 전개 (부채꼴이 아니다) | 한쪽 면이 수직이면 편심량 e = (D1 − D2)/2. 이음은 가장 짧은 모선(수직면) 쪽 |
| NOZZLE NECK (판 롤링) | 필요 | 원통 + 쉘 상관선 | 파이프 넥이면 구매품, 전개 없음 |
| HEAD (2:1 ELLIP, HEMI, TORISPH F&D) | 조건부 | 블랭크 원판 지름 | 성형품이지만 원판은 철판에서 잘라 커팅플랜에 들어간다. 원판 = 형식별 약산식 + 2·SF + 트림 여유 (계산 문서 2·3절). 원판이 판 폭보다 크면 분할. 정답 치수를 맞추려고 SF 를 조작하지 말 것 |
| REINF. PAD / RE-PAD | 조건부 | 평판 링(OD/ID) | 쉘 곡률로 성형하지만 블랭크는 평판 링 |
| BAFFLE, RIB, LUG, BASE/WEB PLATE, PARTITION, STRIP, SCREEN, BRACKET | 불필요 | 평판 윤곽 그대로 | 전체의 약 71% |
| 프레스 성형품 (NOTE 에 "성형해석 DATA 제출") | 불가 | FEA 필요 | 굽힘여유 공식 성립 안 함 |

## 파라미터 읽기 규칙
- cylinder: `inner_dia` 는 **안지름**. OD 로 적혀 있으면 ID = OD − 2t, 평균지름이면 ID = Dm − t 로 환산하고 notes 에 기록. `length` 는 코스 길이 (TL 기준 전체 길이를 코스 수로 나눈 것이 아니라 도면의 코스별 치수).
- cone_frustum: 큰쪽/작은쪽 **안지름** 과 **수직 높이**. 모선 길이만 있으면 높이로 환산. 반정각 α 만 있으면 H = (D1 − D2) / (2 tan α).
- eccentric_cone: cone_frustum 의 값에 더해 두 원 중심 거리 **편심량 e** (`eccentricity`). 한쪽 면이 수직(FOB·FOT)이면 0 으로 둔다 (코드가 e = (D1 − D2)/2 로 계산).
- head: ID, t, 종류(2:1 ELLIP / TORISPHERICAL / HEMI / FLAT FLANGED), 직선부 SF (T.L 에서 끝단까지). 접시형은 내측 너클 반경 IKR (`knuckle_radius`)과 크라운 반경 CR 도 읽는다. 성형 후 최소 두께(MIN. TH'K AFTER FORMING)는 notes 에 적는다. 블랭크 = 코드가 계산.
- pad_ring: OD, ID. BOM 이 `t13` 만 주면 노즐표의 노즐 OD 와 보강 계산이 필요 → `resolve_missing_spec` 또는 HITL(H2).
- bent_sheet (판금): 외측 구간 길이, 굽힘각, **내측** R. `len(segments) == len(bend_angles)+1`.
- flat: 치수로 좌표를 계산한 윤곽. 눈대중 금지.

## 공식 (참고, v2 코드 cutplan_agent/skills/l3_rules.py 에 구현됨)
- 원통: L = π × (ID + t). ID/t < 20 이면 후육 경고.
- 원뿔대: D1m = ID1 + t, D2m = ID2 + t, s = √(h² + ((D1m−D2m)/2)²), R1 = s·D1m/(D1m−D2m) = D1m/(2 sin α), R2 = R1 − s, θ = π·D1m/R1 = 360°·sin α.
- 편심 콘: Ha = H·D1m/(D1m−D2m), Xa = e·D1m/(D1m−D2m). 대경 원주 36 등분, L1(φ) = √((r1 cos φ − Xa)² + (r1 sin φ)² + Ha²), L2 = L1·D2m/D1m, 이웃 모선 사이 각 δ = acos((Li² + Li+1² − c²)/(2 Li Li+1)), c = D1m sin(180°/n).
- 절곡: BA = θ(R + K·t), K = 0.33 (R/t<1) / 0.40 (1~3) / 0.50 (≥3). 전개 = Σ(외측구간 − setback) + ΣBA, setback = (R+t)·tan(θ/2).
- 헤드 블랭크 (Dm = ID + t, OD = ID + 2t, 트림 30 mm, 10 mm 반올림): 2:1 반타원형 1.2·Dm + 2·SF, 반구형 1.414·Dm + 2·SF, 접시형 OD + OD/24 + 2·SF + (2/3)·IKR, 평판형 플랜지 Dm + 2·SF + (π/2 − 1)·IKR.
- 중량(kg) = 가로(m) × 세로(m) × 두께(mm) × 7.85 (탄소강), 스테인리스는 7.93.

## 자기검증 (출력 전 확인)
1. part_type 에 필요한 필드가 모두 채워졌는가. 0 이 있으면 전개 불가.
2. ID 에 OD 를 넣지 않았는가. cone_height 에 모선을 넣지 않았는가.
3. 두께가 BOM 재질 표기와 일치하는가.
4. 확신 없으면 값을 지어내지 말고 confidence 를 낮추고 notes 에 적어라. 지름 10mm 오차 = 원주 31mm 오차 = 판 폐기.
