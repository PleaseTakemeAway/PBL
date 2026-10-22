# 시작하기

필요한 도구는 [uv](https://docs.astral.sh/uv/) 하나다. Python 설치·가상환경·패키지 설치를 uv 가 모두 맡는다.

## 1. 처음 한 번

1. uv 설치 (설치 후 터미널을 새로 연다)
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. 프로젝트 폴더에서 `uv sync` — `.venv` 를 만들고 의존성을 설치한다. `cutplan_agent` 는 설치하지 않고 소스 그대로 실행한다 (2절). 의존성이 바뀌어 `git pull` 한 뒤에도 다시 실행한다.
3. `.env.example` 을 `.env` 로 복사하고 값을 채운다 (Windows: `copy .env.example .env`, Linux: `cp .env.example .env`).
   - `ANTHROPIC_API_KEY`: VLM 단계(L1·L2, orchestrator)에 필요. smoke test 만 돌릴 땐 비워도 된다.
   - `CUTPLAN_ROOT`: 데이터가 project root 가 아닌 곳에 있을 때만.
   - `.env` 는 실행 시 자동으로 읽히고 git 에 올라가지 않는다.

## 2. 실행

프로젝트 폴더에서 `PYTHONPATH=.` 를 주고 파일 경로로 실행한다. `cutplan_agent` 는 설치하지 않으므로 `PYTHONPATH` 가 없으면 `import cutplan_agent` 가 실패한다.

```bash
PYTHONPATH=. uv run python cutplan_agent/eval/smoke_kd25038.py                       # API 불필요
PYTHONPATH=. uv run python cutplan_agent/agent/orchestrator.py --job KD23002 --eval  # dataset/KDM/2023/KD23002/input/drawings 사용
PYTHONPATH=. uv run python cutplan_agent/eval/run_eval.py --jobs KD23002,KD23015,KD23022
```

도면 판독기(v3, `cutplan_agent/reader/`)는 uv 환경에 아직 의존성이 없어 `--with` 로 붙인다. 로컬 모델 실험은 vllm 이 깔린 파이썬으로 `./experiments/experiments.sh --python <파이썬>` 을 쓴다.

```bash
PYTHONPATH=. uv run --with requests --with opencv-python-headless --with pytesseract \
  python cutplan_agent/reader/main.py --batch --input-mode dxf --no-vlm --output-dir runs/reader/novlm data_v3/synthetic
./experiments/experiments.sh --dry-run   # 서버를 띄우지 않고 설정만 출력
```

진입점별 실행 순서는 [execution_flow.md](execution_flow.md), 데이터와 스크립트는 [data/overview.md](data/overview.md) 를 본다.

Windows PowerShell 에서는 터미널마다 `$env:PYTHONPATH = "."` 를 한 번 실행하고, 명령 앞의 `PYTHONPATH=. ` 는 뺀다.

VSCode: `Ctrl+Shift+P` → `Python: Select Interpreter` → `.venv` 를 고른다. 디버그 설정(`launch.json`)에는 `"env": {"PYTHONPATH": "${workspaceFolder}"}` 를 넣는다.

## 3. 데이터·외부 도구

- 데이터·결과는 기본으로 project root 의 `Data/`, `test_data/`, `data_v3/synthetic/`, `runs/` 를 쓴다 (git 제외). `Data/` 는 팀 공유 압축본(노바투스2026)의 `Data/` 를 그대로 둔다.
- `test_data/` 는 `PYTHONPATH=. uv run python scripts/build_test_data.py` 로 `Data/dataset` 에서 만든다. 보통은 압축본의 `Data/` 를 그대로 두고 이것만 실행하면 된다.
- `Data/` 를 처음부터 다시 만들 때는 아래 순서로 `PYTHONPATH=. uv run python scripts/<이름>.py` 를 실행한다. 경로는 프로젝트 루트(또는 `CUTPLAN_ROOT`) 기준이라 Windows 와 Linux 에서 같다.
  `build_dataset.py` → `extract_part_unfolds.py` → `ingest_drive_inputs.py` → `build_part_class_dataset.py` → `build_test_data.py` → `build_test_data_html.py`
  Drive 원본은 `Data/drive/8. Data/` 에 푼다. 원본 없이 `manifest.csv` 만 갱신하려면 빈 `Data/drive/8. Data/` 폴더를 만들고 `ingest_drive_inputs.py` 를 실행한다.
- DWG 변환: Windows 는 `tools/dwg2png/libredwg/dwg2dxf.exe` 를, 그 밖에는 PATH 의 `dwg2dxf` 를 쓴다. Ubuntu 24.04 apt 에는 libredwg 패키지가 없으므로 GNU LibreDWG 를 소스에서 빌드해 설치한다.
- reader·reconstruct 테스트: `PYTHONPATH=. uv run --with requests --with opencv-python-headless --with pytesseract python -m unittest discover -s tests`. OCR 폴백 테스트는 tesseract 바이너리가 필요하다 (`sudo apt install tesseract-ocr`).

### 로컬 모델 (vLLM)

`experiments/experiments.sh` 는 vLLM 서버를 직접 띄운다. vLLM 은 레포의 `.venv` 와 따로 가상환경을 만든다. 아래는 RTX A5000 24GB 4장, NVIDIA 드라이버 535(CUDA 12.2)인 서버에서 실제로 쓴 명령이다.

```bash
uv venv --python 3.12 ~/venvs/vllm-0.31
uv pip install --python ~/venvs/vllm-0.31/bin/python --torch-backend cu129 \
  "vllm @ https://github.com/vllm-project/vllm/releases/download/v0.31.0/vllm-0.31.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl" \
  -r experiments/requirements.txt
uv pip install --python ~/venvs/vllm-0.31/bin/python \
  --index-url https://download.pytorch.org/whl/cpu "torchcodec==0.17.0+cpu"

# 모델 weight 는 ~/.cache/huggingface/hub 에 저장된다 (DeepSeek-OCR-2 6.8GB, Qwen3.6-27B 55.6GB)
HF_HUB_DISABLE_XET=1 ~/venvs/vllm-0.31/bin/hf download deepseek-ai/DeepSeek-OCR-2
HF_HUB_DISABLE_XET=1 ~/venvs/vllm-0.31/bin/hf download Qwen/Qwen3.6-27B

./experiments/experiments.sh --python ~/venvs/vllm-0.31/bin/python \
  --vllm-bin ~/venvs/vllm-0.31/bin/vllm --output-dir runs/reader/<새 폴더>
```

- PyPI 기본 `vllm`·`torch` 는 CUDA 13 용이라 드라이버 580 이상이 필요하다. `+cu129` wheel 은 CUDA 12 의 minor version 호환으로 드라이버 535 에서 돈다. 드라이버가 580 이상이면 `uv pip install vllm==0.31.0 --torch-backend=auto` 로 충분하다.
- `torchcodec` 은 cu129 인덱스에 0.17 이 없어 PyPI 의 CUDA 13 판이 깔린다. 그대로 두면 vLLM 이 시작할 때 `libnvrtc.so.13` 을 못 찾고 죽으므로 CPU 판으로 바꾼다. vLLM 은 이것을 오디오·영상 디코딩에만 쓴다.
- `HF_HUB_DISABLE_XET=1` 은 일반 HTTP 로 받게 한다. 이 서버에서는 xet 프로토콜이 초당 5MB 안팎으로 HTTP 보다 몇 배 느렸다.
- 스크립트 기본값은 GPU 0 에 OCR, GPU 1,2,3 에 Qwen3.6-27B 를 pipeline parallel 로 올린다 ([reader/README.md](reader/README.md)). GPU 가 다르면 `--ocr-gpu`, `--reason-gpu`, `--reason-parallel` 로 바꾼다.

## 4. 자주 나는 문제

| 증상 | 해결 |
|---|---|
| `uv: command not found` / `'uv' 은(는) ... 아닙니다` | uv 설치 후 터미널을 새로 연다 |
| `ModuleNotFoundError: No module named 'cutplan_agent'` | 프로젝트 폴더에서 `PYTHONPATH=.` 를 주고 실행했는지 확인 (2절) |
| `ModuleNotFoundError: No module named 'dotenv'` 등 | `uv sync` 를 다시 실행하고, `python` 대신 `uv run python` 으로 실행했는지 확인 |
| `Could not resolve authentication method` / API 키 오류 | `.env` 의 `ANTHROPIC_API_KEY` 확인 (파일 이름이 `.env.txt` 가 아닌지도) |
| `This API key is not scoped to a workspace` | `.env` 에 `ANTHROPIC_WORKSPACE_ID` 추가 (`cutplan_agent/client.py` 참조) |
| `dwg2dxf 실패` | 3절의 dwg2dxf 설치 확인 |
| vLLM 이 `libnvrtc.so.13: cannot open shared object file` 로 죽음 | `torchcodec` 을 CPU 판으로 바꾼다 (3절 로컬 모델) |
| vLLM 이 `No such file or directory: 'ninja'` 로 죽음 | FlashInfer sampler 의 JIT 컴파일이다. `VLLM_USE_FLASHINFER_SAMPLER=0` 으로 끈다. `experiments.sh` 는 기본으로 끈다 |
| vLLM 이 `No available memory for the cache blocks` 로 죽음 | 모델 weight 가 GPU 메모리 비율을 거의 다 쓴 것이다. GPU 를 더 주거나 `--reason-vllm-arg=--gpu-memory-utilization=…` 를 올린다 |
