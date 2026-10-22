# 발표 자료

발표 슬라이드를 만드는 스크립트는 레포 루트의 `presentation/` 에 둔다. 2026-10-23 에 `presentation` 브랜치에서 만들었다. pptx 는 스크립트로 만드는 결과물이라 커밋하지 않는다.

## 1. 파일

| 파일 | 내용 |
|---|---|
| `presentation/slides.py` | 모든 덱이 같이 쓰는 색, 글꼴, 도형, 슬라이드 틀(`Deck`) |
| `presentation/build_reader_orchestrator.py` | "도면 판독 orchestrator" 파트 (14장, 약 18분) → `reader_orchestrator.pptx` |
| `presentation/build_dwg_dxf.py` | "DWG 와 DXF" 파트 (12장, 약 15분) → `dwg_dxf.pptx`. 글은 줄이고 차트 · 도면 그림 · 도식으로 보여 준다. cone_0019 그림은 빌드할 때 `data_v3/synthetic` 의 DXF 에서 그려 `presentation/build/assets/` 에 둔다 (없으면 회색 상자) |
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

| 슬라이드의 숫자 | 출처 |
|---|---|
| 입력 도면 DWG 536장, 버전 AC1021 301 · AC1018 231 · AC1024 4 | `Data/dataset/KDM` 아래 `input` 의 `*.dwg` 첫 6바이트 |
| DWG 0.2–0.5 MB → DXF 1.1–2.8 MB (5.0–7.7배) | 위 536장을 정렬해 50장마다 1장씩 뽑은 11장을 LibreDWG 0.14 `dwg2dxf` 로 변환. R2007 2장은 7,463 바이트 빈 DXF, 나머지 9장 |
| 82만–218만 토큰 | 변환한 DXF 3장 전체를 Qwen3.6-27B 토크나이저로 셈 (837,402 / 823,730 / 2,179,027) |
| 4,747 토큰, 엔티티 66개 | `data_v3/synthetic/cone_0019/cone_0019.dxf` 같은 방법. 엔티티 수는 판독 01단계 결과 |
| cone_0019 의 표제란 SPCC, 4t · 1/2 · SYN-00019, 치수 150 × 150 × 150 | 판독 02 `title_regex`, 08 `document` 단계 결과 (orchestrator 시연 실행) |
| 262,144 | Qwen3.6-27B 토크나이저 설정의 최대 길이 |
| 엔티티 2,085–7,245개, LINE 60–69% | 변환한 DXF 2장을 ezdxf 로 읽어 modelspace 엔티티를 셈 |
| UTF-8 로 62자 깨짐, CP949 로 한글 39자 | AC1018 DXF 2장(`$DWGCODEPAGE` = ANSI_949)을 두 인코딩으로 읽어 셈 |
| 87장 실패 (빈 DXF 77, ezdxf 가 못 여는 DXF 10), 그중 47장은 PDF 있음 | [AGENTS.md](../AGENTS.md) 6절 (2026-10-22) |

변환한 DXF 는 세션 임시 폴더에만 두었고 레포에는 없다.
