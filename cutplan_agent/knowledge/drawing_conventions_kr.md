# KDM 압력용기·열교환기 도면 표기 규칙 (판독 시 반드시 적용)

## 도면 종류 (한 워크오더 = 여러 장)
- GENERAL ASSEMBLY (GA): 설계조건표(DESIGN DATA), 재질표(MATERIAL SPECIFICATION), 노즐표(NOZZLE LIST), 전체 치수, 참조도면 목록. **판재 부품 치수는 없다.**
- DETAIL OF BODY (& SUPPORT LEG / SADDLE): 쉘 코스, 헤드, 콘, 용접선 배치(WELDING SEAM PLAN / ORIENTATION), 러그·패드 상세, **BOM 표**. 판재 부품의 주 출처.
- DETAIL OF TUBE BUNDLE: 튜브시트, 배플, 타이로드. 배플·튜브시트는 평판.
- DETAIL OF SUPPORT SADDLE: 베이스·웹·리브·웨어플레이트. 전부 평판.
- DETAIL OF NOZZLE: 노즐 넥(파이프 또는 롤링 판), 보강패드(REINF. PAD). BOM 에 두께만 있고 지름이 없는 경우가 많다.
- DETAIL OF MANHOLE: 데빗(파이프 굽힘), 엔드플레이트, 힌지. 파이프 길이는 R·각도·직선구간으로 계산해야 한다.
- PLATFORM & LADDER, NAMEPLATE, TEST RING: 커팅플랜 대상이 아니거나 소형. 우선순위 낮음.

## BOM 표 읽기
- 열: PART NO | PART NAME | MATERIAL | Q'TY | UNIT | SIZE/DIMENSION. SIZE 는 `t10`, `t12`, `Ø21.3x25L`, `H350x350x12x19`, `2800x2949` 등 **형식이 자유롭다**.
- 번호 체계 `8-1`, `8-2` 는 "아이템 8의 세부 1, 2". 도면 풍선(○ 안 숫자)과 짝이 맞는다.
- 두께만 있는 행(`t10`)은 지름·길이를 **도면 뷰에서** 찾아야 한다. 뷰에 없으면 GA 데이터시트로 계산하거나 HITL.
- 수량 단위가 `EA`, `SET`, `SH'T` 로 섞여 있다. `1 SET` 이 2개 이상 부품을 뜻할 수 있으니 PART NAME 과 도면 수량 접두(`2-Ø13`, `4-SOCKET`) 로 교차 확인한다.
- 단위가 윗첨자로 붙거나 표선에 텍스트가 붙어 있어 OCR 이 열을 섞기 쉽다. 열 경계는 표선 기준으로 재정렬한다.
- 재질 표기 `SA516-70` 과 `A516-70` 은 같은 규격(ASME/ASTM). `SA516-70N` 은 노멀라이징 조건.

## 치수 표기
- `T.L` = Tangent Line. 헤드 직선부와 쉘의 경계. TL~TL 길이가 쉘 코스 길이 합이다. TL 표시와 값이 떨어져 적혀 있을 때가 많다.
- `I.D 2600`, `SHELL I.D`, `PTFE LINING I.D` 처럼 **어느 지름인지** 접두를 확인한다. 라이닝 지름은 쉘 지름이 아니다.
- `2:1 ELLIP. HEADS / USED THK t10 / MIN. THK t8.8 (AFTER FORMING)`: 헤드는 성형품. 블랭크 지름은 별도 계산.
- `2-Ø13`, `4-Ø41 HOLES` : 개수-지름. `R5`, `R100` : 반지름(굽힘 R 또는 모서리 R, 문맥으로 구분).
- `△ 숫자` (삼각형 안 숫자) 는 개정 기호. 치수가 아니다.
- 각도 뷰 `WELDING SEAM ORIENTATION (VIEW "X"-"X")`: 용접선(SA-01, SB-04 …)의 원주 방향 위치. 쉘·콘·헤드가 몇 조각으로 나뉘는지 여기서 읽는다.
- 용접선 명명: `SA-xx` 쉘 롱심/원주심, `SB-xx` 콘·헤드 심, `HA-xx` 헤드 심, `CA/CB` 채널. 조각 이름을 용접선으로 부른다 (예: 조각 SA-01 = 쉘 1코스).

## 척도·단위
- 치수는 mm. 도면 척도(1/22 등)는 무시하고 표기 숫자만 쓴다. 눈대중 금지.
- 중량은 kg. BOM 의 WEIGHT 는 부품 1개 중량 (판재 전개 면적 × t × 7.85e-6 으로 역검증 가능).
