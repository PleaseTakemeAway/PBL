# 발표 자료

발표 슬라이드를 만드는 스크립트는 레포 루트의 `presentation/` 에 둔다. 2026-10-23 에 `presentation` 브랜치에서 만들었다. pptx 는 스크립트로 만드는 결과물이라 커밋하지 않는다.

## 1. 파일

| 파일 | 내용 |
|---|---|
| `presentation/slides.py` | 모든 덱이 같이 쓰는 색, 글꼴, 도형, 슬라이드 틀(`Deck`) |
| `presentation/build_roadmap.py` | "우리는 지금 어디쯤 왔나" 파트 (20장, 약 20분) → `roadmap.pptx`. v2 → v3 → 지금 → 다음 순서로 프로젝트의 위치를 AI 를 모르는 청중에게 보인다. 2026-10-23 에 "도면 판독 orchestrator" 덱(`build_reader_orchestrator.py`, 14장, 커밋 7f543c2 까지)을 이 구성으로 바꿨다 |
| `presentation/build_dwg_dxf.py` | "AI 는 도면을 어떻게 읽을까" 파트 (10장, 약 15분) → `dwg_dxf.pptx`. DWG 를 DXF 로 바꾸는 이유를 AI 를 모르는 청중에게 그림과 비유로 설명한다. cone_0019 그림은 빌드할 때 `data_v3/synthetic` 의 DXF 에서 그려 `presentation/build/assets/` 에 둔다 (없으면 회색 상자) |
| `presentation/render.py` | pptx 를 PDF 와 슬라이드별 PNG 로 바꾼다. 배치 확인용 |
| `presentation/*.pptx`, `presentation/build/` | 위 스크립트의 출력. 커밋하지 않는다 (`presentation/.gitignore`) |

슬라이드 내용, 배치, 발표자 노트가 모두 스크립트에 있다. 슬라이드의 숫자를 어디서 가져왔는지는 각 스크립트 머리말과 4절에 적었다. 합성 도면과 집계 숫자만 쓰고 고객 도면의 내용은 싣지 않는다.

## 2. 만들고 확인하기

레포 루트에서 실행한다. `python-pptx` 는 프로젝트 의존성이 아니라서 `--with` 로 붙인다.

```bash
PYTHONPATH=. uv run --with python-pptx python presentation/build_roadmap.py               # → presentation/roadmap.pptx
PYTHONPATH=. uv run --with python-pptx python presentation/build_dwg_dxf.py               # → presentation/dwg_dxf.pptx
PYTHONPATH=. uv run python presentation/render.py presentation/dwg_dxf.pptx               # → presentation/build/*.png
```

- `render.py` 는 LibreOffice(`soffice`)와 한글 폰트가 필요하다. 미리보기는 임시 사본에서 맑은 고딕을 나눔고딕으로 바꿔 그린다. 바꾸지 않으면 LibreOffice 가 글자 묶음마다 대체 글꼴을 따로 골라 일부 한글이 네모로 나온다. `mlic` 에는 나눔고딕을 `~/.local/share/fonts/nanum/` 에 받아 두었다 (2026-10-23).
- 슬라이드 글꼴은 맑은 고딕(Malgun Gothic)이다. 미리보기는 나눔고딕과 DejaVu Sans 로 대신 그리므로, PowerPoint 에서는 줄바꿈 위치와 단어 간격이 조금 다르다. 대체 글꼴이 더 넓어서, 미리보기에서 들어가면 PowerPoint 에서도 들어간다.
- 같은 스크립트는 같은 pptx 를 바이트 단위로 똑같이 만든다 (zip 항목 시각과 문서 속성을 고정한다). 리팩터링 뒤 결과가 그대로인지 sha256 으로 확인할 수 있다.

## 3. 고치는 방법

- 슬라이드는 스크립트를 고쳐서 바꾼다. 변경이 텍스트 diff 로 보이고, 여러 worktree 의 변경을 git 이 머지한다. 머지한 뒤 pptx 를 다시 만들면 된다.
- 공통 모양(색, 글꼴, 카드 모양)은 `slides.py` 에서 한 번 고치면 모든 덱에 반영된다.
- 새 파트는 `presentation/build_<파트>.py` 를 따로 만든다. 파트끼리 같은 파일을 고치지 않으므로 충돌이 나지 않는다.
- PowerPoint 에서 손으로 다듬고 싶으면 다른 이름으로 저장한다 (예: `roadmap_final.pptx`). 스크립트를 다시 돌리면 원래 이름의 파일을 덮어쓴다. 손으로 고친 파일은 커밋되지 않으므로 발표 PC 로 따로 옮긴다.

