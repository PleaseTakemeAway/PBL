# 발표 자료

발표 슬라이드를 만드는 스크립트는 레포 루트의 `presentation/` 에 둔다. 2026-10-23 에 `presentation` 브랜치에서 만들었다. pptx 는 스크립트로 만드는 결과물이라 커밋하지 않는다.

## 1. 파일

| 파일 | 내용 |
|---|---|
| `presentation/slides.py` | 모든 덱이 같이 쓰는 색, 글꼴, 도형, 슬라이드 틀(`Deck`) |
| `presentation/build_reader_orchestrator.py` | "도면 판독 orchestrator" 파트 (14장, 약 18분) → `reader_orchestrator.pptx` |
| `presentation/build_dwg_dxf.py` | "AI 는 도면을 어떻게 읽을까" 파트 (10장, 약 15분) → `dwg_dxf.pptx`. DWG 를 DXF 로 바꾸는 이유를 AI 를 모르는 청중에게 그림과 비유로 설명한다. cone_0019 그림은 빌드할 때 `data_v3/synthetic` 의 DXF 에서 그려 `presentation/build/assets/` 에 둔다 (없으면 회색 상자) |
| `presentation/render.py` | pptx 를 PDF 와 슬라이드별 PNG 로 바꾼다. 배치 확인용 |
| `presentation/*.pptx`, `presentation/build/` | 위 스크립트의 출력. 커밋하지 않는다 (`presentation/.gitignore`) |

슬라이드 내용, 배치, 발표자 노트가 모두 스크립트에 있다. 슬라이드의 숫자를 어디서 가져왔는지는 각 스크립트 머리말과 4절에 적었다. 합성 도면과 집계 숫자만 쓰고 고객 도면의 내용은 싣지 않는다.

## 2. 만들고 확인하기

레포 루트에서 실행한다. `python-pptx` 는 프로젝트 의존성이 아니라서 `--with` 로 붙인다.

```bash
PYTHONPATH=. uv run --with python-pptx python presentation/build_reader_orchestrator.py   # → presentation/reader_orchestrator.pptx
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
- PowerPoint 에서 손으로 다듬고 싶으면 다른 이름으로 저장한다 (예: `reader_orchestrator_final.pptx`). 스크립트를 다시 돌리면 원래 이름의 파일을 덮어쓴다. 손으로 고친 파일은 커밋되지 않으므로 발표 PC 로 따로 옮긴다.

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
