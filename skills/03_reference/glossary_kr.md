# 발표 자료 용어 메모 — Prompting vs Harness 기반 VLM Framework

덱 `API_vs_Harness_VLM_Framework_v9.pptx`(35장)와 `Harness_Engineering_기초강의.pptx`(10장)에 나오는 용어를 세 묶음으로 정리했다.
각 항목은 "뜻 → 덱에서 어떻게 쓰였나" 순서다. 2026-10-02.

---

## 1. 도면·제작 용어 (케이디엠텍 압력용기 / 현대건설기계 판금)

**문서·공정**

| 용어 | 뜻 | 덱에서 |
|---|---|---|
| 도면 (DWG / PDF) | 설계자가 그린 설계도. DWG는 캐드 원본, PDF는 그림으로만 남은 스캔본 | 입력. 한 작업 건에 9~12장 |
| GA 도면 (General Arrangement) | 장비 전체 조립도. 설계 조건표(압력·온도·부식 여유), 재질표, 노즐표가 있음 | 패드 지름 계산의 출처, 재질 확인 |
| 본체 상세도 (Detail of body) | 쉘·헤드·콘 치수, 용접선 배치도, 부품 목록표(BOM)가 있는 도면 | 판재 부품의 주 출처 |
| BOM (Bill of Material, 부품 목록표) | 도면 안의 표. 부품 번호·이름·재질·두께·수량·단위(EA/SET) | L1 `vlm_read_page(bom)` → `normalize_bom` |
| 자재목록 | BOM을 정리해 "어떤 철판 부품이 몇 개 필요한가"로 만든 목록 | 파이프라인 ②단계 |
| 전개도 | 원통·뚜껑 같은 입체 부품을 평평하게 펼친 모양의 도면 | 중간 산출물, DXF+PNG |
| 커팅플랜 (CP, cutting plan) | 철판 한 장 위에 어떤 부품 조각을 어디에 놓고 자를지 그린 배치도 | 최종 산출물, 사람 설계자 것이 정답 |
| POR (Purchase Order Request, 구매요구서) | 어떤 철판(재질·두께·폭·길이)을 몇 장 살지 적은 구매 요청서. 무게가 곧 금액 | `build_por` → `por.csv` |
| 워크오더 (WO, KDxxxxx) | 작업 건 번호. KD23002 = 2023년 2번째 건 | 실험 단위 (38건 + HCE 1건) |
| KDM / HCE | 케이디엠텍(압력용기 제작사) / 현대건설기계(판금 커버) | 두 도메인 |
| 세트 (SET) | 같은 장비를 몇 대 만드는지. BOM 수량에 세트 수를 곱해야 총 수량 | "세트 곱" 오류의 원인 |
| 발주 | 고객이 주문한 수량·조건 | HCE는 세트 수가 입력에 없음 |

**부품 이름**

| 용어 | 뜻 |
|---|---|
| 쉘 (SHELL) | 원통 몸체. 철판을 말아 만든다 |
| 헤드 (HEAD) | 원통 양끝의 둥근 뚜껑. 2:1 ELLIP = 타원형 뚜껑 |
| 콘 (CONE) | 깔때기 모양 부품. 큰 지름과 작은 지름을 잇는다 |
| 채널 (CHANNEL) | 열교환기의 짧은 원통(물이 드나드는 쪽) |
| 패드 / 보강판 (REINF. PAD) | 노즐 주위에 덧대는 도넛 모양 보강 철판 |
| 노즐 (NOZZLE) | 배관을 연결하는 구멍·짧은 관. 노즐표에 크기와 패드 정보 |
| 배플 (BAFFLE) | 열교환기 안의 칸막이판. 일부가 잘린 원판 |
| 새들 (SADDLE) | 수평 장비를 받치는 받침대 |
| 러그 (LUG) | 들어올림 고리(LIFTING LUG), 접지 고리(EARTH LUG) |
| 격벽 / 패스 파티션 (PASS PARTITION) | 채널 안을 나누는 칸막이판 |
| 튜브시트 (TUBESHEET) | 튜브 다발을 고정하는 두꺼운 원판 |
| 테스트 링 (TEST RING) | 압력 시험용 임시 원통. 커팅 대상이지만 놓치기 쉬움 |
| 임핀지먼트 판 / 명판 브래킷 / 클립 | 유체 충돌 방지판 / 명판 받침 / 보온재 고정 클립. 모두 작은 판재 |

**전개·치수 용어**

