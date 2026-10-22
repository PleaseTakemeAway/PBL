# 문서 안내

사람이 읽는 문서는 모두 이 폴더에 있다. 코드가 실행 중에 읽는 프롬프트·지식 문서는 코드 옆에 둔다 (4절).

## 1. 처음 읽는 순서

1. [harness_engineering.md](harness_engineering.md) — 이 프로젝트의 목표(로컬 LLM + 하네스)와 지금 상태, 로드맵
2. [getting_started.md](getting_started.md) — 설치, 실행, 자주 나는 문제
3. [execution_flow.md](execution_flow.md) — 두 에이전트(v2 워크오더 에이전트, v3 도면 판독기)의 진입점과 함수 호출 순서
4. [data/overview.md](data/overview.md) — 데이터가 어디 있고 어떤 스크립트가 만들며 누가 쓰는지
5. [domain/glossary_kr.md](domain/glossary_kr.md) — 도면·제작 용어 (쉘, 코스, 경판, 네스팅, POR …)

그다음은 보려는 쪽에 따라 `agent/` (v2) 또는 `reader/` (v3) 로 간다.

## 2. 문서 목록

| 폴더 | 문서 | 내용 |
|---|---|---|
| `docs/` | [harness_engineering.md](harness_engineering.md) | 목표: 로컬 LLM 으로 orchestration 과 작업을 모두 하는 하네스. 지금 상태 판단과 로드맵 |
| | [getting_started.md](getting_started.md) | uv 설치, `.env`, 실행 명령, 데이터·외부 도구, 자주 나는 문제 |
| | [execution_flow.md](execution_flow.md) | 진입점, 실행 순서, 결과물, 두 코드가 같은 일을 다르게 하는 곳 |
| `agent/` (v2) | [skills.md](agent/skills.md) | skill 25개 분류표, KD25038 smoke test 기록, 다음 단계 |
| | [skill_agent_framework.md](agent/skill_agent_framework.md) | 2026-10-01 의 설계 문서. 구현과 다른 부분이 있다 |
| `reader/` (v3) | [stages.md](reader/stages.md) | DXF 판독 13단계: 단계별 실행 명령, 단계마다 남는 파일, 한 단계만 다시 돌리기 |
| | [README.md](reader/README.md) | 동료가 쓴 v3 사용법: 입력 경로, VLM 설정, 실험 스크립트 옵션 |
| | [code_v3.md](reader/code_v3.md) | `experiments.sh` 실행 흐름과 파일별 역할, 출력 구조 |
| | [framework.md](reader/framework.md) | 구성도와 모델·결정론 처리의 경계 |
| `data/` | [overview.md](data/overview.md) | 데이터 지도, 스크립트 ①~⑥ 의 입출력, 정답과 평가 |
| | [dataset_structure.md](data/dataset_structure.md) | `Data/dataset/` 의 폴더 구조와 Drive 원본의 의미 |
| | [part_class_rules.md](data/part_class_rules.md) | 부품 이름 정규화와 형상 class 결정 규칙 |
| `domain/` | [glossary_kr.md](domain/glossary_kr.md) | 도면·제작 용어, AI 구조·skill 용어, 실험 용어 |
| | [unfold_pipeline_tools.md](domain/unfold_pipeline_tools.md) | 형상별 전개 판정과 전개 공식, 툴킷 설명 |
| | [unfold_classification_table.md](domain/unfold_classification_table.md) | KDM 도면 부품 라벨 779건의 전개 분류표 |
| | [knowledge_files.md](domain/knowledge_files.md) | 에이전트가 읽는 지식·프롬프트 파일 목록과 읽는 시점 |

동료의 zip 에서 받아 온 문서(`reader/` 의 `stages.md` 를 뺀 문서, `agent/skill_agent_framework.md`, `data/dataset_structure.md`, `data/part_class_rules.md`, `domain/`)는 내용을 그대로 두었다. 옛 경로가 나오면 [execution_flow.md](execution_flow.md) 와 [getting_started.md](getting_started.md) 의 경로가 현재 기준이다.

