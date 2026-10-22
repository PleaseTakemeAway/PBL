#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
main_py="$repo_root/cutplan_agent/reader/main.py"
# cutplan_agent 는 설치하지 않는 패키지라 레포 루트를 import 경로에 넣는다
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"

# Local OpenAI-compatible VLM server settings (vLLM by default).
# Existing environment variables take precedence over these defaults.
: "${CUTPLAN_OCR_PROVIDER:=openai}"
: "${CUTPLAN_OCR_BASE_URL:=http://localhost:8000/v1}"
: "${CUTPLAN_OCR_MODEL:=deepseek-ai/DeepSeek-OCR-2}"
: "${CUTPLAN_REASON_PROVIDER:=openai}"
: "${CUTPLAN_REASON_BASE_URL:=http://localhost:8001/v1}"
: "${CUTPLAN_REASON_MODEL:=Qwen/Qwen3.6-27B}"
: "${CUTPLAN_BATCH_OUTPUT:=${CUTPLAN_LOCAL_OUTPUT:-$repo_root/runs/reader/data_v3_local_batch}}"
: "${CUTPLAN_PYTHON:=python}"
: "${CUTPLAN_VLLM_BIN:=vllm}"
: "${CUTPLAN_VLLM_STARTUP_TIMEOUT:=1800}"
: "${CUTPLAN_OCR_GPU:=0}"
: "${CUTPLAN_REASON_GPU:=1}"
: "${CUTPLAN_OCR_PORT:=8000}"
: "${CUTPLAN_REASON_PORT:=8001}"
: "${CUTPLAN_OCR_TRUST_REMOTE_CODE:=0}"
: "${CUTPLAN_REASON_TRUST_REMOTE_CODE:=0}"

# vLLM 0.31.0 imports LOG2E as a plain global in the DeepSeek-OCR-2 Triton
# kernel, while Triton 3.7 rejects non-constexpr globals by default.
: "${CUTPLAN_TRITON_ALLOW_NON_CONSTEXPR_GLOBALS:=1}"

ocr_gpu="$CUTPLAN_OCR_GPU"
reason_gpu="$CUTPLAN_REASON_GPU"
main_args=()
ocr_vllm_args=()
reason_vllm_args=(--structured-outputs-config.backend=xgrammar)

usage() {
  cat <<EOF
Usage: ./experiments_local.sh [wrapper options] [DXF files/directories] [main.py options]

Wrapper options:
  --ocr-gpu IDS      Start a dedicated vLLM OCR server on these GPU IDs.
  --reason-gpu IDS   Start a dedicated vLLM reasoning server on these GPU IDs.
  --ocr-vllm-arg X   Append one model-specific argument to the OCR server.
  --reason-vllm-arg X
                     Append one model-specific argument to the reasoning server.
  -h, --help         Show this help and the main.py options.

GPU IDs may also be supplied through CUTPLAN_OCR_GPU and CUTPLAN_REASON_GPU.
Comma-separated IDs automatically set vLLM tensor parallelism to their count.
Managed vLLM ports default to CUTPLAN_OCR_PORT=8000 and
CUTPLAN_REASON_PORT=8001. Servers started by this script stop on exit.
Set CUTPLAN_VLLM_BIN to a vLLM executable in another virtual environment.
CUTPLAN_TRITON_ALLOW_NON_CONSTEXPR_GLOBALS defaults to 1 for the
vLLM 0.31 / Triton 3.7 DeepSeek-OCR-2 compatibility workaround.

Examples:
  ./experiments_local.sh --ocr-gpu 4 --reason-gpu 5 /path/to/dataset
  ./experiments_local.sh --ocr-gpu 4 --reason-gpu 5,6 /path/to/dataset
  ./experiments_local.sh --ocr-gpu 4 --ocr-vllm-arg=--max-model-len=8192 /path/to/dataset
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --ocr-gpu)
      (( $# >= 2 )) || { echo "--ocr-gpu requires a GPU ID" >&2; exit 2; }
      [[ -n "$2" && "$2" != --* ]] || { echo "--ocr-gpu requires a GPU ID" >&2; exit 2; }
      ocr_gpu="$2"
      shift 2
      ;;
    --ocr-gpu=*)
      ocr_gpu="${1#*=}"
      [[ -n "$ocr_gpu" ]] || { echo "--ocr-gpu requires a GPU ID" >&2; exit 2; }
      shift
      ;;
    --reason-gpu)
      (( $# >= 2 )) || { echo "--reason-gpu requires a GPU ID" >&2; exit 2; }
      [[ -n "$2" && "$2" != --* ]] || { echo "--reason-gpu requires a GPU ID" >&2; exit 2; }
      reason_gpu="$2"
      shift 2
      ;;
    --reason-gpu=*)
      reason_gpu="${1#*=}"
      [[ -n "$reason_gpu" ]] || { echo "--reason-gpu requires a GPU ID" >&2; exit 2; }
      shift
      ;;
    --ocr-vllm-arg)
      (( $# >= 2 )) || { echo "--ocr-vllm-arg requires one vLLM argument" >&2; exit 2; }
      ocr_vllm_args+=("$2")
      shift 2
      ;;
    --ocr-vllm-arg=*)
      ocr_vllm_args+=("${1#*=}")
      shift
      ;;
    --reason-vllm-arg)
      (( $# >= 2 )) || { echo "--reason-vllm-arg requires one vLLM argument" >&2; exit 2; }
      reason_vllm_args+=("$2")
      shift 2
      ;;
    --reason-vllm-arg=*)
      reason_vllm_args+=("${1#*=}")
      shift
      ;;
    -h|--help)
      usage
      echo
      "$CUTPLAN_PYTHON" "$main_py" --help
      exit 0
      ;;
    --)
      shift
      main_args+=("$@")
      break
      ;;
    *)
      main_args+=("$1")
      shift
      ;;
  esac