| 용어 | 뜻 | 덱에서 |
|---|---|---|
| I.D / O.D | 안지름 / 바깥지름 | 쉘은 I.D 기준, O.D면 I.D = O.D − 2t |
| t10, t12 … | 두께 10 mm, 12 mm | 재질·두께가 철판 묶음의 기준 |
| T.L (Tangent Line) | 뚜껑과 원통이 만나는 기준선 | 치수의 기준점, 모델이 뜻을 모르는 예 |
| 코스 (course) | 긴 원통을 나눈 한 마디. 코스마다 철판 한 장 | 2764.5 + 2764.5 = 쉘 5529 |
| 롱심 / 용접선 배치도 (SA-01 …) | 세로 방향 용접선 / 어디서 철판이 이어지는지 그린 도면 | 분할 수의 근거 |
| 블랭크 (blank) | 펼친 철판 조각 그 자체. 헤드 블랭크 = 뚜껑을 만들 원판 | 헤드 블랭크 Ø1296 |
| 헤드 블랭크 계수 | 뚜껑 블랭크 지름 ÷ 안지름. 경험값 1.25~1.39 | 소경에서 커짐, 보정 필요 |
| 직선부 (SF, straight flange) | 뚜껑 가장자리의 곧은 구간 | 정답 누출 사례에서 조작된 값 |
| 중립축 | 철판을 말 때 늘지도 줄지도 않는 가운데 선. 펼침 길이 = π × (I.D + t) | 현장 툴은 π×I.D, 규약 확인 |
| 부채꼴 전개 | 콘을 펼치면 나오는 부채꼴 모양 | 판폭에 따라 2~4조각 |
| 절곡 / BA / K | 판을 꺾어 접음 / 꺾인 곳의 펼친 길이(bend allowance) / 그 계산 계수(0.44) | HCE 판금 부품 |
| 3D 절곡 전개 | 여러 방향으로 꺾인 부품을 평면으로 펼치는 일. 2D 삼면도만으로는 불가 | HCE 42510 오차 57% |
| 설계치수 → 절단치수 여유 | 설계 길이에 더하는 가공 여유. 쉘 길이 +23~35 mm, 배플 지름 +10 | 지식 파일 split_and_margin |

**네스팅·구매 용어**

| 용어 | 뜻 | 덱에서 |
|---|---|---|
| 네스팅 (nesting) | 철판 위에 조각을 배치하는 일 | L3 `nest_group / nest_all` |
| 활용률 | 철판 면적 중 실제 조각이 차지한 비율 | 사람 79% vs 우리 66% |
| bbox (bounding box) | 조각을 감싸는 네모 테두리. 우리 배치는 이 네모 기준 | 활용률도 bbox 기준 |
| shelf 배치 | 책꽂이 선반처럼 줄 단위로 채우는 단순 배치 방식 | 현재 엔진 |
| NFP (No-Fit Polygon) | 모양대로 맞물리게 배치하는 고급 방식 | 미구현, 개선 항목 |
| 커팅 여유 (kerf) | 조각 사이 최소 간격. 가스 20 mm, 플라즈마 10 mm | 검사 항목 |
| 운송 상한 | 철판 최대 크기 12000 × 3050 mm | 검사 항목 |
| 표준폭 / 맞춤 규격 | 1219·1524·2438·3048 같은 기성 폭 / 주문 제작 치수 | 길이는 10 mm 단위 |
| 재고확인 | 작은 묶음은 새 철판 대신 재고·자투리로 처리하라는 표시 | POR 비고 |
| gross kg | 철판 무게(= 두께 × 폭 × 길이 × 7.85e-6). 조각 무게가 아니라 산 철판 전체 무게 | kg 비율의 기준 |
| 커팅플랜 프로그램 | 현장에서 쓰는 배치 소프트웨어(TruTops, KDM 배치툴) | 아직 연동 없음 |

**재질 표기**

| 표기 | 뜻 |
|---|---|
| A516-70 / SA516-70(N) | 압력용기용 탄소강 후판. SA = ASME 규격 접두 |
| A283-C / A516-60 | 일반 구조용·저강도 탄소강 |
| A240-304(L) / 316L / S32205 | 스테인리스 판 (304·316 계열, S32205 = 듀플렉스) |
| SS400 / St37 | 일반 구조용 강(한국·독일 표기). HCE 판금 |
| 2438 × 9150 - 1 SH'T | 폭 × 길이 × 장수(sheet) — POR 행 형식 |

---

## 2. AI 구조·Skill 용어 (Harness Framework)

**접근 방식**

| 용어 | 뜻 | 덱에서 |
|---|---|---|
| Prompting | 도면 그림과 지시문을 한 번 넣고 답 문장을 받는 방식 | 접근 A |
| Harness | 모델 바깥에 기능·작업 상태·검사기·사람 확인을 붙인 틀. 모델은 그대로 | 접근 B |
| VLM / MLLM / LLM | 그림+글을 이해하는 모델 / 같은 뜻(multimodal) / 글만 다루는 모델 | claude-opus-5-5 |
| OCR | 그림 속 글자를 읽어 텍스트로 바꾸는 기술. "무엇이 어디 적혀 있나"까지 | L1 경계 |
| Multi-agent VLM Framework | 역할을 나눈 여러 모델(에이전트)이 공유 작업 상태를 두고 협업하는 구조 | 다음 단계 |