## 4. DWG·DXF 파트의 숫자 출처 (2026-10-23, `mlic`)

청중은 AI 와 프로그래밍을 잘 모르는 사람들이다. 이야기 순서: AI 는 글자와 그림을 읽고 바이너리는 못 읽는다 → DWG 는 메모장에서 기호뿐, DXF 는 글자 → 그런데 실제 도면의 DXF 는 AI 가 한 번에 읽는 양의 50배 → 프로그램은 0.1초에 읽는다 → 둘이 잘하는 것이 다르다 → 함께 하면 → 그래서 DWG 를 DXF 로 바꾼다.

| 슬라이드의 숫자 | 출처 |
|---|---|
| DWG 를 메모장으로 연 모습, 읽히는 글자 23% | `cone_0019.dxf` 를 LibreDWG 0.14 `dxf2dwg` 로 DWG(6,346 바이트, AC1015)로 저장. 바이트를 Latin-1 로 보고 제어 문자를 □ 로 바꿈. 출력 가능한 ASCII 바이트 비율 23%. 문자열은 스크립트의 `DWG_AS_TEXT` |
| DXF 를 메모장으로 연 모습 | `cone_0019.dxf` 의 첫 LINE 엔티티 |
| AI 가 한 번에 약 50쪽, 실제 도면 DXF 약 2,500쪽 (×50) | 실제 입력 도면 1장의 DXF (1.1 MB, 124,962줄, Qwen3.6-27B 토크나이저로 837,402 토큰 = 줄당 6.7 토큰). 서버 컨텍스트 16,384 토큰 ≈ 2,445줄 ≈ 49쪽, DXF 124,962줄 ≈ 2,499쪽 (1쪽 = 50줄). 토크나이저 최대 262,144 토큰으로도 약 780쪽 |
| 0.1초, 선 1,243, 글자 330 | 같은 DXF 를 `ezdxf.readfile` 로 읽고 modelspace 를 센 시간 0.13초, LINE 1,243, TEXT·MTEXT 330 |
| 요소 66개, 치수 150, SPCC · 두께 4, "원뿔", 정면 · 평면 · 우측면 | cone_0019 판독 실행(orchestrator 시연): 01 `read` 엔티티 66개, 02 `title_regex`, 08 `document`, 06 `view_labels` (part_class=cone) |
| 전개도 (반지름 405.65 / 252.87, 68.33°) | 같은 실행의 10 `develop`. 그림은 이 값으로 그린 부채꼴. 작은 지름을 모델이 92 로 읽었다 (정답 100). 발표자 노트에 적었다 |
| 536장 중 87장 실패 (빈 파일 77, 못 엶 10) | [AGENTS.md](../AGENTS.md) 6절 (2026-10-22). 2026-10-23 에 같은 스크립트로 다시 돌려 같은 숫자를 얻었다: `uv run python scripts/render_drawings.py Data/dataset/KDM/*/*/input -o runs/render_drawings/kdm_input --format png -j 16` → 도면 572개(DWG 536, DXF 36) 중 485개 성공. 실패 87개는 모두 DWG 이고, 빈 DXF 77개의 버전은 R2007 76 · R2004 1 이다 (AGENTS.md 는 77개 모두 R2007 이라고 적었다). 47개는 같은 이름의 PDF 가 있다 |

### 실패한 도면 목록과 부록

- `runs/render_drawings/kdm_input/render_failures.txt`: 위 명령이 쓴 원본 (`DWG 절대경로 <탭> 오류`).
- `runs/render_drawings/kdm_input/render_failures_summary.tsv`: 워크오더, 파일, 실패 종류, DWG 버전, 같은 이름 PDF, 레포 루트 기준 경로. 엑셀에서 열린다 (UTF-8 BOM). `render_failures.txt` 에서 만들었다.
- 덱은 빌드할 때 이 TSV 를 읽어 9번 슬라이드의 발표자 노트에 87개 경로를 넣고, 끝에 숨긴 부록 슬라이드 A1–A6 을 붙인다. 슬라이드쇼에서는 건너뛰고, 질문이 나오면 그 슬라이드로 간다. TSV 가 없으면 부록 없이 빌드된다.
- 도면 파일 이름은 고객 정보라서 스크립트에는 적지 않고 빌드할 때만 읽는다. 그래서 만든 pptx 에는 파일 이름이 들어 있으니 밖으로 공유하지 않는다. 발표용 worktree 에서는 `runs/render_drawings` 를 원래 clone 의 같은 폴더로 링크해 쓴다.