done

[[ "$CUTPLAN_OCR_PORT" =~ ^[0-9]+$ ]] || { echo "CUTPLAN_OCR_PORT must be a number" >&2; exit 2; }
[[ "$CUTPLAN_REASON_PORT" =~ ^[0-9]+$ ]] || { echo "CUTPLAN_REASON_PORT must be a number" >&2; exit 2; }
[[ "$CUTPLAN_VLLM_STARTUP_TIMEOUT" =~ ^[0-9]+$ ]] || { echo "CUTPLAN_VLLM_STARTUP_TIMEOUT must be seconds" >&2; exit 2; }

server_pids=()
cleanup_servers() {
  local pid
  for pid in "${server_pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup_servers EXIT INT TERM

gpu_count() {
  local value="${1//[[:space:]]/}"
  local ids=()
  local id
  IFS=',' read -r -a ids <<< "$value"
  (( ${#ids[@]} > 0 )) || return 1
  for id in "${ids[@]}"; do
    [[ -n "$id" ]] || return 1
  done
  printf '%s\n' "${#ids[@]}"
}

start_vllm_server() {
  local role="$1"
  local gpu="$2"
  local port="$3"
  local model="$4"
  local log_dir="$CUTPLAN_BATCH_OUTPUT/server_logs"
  local log_file="$log_dir/${role}_vllm.log"
  local tensor_parallel_size
  local trust_remote_code
  local elapsed
  local pid
  local -a vllm_args

  tensor_parallel_size="$(gpu_count "$gpu")" || {
    echo "Invalid ${role} GPU list: ${gpu}" >&2
    exit 2
  }
  command -v "$CUTPLAN_VLLM_BIN" >/dev/null 2>&1 || {
    echo "vLLM executable not found: ${CUTPLAN_VLLM_BIN}" >&2
    echo "Install vLLM or set CUTPLAN_VLLM_BIN=/path/to/venv/bin/vllm" >&2
    exit 2
  }
  command -v curl >/dev/null 2>&1 || {
    echo "curl was not found in PATH; it is required for the managed vLLM health check" >&2
    exit 2
  }
  if curl --silent --max-time 1 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    echo "Port ${port} already has an HTTP server; choose another CUTPLAN_${role^^}_PORT" >&2
    exit 2
  fi

  mkdir -p "$log_dir"
  echo "Starting ${role} vLLM server: model=${model}, GPU=${gpu}, TP=${tensor_parallel_size}, port=${port}"
  trust_remote_code="CUTPLAN_${role^^}_TRUST_REMOTE_CODE"
  vllm_args=(
    serve "$model"
    --host 127.0.0.1
    --port "$port"
    --tensor-parallel-size "$tensor_parallel_size"
  )
  if [[ "${!trust_remote_code}" == "1" ]]; then
    vllm_args+=(--trust-remote-code)
  fi
  if [[ "$role" == "ocr" ]]; then
    vllm_args+=("${ocr_vllm_args[@]}")
  else
    vllm_args+=("${reason_vllm_args[@]}")
  fi
  CUDA_VISIBLE_DEVICES="$gpu" \
    TRITON_ALLOW_NON_CONSTEXPR_GLOBALS="$CUTPLAN_TRITON_ALLOW_NON_CONSTEXPR_GLOBALS" \
    "$CUTPLAN_VLLM_BIN" "${vllm_args[@]}" \
    >"$log_file" 2>&1 &
  pid=$!
  server_pids+=("$pid")

  for ((elapsed=0; elapsed<CUTPLAN_VLLM_STARTUP_TIMEOUT; elapsed++)); do
    if curl --fail --silent --max-time 1 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      echo "${role} vLLM server is ready: http://127.0.0.1:${port}/v1"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "${role} vLLM server exited during startup; inspect ${log_file}" >&2
      grep -nE "CompilationError|NameError|OutOfMemoryError|CUDA out of memory|ValueError|RuntimeError|not supported|requires CUDA" \
        "$log_file" | tail -n 30 >&2 || true
      echo "--- final log lines ---" >&2
      tail -n 30 "$log_file" >&2 || true
      exit 2
    fi
    if (( elapsed > 0 && elapsed % 30 == 0 )); then
      echo "Waiting for ${role} vLLM model to load (${elapsed}s); log=${log_file}"
    fi
    sleep 1
  done
  echo "Timed out waiting for ${role} vLLM server; inspect ${log_file}" >&2
  exit 2
}

if [[ -n "$ocr_gpu" && -n "$reason_gpu" && "$CUTPLAN_OCR_PORT" == "$CUTPLAN_REASON_PORT" ]]; then
  echo "OCR and reasoning vLLM servers require different ports" >&2
  exit 2
fi

if [[ -n "$ocr_gpu" ]]; then
  start_vllm_server "ocr" "$ocr_gpu" "$CUTPLAN_OCR_PORT" "$CUTPLAN_OCR_MODEL"
  CUTPLAN_OCR_PROVIDER="openai"
  CUTPLAN_OCR_BASE_URL="http://127.0.0.1:${CUTPLAN_OCR_PORT}/v1"
fi
if [[ -n "$reason_gpu" ]]; then
  start_vllm_server "reason" "$reason_gpu" "$CUTPLAN_REASON_PORT" "$CUTPLAN_REASON_MODEL"
  CUTPLAN_REASON_PROVIDER="openai"
  CUTPLAN_REASON_BASE_URL="http://127.0.0.1:${CUTPLAN_REASON_PORT}/v1"
fi

export CUTPLAN_OCR_PROVIDER CUTPLAN_OCR_BASE_URL CUTPLAN_OCR_MODEL
export CUTPLAN_REASON_PROVIDER CUTPLAN_REASON_BASE_URL CUTPLAN_REASON_MODEL
export CUTPLAN_OCR_OUTPUT_FORMAT=raw
export CUTPLAN_REASON_OUTPUT_FORMAT="${CUTPLAN_REASON_OUTPUT_FORMAT:-json_schema}"

# With no arguments, process the complete synthetic DXF dataset. Otherwise,
# every supplied DXF file/directory is discovered and processed as one batch.
if (( ${#main_args[@]} == 0 )); then
  main_args=("$repo_root/data_v3/synthetic")
fi

"$CUTPLAN_PYTHON" "$main_py" \
  "${main_args[@]}" \
  --batch \
  --input-mode dxf \
  --output-dir "$CUTPLAN_BATCH_OUTPUT"