**구조 요소**

| 용어 | 뜻 | 덱에서 |
|---|---|---|
| Skill / tool | 모델이 호출하는 기능 하나 (파일 변환, 표 읽기, 펼치기 …). 25개 | 8장 |
| L1 인식 | 글자·숫자·표를 꺼내는 단계. 코드 + 모델 | `ingest_drawing`, `dxf_read_text`, `vlm_read_page`, `normalize_bom` |
| L2 관계·의미 | "이 숫자가 어느 부품의 어떤 치수인가"를 판단하는 단계. 모델이 유일하게 판단 | `classify_drawing`, `extract_design_data`, `extract_part_model`, `detect_split_lines`, `resolve_missing_spec`, `set_part_spec`, `load_domain_prompt` |
| L3 계산·로직 | 펼치기·나누기·배치·무게를 공식대로 계산하는 단계. 모델 호출 없음 | `unfold_part`, `split_to_pieces`, `nest_group/nest_all`, `write_cutting_plan_dxf`, `build_por` |
| L4 검증·HITL | 검사하고 사람에게 묻는 단계 | `verify_*`, `compare_with_gt`, `ask_human`, `confidence_report` |
| Orchestrator | 어떤 기능을 언제 쓸지 정하는 지휘 역할의 모델. `tool_runner`로 돌림 | system.md 절차 ①~⑥ |
| system.md | 지휘 모델에 주는 지시문. 원칙 5개 + 절차 6단계 | 10~13장 발췌 |
| 지식 파일 (load_domain_prompt) | 도면 표기 규칙·전개 규칙·분할 여유·재질 표기·네스팅 규칙·POR 형식 등 7개 문서 | 평가 정답은 넣지 않음 |
| JobState (state.json) | 작업 상태 저장소. 도면·BOM·부품·전개·조각·철판·POR·검증·HITL 전부 | 재개·재실행 |
| Trajectory (trajectory.json) | 기능 호출을 순서대로 남긴 실행 기록 (step·skill·args·result) | 270회, 누출 발견 |
| PartSpec | 부품 하나의 3D 파라미터 묶음 (유형, 안지름, 코스, 두께, 수량, 확신도, 근거) | L2의 출력 |
| part_type | 부품 유형: cylinder(원통) / cone_frustum(콘) / head(뚜껑) / pad_ring(보강판) / bent_sheet(절곡) / flat(평판) / unknown | 틀리면 블랭크가 틀림 |
| confidence (high / medium / estimated / unreadable) | 확신도. estimated = 추정값, 사람 확인 대상 | HITL 트리거 |
| evidence / notes | 어느 도면의 어느 치수를 썼는지 근거 / 비고 | 추적용 |
| structured output / pydantic 스키마 | 모델 답을 정해진 표 형식(JSON)으로 강제하는 방법 / 그 형식 정의 | `BomTable`, `PartModelOut` |
| HITL (Human-in-the-loop) | 사람이 중간에 확인하는 것. H1 펼치기 직전, H2 자재목록 후, H3 배치 후, H4 구매요구서 전 | 정책 ask / auto |
| 평가 모드 (eval_mode) | 사람 질문에 기본값으로 자동 응답하고 기록만 남기는 실행 방식 | 실험용 |
| 검사기 (verifier) | 코드로 하는 검사. 겹침·간격·운송·무게·정답 대비 | 품질 기준 |
| spec.json | 수동 판독에서 사람(Claude 세션)이 직접 쓴 PartSpec 목록 | L2를 손으로 대신 |

**자주 나오는 skill 이름**

| skill | 하는 일 |
|---|---|
| `ingest_drawing` | DWG→DXF→PNG, PDF→PNG 변환 |
| `dxf_read_text` | 캐드 파일의 글자(TEXT/MTEXT)·치수(DIM)를 좌표와 함께 꺼냄 |
| `vlm_read_page` | 모델이 제목란·BOM·설계조건표를 정해진 형식으로 옮김 |
| `normalize_bom` | 재질·두께·수량·세트·전개 여부를 정리 |
| `classify_drawing` | 도면 종류 판정 (GA/본체/노즐/새들 …) |
| `extract_design_data` | GA의 설계조건·재질표·노즐표 읽기 |
| `extract_part_model` | BOM 항목 하나를 3D 파라미터(PartSpec)로 |
| `set_part_spec` | 파라미터를 직접 입력 (사람 / 수동 판독) |
| `resolve_missing_spec` | 두께만 있는 보강판 등을 노즐표·관례로 보충, estimated 표시 |
| `unfold_part` | 펼치기 (원통 π(I.D+t), 콘, 뚜껑, 보강판, 절곡) |
| `split_to_pieces` | 판폭·용접선 기준으로 나누고 여유를 더함 |
| `nest_group / nest_all` | 재질·두께 묶음별 / 전체 배치 |
| `write_cutting_plan_dxf` | 커팅플랜 DXF+PNG 출력 |
| `build_por` | 철판별 구매 행 + por.csv |
| `verify_part_spec / verify_weight_vs_bom / verify_nesting` | 범위 검사 / 무게 대조 / 겹침·간격·운송·미배치 검사 |
| `compare_with_gt` | 사람 커팅플랜(정답)과 비교 |
| `ask_human` | H1~H4에서 질문 |
| `confidence_report` | 확신 낮은 항목 요약 |