변환한 DWG·DXF 는 세션 임시 폴더에만 두었고 레포에는 없다. 회사 도면은 크기, 줄 수, 개수, 시간만 썼다.

## 5. 로드맵 파트의 숫자 출처 (2026-10-23, `mlic`)

이야기 순서: 전체 지도(도면 읽기 → 전개도 → 커팅플랜 → 구매의뢰) → v2 는 Claude 에게 전부 맡겼다 → skill 이란 (메뉴판과 주방) → Claude 가 skill 을 부르는 반복 → 잘 안 됐다 → 왜 옮겼나 → v3 는 로컬 AI 로 도면 읽기에 집중 → 서버와 두 모델 → 13단계 중 AI 5곳 → 연습(합성) 도면부터 → 27/30 (지금) → 할 일 둘: 하네스, 실제 도면 → tool calling (v2 에서 본 그 방식) → 실제 도면에 적용 → 함수로 만들 수 있으면 AI 가 쓴다.

MCP 는 청중에게 소개한 적이 없어서 넣지 않았다.

| 슬라이드의 내용 | 출처 |
|---|---|
| v2: Claude Opus, skill 25개 (보기 · 읽기 4, 판단 7, 계산 6, 검사 6, 상태 2), 참고서 7권 | `cutplan_agent/agent/orchestrator.py` 의 `SKILLS`, `config.py` 의 `MODEL = "claude-opus-5-5"` (동료 원본 f51473f 도 같다), `cutplan_agent/knowledge/*.md` 7개. 분류는 [agent/skills.md](agent/skills.md) 1절. `load_domain_prompt` 를 판단에 셌다 |
| v2 의 대상은 실제 회사 도면 | [agent/skill_agent_framework.md](agent/skill_agent_framework.md) 의 대상 데이터 (`Data/data_v2` HCE 판금 스캔 PDF, KDM 압력용기 커팅플랜). v2 는 합성 도면을 쓰지 않았다 |
| v2 결과: 잘 안 됐다 | 팀의 경험. **이 레포에는 v2 를 Claude 로 끝까지 돌린 기록이나 숫자가 없다** ([agent/skills.md](agent/skills.md) 는 VLM 경로를 미실행으로 적는다). 슬라이드에 숫자를 넣지 않았다 |
| 지름 10 mm → 둘레 31 mm → 폐기 | v2 에서 실제로 일어난 일이 아니라 예시다. `cutplan_agent/agent/system.md` 원칙 2 ("지름 10mm 오차는 원주 31mm 오차이고 그 판은 폐기된다", 동료가 AI 에게 준 지침). π × 10 = 31.4. 슬라이드에 "예" 와 출처 한 줄을 붙였다 |
| 왜 옮겼나: 수업의 목표, v2 의 교훈, 비용과 보안 | 목표와 "Claude 는 시행착오용" 은 [harness_engineering.md](harness_engineering.md) 1절. 교훈은 앞 슬라이드. 비용과 보안은 클라우드 API 의 일반적인 성질이고, 동료가 이유로 적어 둔 기록은 없다 |
| 보이려는 것 (가설): 작은 로컬 AI 라도 하네스를 잘 만들면 쓸 만한 결과 | [harness_engineering.md](harness_engineering.md) 1절의 목표 문장. 아직 증명 전이라 "주장" 대신 "가설" 로 적었다 |
| 서버: RTX A5000 24 GB × 4, Xeon Gold 6336Y 48코어, 메모리 128 GB (`free` 125 GiB) | `nvidia-smi`, `lscpu`, `free` |
| OCR 모델 6 GB, 추론 모델 52 GB, 추론 모델은 GPU 1–3 | `~/.cache/huggingface/hub` 의 모델 폴더 크기 (`du -shL`). 배치는 `experiments/vllm_common.sh` 기본값. Qwen3.6-27B 는 `vision_config` 가 있는 VLM 이다 |
| 동료는 90 GB 급 GPU 두 장 (발표자 노트) | [AGENTS.md](../AGENTS.md) 6절 |
| 13단계 중 AI 5곳 | [reader/quickstart.md](reader/quickstart.md) 3절 |
| 합성: 부품 1, 뷰 3, 선 · 글자 66 / 실제: 뷰 후보 최대 13, 선 · 글자 2,000–5,900 | `runs/reader/check/cone_0019` 와 `runs/reader/real_drawings/` 의 `01_read.json` `entity_counts` 합, `05_views.json` 의 `views` 수. 실제는 S-2120 4장과 KD23009 1장: 요소 2,074–5,876, 뷰 후보 0–13 |
| 합성 30장 = 5모양 × 6장 | `data_v3/synthetic` 폴더 이름 |
| 27/30, 모양별 6 · 6 · 6 · 5 · 4 | `runs/reader/deepseek_ocr_qwen_reasoning_skills/accuracy.md` (동료, 2026-10-18) |
| 시제품: AI 판단 3번, 133초, 지어낸 숫자 0 | `reader-agent` 브랜치의 orchestrator 를 cone_0019 에 돌린 실행 (2026-10-23, schema 모드). 아직 main 에 없다 |
| S-2120: 정답 부품 22종 (라벨 51개), 입력 도면 4장 | `test_data/cases/S-2120/output_cutting_plan/parts.csv`: 행 51개, (도면 번호, 아이템) 쌍 22개 |
| 실제 도면을 로컬 모델로 판독한 결과 | 2026-10-23 05:00 에 떠 있던 서버(DeepSeek-OCR-2 + Qwen3.6-27B)로 `scripts/reader/run_stages.py <작업 폴더> --dxf <도면>` 을 `runs/reader/real_drawings/*/dxf/` 의 S-2120 4장에 돌렸다 . 실행 스크립트·로그·단계 파일은 `runs/reader/real_drawings_vlm/` (`run.sh`, `run.log`, `<도면>/stages/NN_*.json`, git 제외). 단계 파일 안의 그림 경로는 처음 돌린 임시 폴더를 가리킨다. DWG-001(조립도): 원통, 두께 18, 안지름 1500, 길이 1877 → 펼친 길이 π(1500+18) = 4,768.9. DWG-002·004: 08 document 에서 `views with unique IDs` 오류. DWG-003: `part_class` other 라 전개 안 함 |
| 두께 정답 8, 펼친 길이 정답 4,738, "두께가 틀리면 철판을 잘못 산다" | 같은 `parts.csv` 의 SHELL (A240-S31803, 두께 8, 외곽 4738 × 1823). π(1500+8) = 4,737.6. 조립도 DXF 의 글자에도 `USED TH'K : t8` 이 있다. 모델의 근거 문장은 "t=18 mm in the front view" 였다 (`VP-S-2120-DWG-001/stages/09_unfold_params.json` 의 `record.notes`). 길이가 31 mm 긴 판은 잘라 맞출 수도 있어 이 슬라이드에서는 "폐기" 대신 두께(구매할 철판)가 틀린다는 점을 결과로 적었다. 폭도 1,877 (모델이 읽은 T.L 길이) 과 정답 1,823 이 다르다 |
| 부품별 결과 표 예시 (SHELL 4738 × 1823, TOP HEAD Ø1890) | 같은 `parts.csv` 의 정답 외곽. 슬라이드에서는 tool calling 으로 만들 결과의 모양을 보이는 예시로 썼다 |
| v2 계산 도구가 끝까지 돈다 | smoke test: 손으로 넣은 부품 8개로 22/22 배치, 6132.2 kg ([AGENTS.md](../AGENTS.md) 6절) |

참고: `runs/reader/data_v3_claude_batch_10141611` 은 같은 합성 30장을 Claude(Sonnet 5 추론, Haiku 4.5 OCR)로 돌려 25/30 이다 (2026-10-14). 날짜와 코드가 27/30 실행과 달라 로컬과 Claude 를 비교하는 근거로 쓰지 않았다. "로컬 AI 가 Claude 보다 작고 도면을 보는 눈이 약하다"는 팀의 판단이고, 같은 조건에서 잰 숫자는 아직 없다 ([harness_engineering.md](harness_engineering.md) 2.1절 5번).
