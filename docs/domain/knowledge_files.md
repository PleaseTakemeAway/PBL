# skills — 커팅플랜 생성용 도메인 지식 모음

> **위치 안내 (2026-10-22).** 이 문서는 원래 `skills/README.md` 였다. 사람이 읽는 문서를 `docs/` 로 모으면서 옮겼고, 아래 03_reference 의 문서는 지금 [../agent/](../agent/) (`skill_agent_framework.md`), [../data/](../data/) (`dataset_structure.md`, `part_class_rules.md`), 이 폴더(`glossary_kr.md`, `unfold_pipeline_tools.md`, `unfold_classification_table.md`)에 있다. 01_core_knowledge 와 02_prompts 는 코드가 읽으므로 `skills/` 에 그대로 있다.

프로젝트 곳곳에 흩어져 있던 도메인 지식 md 파일을 2026-10-18 에 한 곳에 **복사**한 것이다. 원본은 그대로 두었으므로
원본을 고치면 여기도 다시 복사해야 한다 (아래 "원본" 열 참조).

## 01_core_knowledge — 에이전트가 단계별로 읽는 규칙 (원본: `cutplan_agent/knowledge/`, `cutplan_agent/agent/`)

| 파일 | 내용 | 읽는 시점 |
|---|---|---|
| 00_system_role_and_procedure.md | 역할(KDM 생산기술), 원칙 5개, 절차 ①도면 읽기 ~ ⑥검증 | 항상 (시스템 프롬프트) |
| drawing_conventions_kr.md | 도면 종류별 내용(GA 에는 판재 치수 없음, BODY 에 BOM), BOM 열 읽기, 품번과 커팅플랜 부품 라벨의 대응, 판재가 아닌 행(형강·파이프·볼트·와셔), 치수 표기(T.L, I.D, `2-Ø13`, △) | BOM 읽기 전 |
| unfold_rules.md | 전개 판정표, 파라미터 읽기 규칙(안지름 기준), 원통·원뿔·절곡 공식 | 부품 유형 결정 전 |
| split_and_margin.md | 분할 이유(운반 상한 12000×3050, 용접선), 쉘·헤드·콘 분할 규칙, 커팅 여유(가스 20), 표준폭 | 네스팅 전 |
| nesting_rules.md | 그룹 키(재질, 두께), 회전, 판 크기 선택, 목표 지표, 판재·부품 라벨 형식 | 네스팅 전 |
| material_mapping.md | 재질 정규화(SA516-70 = A516-70, N 유지, SS400 ↔ St37, 클래드), 판재 여부 판정 | BOM 정규화 |
| design_data_ga.md | GA DESIGN DATA·MATERIAL SPEC·NOZZLE LIST 용도, 보강패드 지름 결정 순서 | GA 읽을 때 |
| por_format.md | POR 열 구조, 판재 행 예, 중량 t×W×L×7.85e-6, 품명 규칙 | POR 작성 전 |
| shell_cone_head_unfold.md | (2026-10-23 추가) 회사 담당자에게 받은 쉘·콘·헤드 전개 계산 기준. 원문은 녹음을 AI 가 정리한 대화체 문서이고 (b399b4d), 같은 날 내용을 빼지 않고 부품별 기준 문서로 다시 썼다. 평균지름 원칙, 쉘, 동심·편심 콘, 헤드 형식별 원판 식, 부품별 필요 수치, 중량 7.85·7.93, 받은 커팅플랜과의 대조와 확인할 식(7절). unfold_rules.md 와 v2 L3 식의 원본 | v2: `load_domain_prompt` 로 필요할 때. v3 단계는 읽지 않는다 |

숫자 상수(커팅여유, 운반상한, 표준폭, 전개판정 키워드)는 md 가 아니라 `cutplan_agent/config.py` 에 있다.

## 02_prompts — VLM 도면 판독 프롬프트 (원본: `tools/dwg2png/vlm/prompts/`)

| 파일 | 내용 |
|---|---|
| unfold_extract.md | "따라 그리지 말고 형상을 읽어라". part_type 분류표와 유형별 추출 파라미터, confidence 규칙 |
| dxf_extract.md | 스캔 도면 → 기하·표제란 JSON. 좌표계(mm, 좌하단 원점), 척도 무시하고 치수값 사용 |

## 03_reference — 분류표·설계 문서·용어집

| 파일 | 원본 | 내용 |
|---|---|---|
| unfold_classification_table.md | tools/dwg2png/전개구분표.md | KD 도면 67개 라벨 779건을 14계열로 분류: 전개 필요 여부·형상 |
| part_class_rules.md | Data/part_class_dataset/class_rules.md | part_name 정규화 → cylinder/cone/head/ring/flat 결정 규칙, size 파싱, 품질 플래그 |
| skill_agent_framework.md | design/skill_agent_framework.md | L1~L4 skill 프레임워크 설계, KDM 압력용기 vs HCE 판금 도메인 차이, verifier=reward |
| glossary_kr.md | Week/용어_메모.md | 도면·제작 용어(GA, BOM, 전개도, CP, POR, SET), 부품 이름, VLM/하네스 용어 |
| dataset_structure.md | Data/dataset/README.md | 데이터셋 구조, Drive 폴더별 역할표, 사용 우선순위, unfold match 주의 |
| unfold_pipeline_tools.md | tools/dwg2png/README.md | DWG/PDF/이미지 → 전개도 추출 플로우와 스크립트 역할 |

## 04_reading_records — 사람 판독 기록·실험 보고 (원본: `runs/`)

| 파일 | 내용 |
|---|---|
| experiment_report.md | 무엇이 검증됐고(네스팅, 원통 전개 공식, POR 중량) 무엇이 안 됐는지, E1/E2 수치 |
| reading_sheet_KD23015 / KD23022 / KD23031 / KD24023 / KD24053.md | 도면별 세트 수, BOM 판재 판정, 치수 후보(I.D/O.D/Ø), 용접선, 헤드/콘/TL 문구. 사람이 어떤 단서로 읽는지의 기록 |

## md 가 아니라 여기 없는 지식

- `KDMTECH_발표자료_통합.pptx` (루트, 주차별_슬라이드/ 동일 파일): KDM 4계층 정의, 패드 치수는 GA 데이터시트에서 계산된다는 결론
- `cutplan_agent/config.py`: 수치 상수
- `tools/dwg2png/전개구분표.csv`: 위 분류표의 CSV 판
- `tools/dwg2png/SCORECARD.txt`, `VALIDATION.txt`: CP 추출 품질·원통 전개 공식 검증 기록