---

## 3. 실험·평가·데이터 용어

| 용어 | 뜻 | 덱에서 |
|---|---|---|
| test_data | 작업 건 39개를 입력 도면 / 정답 전개 / 정답 커팅플랜 세 폴더로 정리한 평가 자료 | `input_drawings`, `output_unfold`, `output_cutting_plan` |
| 정답 (GT, ground truth) | 사람 설계자가 실제로 만든 커팅플랜·전개도 | 비교 기준 |
| sheets.csv / parts.csv / part_tags.csv | 정답 커팅플랜에서 뽑은 철판 목록 / 조각 목록 / 설계자가 붙인 부품 번호 | 비교 도구 입력 |
| Oracle 실험 (E1 / E2) | 정답 조각을 그대로 넣어 계산·배치(L3)만 평가한 실험. E1 = KDM 38건, E2 = HCE | "조각이 정답으로 주어진 조건" |
| VLM 에이전트 실행 (E6) | 모델이 25개 기능을 직접 호출해 끝까지 간 실행. KD23002 1건 | 270회, 22.4분 |
| 수동 판독 (E5 / E7) | Claude 세션이 도면을 읽어 spec.json을 쓰고, 나머지는 같은 L3·L4 코드. 6건 | Prompting이 아님, "사람이 L2를 맡은 Harness" |
| kg 비율 | 우리 철판 무게 ÷ 사람 철판 무게. 1.0이 같음, 1.12면 12% 더 삼 | 핵심 지표 |
| 판 수 비율 | 우리 철판 장 수 ÷ 사람 장 수 | 보조 지표 |
| feasibility | 겹침 0, 간격 위반 0, 운송 초과 0, 미배치 0인가 | 배치 검증 ✓ |
| 태그 매칭 / 5% 이내 / 수량 일치 | 설계자 부품 번호와 우리 부품을 짝지은 수 / 치수 오차 5% 이내 수 / 수량이 같은 수 | 부품 추출 현황 |
| 성공 등급 | 정답 자료가 완비되어 비교 가능한 작업 건 | KD23022 등 |
| 정답 누출 (reward hacking) | 정답 수치가 지식 자료에 적혀 있어 모델이 그 값을 맞추러 간 문제 | 실패 모드 1 |
| 세트 곱 | BOM 수량 × 세트 수. 두 번 곱하면 수량이 2배 | 실패 모드 3 |
| 소량 그룹 새 판 | 10~25 kg 작은 묶음마다 새 철판을 잡는 문제 | 실패 모드 4 |
| 꼬리 부품 | 보강판·노즐·격벽 등 수는 많고 치수가 도면에 없는 작은 부품들 | 치수 일치 18% |
| 래스터 / 벡터 | 그림으로만 된 파일(PDF 스캔) / 선·글자가 데이터로 있는 파일(DWG·DXF) | 벡터면 숫자를 '꺼냄' |
| 타일 (tile) | 큰 도면을 5000px 급으로 잘라 모델에 넣는 조각 그림 | 래스터 판독 |
| 픽셀 → 토큰 | 그림이 모델 입력으로 압축되는 과정. 작은 글씨가 뭉개짐 | 차이 ① 그림 |
| DXF 텍스트 좌표 (TEXT/MTEXT/DIM) | 캐드 파일 안의 글자·치수 항목과 그 위치 | 810개·55개 |
| compare 폴더 (cp_compare / unfold_compare) | 커팅플랜 비교표 / 전개도 비교표 (md·csv·png) | 자동 누적 |
| aggregate | 여러 실행의 비교표를 한 표로 모으는 도구 | E7 표 |
| TruTops | 현대건설기계 쪽 커팅플랜 프로그램(레이저) 산출 파일(TAF) | HCE 정답 |
| KDM 배치툴 | 케이디엠텍이 만든 브라우저용 배치 프로토타입 | 8168 vs 8199.6 비교 |
| Florence-2 / Design-to-Plan / MADP | 과제 제기 때 검토한 기존 접근: 소형 VLM 파인튜닝 / 3D CAD + LLM / 멀티에이전트 | 4장 하단 |
