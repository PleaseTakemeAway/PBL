# v2 워크오더 에이전트: skill 과 검증 기록

`cutplan_agent/` 의 `agent/`, `skills/`, `eval/` 가 이루는 v2 에이전트의 skill 목록, smoke test 기록, 다음 단계다. 실행 순서는 [../execution_flow.md](../execution_flow.md) 2절, 설계 의도는 [skill_agent_framework.md](skill_agent_framework.md) 를 본다.

KDM 발표자료(`주차별_슬라이드/KDMTECH_발표자료_통합.pptx`, 2026-08-03)의 4계층 구분을 skill 분류의 뼈대로 썼다.
"OCR 은 무엇이 어디 적혀 있나까지. 무엇을 의미하고 무엇과 이어지나는 OCR 의 일이 아니다." — 이 경계가 L1 / L2 의 경계다.

## 1. Skill 분류 (25개 tool)

| 계층 | KDM 정의 | skill | 구현 | 비고 |
|---|---|---|---|---|
| **L1 인식** | OCR: 문자·위치·표 구조 → JSON | `ingest_drawing` DWG→DXF→PNG / PDF→PNG | ✅ 동작 | libredwg `dwg2dxf` + ezdxf 렌더 + PyMuPDF |
| | | `dxf_read_text` 벡터 텍스트·치수 좌표 추출 | ✅ 동작 | 정확한 숫자의 1차 출처. VLM 판독값과 교차검증 |
| | | `vlm_read_page(what=title_block/bom/design_data/dims/notes)` | 🔑 API 필요 | Claude structured output (pydantic 스키마) |
| | | `normalize_bom` 재질·두께·수량·단위·전개판정 | ✅ 동작 | 정규식 + 전개구분표 키워드 |
| **L2 관계·의미** | 심볼·연결관계·의미 매핑 (VLM 추론의 본체) | `classify_drawing` GA/BODY/NOZZLE/SADDLE/… | 🔑 | |
| | | `extract_design_data` GA 설계조건·재질표·노즐표 | 🔑 | 패드 치수 계산의 출처 (발표자료 10쪽 결론) |
| | | `extract_part_model` BOM 항목 → 3D 파라미터(PartSpec) | 🔑 | `skills/02_prompts/unfold_extract.md` 프롬프트. "따라 그리지 말고 형상을 읽어라" |
| | | `set_part_spec` 파라미터 직접 입력 | ✅ | KDM 접근 B(조각+스펙 입력) / HITL 경로 |
| | | `detect_split_lines` 용접선 배치도 → 코스·롱심 (RQ1) | 🔑 | |
| | | `resolve_missing_spec` 두께만 있는 패드 → 노즐표/관례 | ✅ | 추정값은 confidence=estimated → H2 |
| | | `load_domain_prompt(topic)` 도메인 지식 7종 | ✅ | `knowledge/*.md`. 언제 불러오는지도 정책의 일부 |
| **L3 계산·로직** | 규칙엔진 (검증 완료) | `unfold_part` 원통·원뿔·절곡·평판·헤드·패드 | ✅ | 절곡·평판은 `cutplan_agent/unfold.py` (툴킷에서 이전, 원통 공식 44건 역산 검증) + 헤드 블랭크·패드 링 추가 |
| | | `split_to_pieces` 판폭/길이·용접선 기준 분할 + 여유 | ✅ | 쉘 롱심/원주분할, 헤드 현 분할(오프셋), 콘 부채꼴 n 분할 |
| | | `nest_group` / `nest_all` shelf 배치, 멀티규격·맞춤 길이 | ✅ | bbox 기반. 목적함수 4종 비교 후 `pieces` 기본 |
| | | `write_cutting_plan_dxf` 기존 CP 도면 형식 | ✅ | 라벨 `A516-70 t10 x 2438 x 9150 - 1 SH'T` |
| | | `build_por` POR PLATE 행 + por.csv | ✅ | 중량 = t×W×L×7.85e-6 (실제 POR 1,751kg 재현) |
| **L4 검증·HITL** | 저신뢰 항목 사람 확정 | `verify_part_spec` / `verify_weight_vs_bom` / `verify_nesting` | ✅ | reward 함수의 원형 |
| | | `compare_with_gt` 사람 커팅플랜(gt/sheets.csv) 대비 | ✅ | 개발·평가용 |
| | | `ask_human(H1~H4)` | ✅ | policy: ask / auto. eval 모드는 자동 응답 + 기록 |
| | | `confidence_report` | ✅ | HITL 위치 결정 근거 (RQ2) |
| 보조 | | `list_inputs`, `get_state_summary` | ✅ | |

✅ = API 없이 smoke test 통과, 🔑 = 코드는 있으나 `ANTHROPIC_API_KEY` 가 없어 미실행.

## 2. Smoke test 결과 (KD25038, 발표자료 검증 사례, 2026-10-01)

| 항목 | 이 코드 | KDM 배치툴 / 실제 PO | 비고 |
|---|---|---|---|
| 쉘 전개 길이 | π(2600+10) = **8199.6** | 8168 (= π×2600) | KDM 툴은 ID 기준. 툴킷 44건 역산은 평균지름. **어느 쪽이 KDM 표준인지 확인 필요** |
| 헤드 블랭크 | 1.25×ID = **3250** | 3240 | 경험계수. 2026-10-23 부터는 회사 계산 문서 식 1.2×Dm + 2×SF + 트림 30 = **3260** (SF 50 은 가정값) |
| 헤드 분할 | 1970 + 1280 (오프셋 345) | 1970 + 1270 (오프셋 350) | 현 분할 규칙 일치 |
| 콘 분할 | 폭 2438 기준 4조각 (1447×1998) | 폭 3048 기준 2조각 (2604×2604) | **분할 수는 판폭 선택에 종속** → 분할·판폭 공동 탐색 필요 |
| t10 판 수 / gross | 4장 / 5,657 kg (활용률 75%) | 3장 / 5,486 kg (77%) | 중량 +3%. bbox 배치라 반원·부채꼴 맞물림 불가 → NFP 엔진 필요 |
| 검증 | 겹침 0, 여유 위반 0, 22/22 배치 | | |

목적함수 비교 (콘 폭 2438): pieces 4장 5,657 / util 4장 5,671 / net 3장 6,692 / net_util 4장 5,671 → `pieces` 채택.

## 3. 다음 단계
1. `ANTHROPIC_API_KEY` 를 넣고 KD23002 (도면 12장, 정답 완비) 로 L1·L2 실행 → `runs/KD23002/trajectory.json` 확보.
2. 분할·판폭 공동 최적화: `split_to_pieces(max_w)` 를 후보 폭마다 돌려 `nest_group` 결과가 최소인 조합 선택 (RQ1 과 직결).
3. 곡선 맞물림 네스팅 (NFP: SVGnest/Deepnest 포트 또는 shapely 기반).
4. 헤드 블랭크 계수·쉘 중립축 규약을 part_tags.csv 로 확정.
5. 평가: scorecard 성공 워크오더 30건에 run_eval → 판 수·중량 비율 분포 → verifier 를 reward 로 Phase 2.
