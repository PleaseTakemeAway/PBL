# 발표 자료

발표 슬라이드와 그것을 만드는 스크립트는 레포 루트의 `presentation/` 에 둔다. 2026-10-23 에 `presentation` 브랜치에서 만들었다.

## 1. 파일

| 파일 | 내용 |
|---|---|
| `presentation/build_reader_orchestrator.py` | "도면 판독 orchestrator" 파트 (14장, 약 18분). 슬라이드 내용과 배치, 발표자 노트가 모두 이 스크립트에 있다 |
| `presentation/reader_orchestrator.pptx` | 위 스크립트가 만든 결과. 바로 열어 발표할 수 있게 커밋한다 |
| `presentation/render.py` | pptx 를 PDF 와 슬라이드별 PNG 로 바꾼다. 배치 확인용 |
| `presentation/build/` | `render.py` 출력. 커밋하지 않는다 |

orchestrator 파트의 숫자는 `reader-agent` 브랜치의 [reader/orchestrator.md](reader/orchestrator.md) 와 2026-10-23 `mlic` 의 cone_0019 실행 기록에서 가져왔다. 합성 도면만 썼고 고객 도면은 없다.

## 2. 만들고 확인하기

레포 루트에서 실행한다.

```bash
PYTHONPATH=. uv run --with python-pptx python presentation/build_reader_orchestrator.py
PYTHONPATH=. uv run python presentation/render.py presentation/reader_orchestrator.pptx   # build/*.png
```

- `render.py` 는 LibreOffice(`soffice`)가 필요하다. 한글 폰트가 없으면 글자가 네모로 나온다. `mlic` 에는 나눔고딕을 `~/.local/share/fonts/nanum/` 에 받아 두었다 (2026-10-23).
- 슬라이드 글꼴은 맑은 고딕(Malgun Gothic)이다. 미리보기는 나눔고딕과 DejaVu Sans 로 대신 그리므로, PowerPoint 에서는 줄바꿈 위치와 단어 간격이 조금 다르다. 미리보기에서 들어가면 PowerPoint 에서도 들어간다 (대체 글꼴이 더 넓다).
- 같은 스크립트는 같은 pptx 를 바이트 단위로 똑같이 만든다 (zip 항목 시각과 문서 속성을 고정한다). 내용을 바꾸지 않고 다시 빌드하면 git 에 변경이 생기지 않는다.

## 3. 고치는 방법

- 슬라이드는 스크립트를 고쳐서 바꾸고, pptx 를 다시 만들어 둘을 같은 커밋에 넣는다. 그래야 변경이 텍스트 diff 로 보이고 여러 worktree 의 변경을 머지할 수 있다.
- pptx 는 바이너리라 git 이 머지하지 못한다. 두 브랜치가 모두 pptx 를 바꿨으면 스크립트만 머지하고 pptx 는 어느 쪽이든 받은 뒤 다시 빌드한다.

  ```bash
  git checkout --theirs presentation/reader_orchestrator.pptx
  PYTHONPATH=. uv run --with python-pptx python presentation/build_reader_orchestrator.py
  git add presentation/reader_orchestrator.pptx
  ```

- PowerPoint 에서 손으로 다듬고 싶으면 다른 이름으로 저장한다 (예: `presentation/reader_orchestrator_final.pptx`). 스크립트를 다시 돌리면 `reader_orchestrator.pptx` 를 덮어쓰기 때문이다. 손으로 고친 파일은 그 뒤로 스크립트와 따로 관리된다.
- 발표의 다른 파트도 같은 방식으로 `presentation/build_<파트>.py` 와 `presentation/<파트>.pptx` 를 따로 만들면, 파트끼리 머지 충돌이 나지 않는다.