## 3. 레포 구조

```
pyproject.toml, uv.lock  uv 의존성
.env.example           .env (API 키·머신별 값, git 제외) 템플릿
AGENTS.md, CLAUDE.md   코딩 에이전트용 규칙 (도구가 루트에서 찾는다)
cutplan_agent/
  config.py            경로, 모델(claude-opus-5-5), 커팅여유 20(가스), 운반상한 12000x3050, 표준폭, 전개판정 키워드
  state.py             JobState(도면·BOM·PartSpec·조각·판·POR·HITL) + Trajectory(skill 호출 로그 = RL 데이터) + @logged
  unfold.py            절곡·평판 전개 엔진 (tools/dwg2png/vlm/unfold.py 에서 이전). --validate 로 원통 공식 재검증
  skills/l1_perception.py  l2_relation.py  l3_rules.py  l4_verify.py  knowledge.py
  knowledge/*.md       v2 가 읽는 도메인 지식 7종 (skills/01_core_knowledge 와 같은 내용)
  agent/orchestrator.py  Claude tool_runner. agent/system.md = 절차 ①~⑥ + 원칙
  eval/smoke_kd25038.py  API 없이 L2(B경로)→L3→L4 전체 경로 실행
  eval/run_eval.py       dataset 워크오더 평가 (API 필요)
  eval/run_experiments.py  E1·E2 는 API 없이 test_data 로 실행
  reader/              v3 도면 판독: DXF·이미지 → 형상 분류 → 전개도. main.py 가 CLI
  reader/stages/       DXF 판독 13단계. 단계마다 따로 실행되고, main.py --batch 가 차례로 부른다
  reconstruct/         v3 3D 복원: models, geometry, pipeline, step1~6
tests/                 reader·reconstruct 단위 테스트 (fixtures/ 는 git 제외)
experiments/           v3 실험 스크립트: experiments*.sh (vLLM 서버 + 배치), serve.sh (서버만), verify_ocr_output.py, requirements.txt
scripts/               Data/dataset · part_class_dataset · test_data 구축 스크립트 (data/overview.md)
skills/                reader 와 v2 가 프롬프트로 읽는 지식·프롬프트 문서 (01_core_knowledge, 02_prompts)
docs/                  사람이 읽는 문서 (이 폴더)

# 아래는 git 제외 (data/overview.md)
Data/                  원본·정제 데이터 (dataset, _dataset, part_class_dataset, 연도별 cutting plan)
test_data/             scripts/build_test_data.py 가 Data/dataset 에서 만든 평가 세트
data_v3/synthetic/     reader 입력: 합성 DXF + label.json 30개
tools/dwg2png/         이전 세션 툴킷 (Windows 용 libredwg, cp_extract 등). 코드는 Windows 의 dwg2dxf.exe 만 쓴다
runs/                  실행 결과. v2 는 runs/<job>/, v3 는 runs/reader/
```

## 4. 이 폴더 밖에 있는 문서

| 위치 | 왜 밖에 있나 |
|---|---|
| `skills/01_core_knowledge/*.md`, `skills/02_prompts/*.md` | reader 와 v2 가 실행 중에 프롬프트로 읽는다. 고치면 모델 입력이 바뀌고, reader 는 읽은 문서의 sha256 을 실행 기록에 남긴다. 목록과 읽는 시점은 [domain/knowledge_files.md](domain/knowledge_files.md) |
| `cutplan_agent/knowledge/*.md`, `cutplan_agent/agent/system.md` | v2 가 읽는다. `skills/01_core_knowledge/` 와 바이트 단위로 같은 복사본이다 |
| `AGENTS.md`, `CLAUDE.md` | 코딩 에이전트 도구가 레포 루트에서 찾는다 |
| `README.md` (루트) | GitHub 첫 화면. 짧은 소개와 이 폴더로 가는 링크만 둔다 |
| `Data/dataset/README.md`, `Data/part_class_dataset/README.md`, `test_data/README.md`·`README.html` | 데이터를 만드는 스크립트가 데이터와 함께 만든다 (git 제외) |
