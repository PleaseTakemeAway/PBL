#!/usr/bin/env bash
set -euo pipefail

# Edit these two blocks, use CUTPLAN_* environment variables, or pass CLI flags.
# Precedence: CLI > environment > defaults below. API keys stay in the environment.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
main_py="$repo_root/cutplan_agent/reader/main.py"
# cutplan_agent 는 설치하지 않는 패키지라 레포 루트를 import 경로에 넣는다
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"
declare -A ocr=(
  [mode]="${CUTPLAN_OCR_MODE:-local}"
  [model]="${CUTPLAN_OCR_MODEL:-deepseek-ai/DeepSeek-OCR-2}"
  [gpu]="${CUTPLAN_OCR_GPU:-4}"
  [port]="${CUTPLAN_OCR_PORT:-8000}"
  [provider]="${CUTPLAN_OCR_PROVIDER:-openai}"
  [base_url]="${CUTPLAN_OCR_BASE_URL:-}"
  [api_key_env]=""
  [output_format]="${CUTPLAN_OCR_OUTPUT_FORMAT:-raw}"
)
declare -A reason=(
  [mode]="${CUTPLAN_REASON_MODE:-local}"
  [model]="${CUTPLAN_REASON_MODEL:-Qwen/Qwen3.6-27B}"
  [gpu]="${CUTPLAN_REASON_GPU:-5}"
  [port]="${CUTPLAN_REASON_PORT:-8001}"
  [provider]="${CUTPLAN_REASON_PROVIDER:-openai}"
  [base_url]="${CUTPLAN_REASON_BASE_URL:-}"
  [api_key_env]=""
  [output_format]="${CUTPLAN_REASON_OUTPUT_FORMAT:-json_schema}"
)
output_dir="${CUTPLAN_BATCH_OUTPUT:-$repo_root/runs/reader/deepseek_ocr_qwen_reasoning_skills}"
python_bin="${CUTPLAN_PYTHON:-python}"
vllm_bin="${CUTPLAN_VLLM_BIN:-vllm}"
startup_timeout="${CUTPLAN_VLLM_STARTUP_TIMEOUT:-7200}"
allow_shared_gpus="${CUTPLAN_ALLOW_SHARED_GPUS:-0}"
dry_run=0

# These limits fit the default models' sequential drawing workflow. Repeated
# --*-vllm-arg options are appended last and can override any of these values.
ocr_vllm_args=(--max-model-len=8192 --max-num-seqs=16 --gpu-memory-utilization=0.20)
reason_vllm_args=(--max-model-len=16384 --max-num-seqs=16 --gpu-memory-utilization=0.80
                  --structured-outputs-config.backend=xgrammar)
inputs=()
main_args=()
server_pids=()

usage() {
  cat <<'EOF'
Usage: bash experiments.sh [options] [DXF files/directories]
No arguments: local OCR on GPU 0 + local Qwen3.6-27B on GPU 1;
             process data_v3/synthetic as one batch.

Role options (replace ROLE with ocr or reason):
  --ROLE-mode local|api         local starts vLLM; api uses an existing endpoint.
  --ROLE-model MODEL           Model ID for that role.
  --ROLE-gpu IDS               GPU IDs, e.g. 4 or 4,5; count sets tensor parallelism.
  --ROLE-port PORT             Local server port (OCR 8000, reason 8001).
  --ROLE-provider openai|anthropic
  --ROLE-base-url URL          API URL (OpenAI-compatible URLs include /v1).
  --ROLE-api-key-env NAME      Read the API key from environment variable NAME.
  --reason-output-format prompt|json_schema
                               Default json_schema; local vLLM uses XGrammar.
                               prompt explicitly disables server constraints.
  --ocr-output-format raw      OCR always reads unrestricted text; old
                               prompt/json_schema values also resolve to raw.
  --ROLE-vllm-arg ARG          Repeat to append vLLM options; use = for flags:
                               --reason-vllm-arg=--max-num-seqs=16

Other options:
  --output-dir DIR            Batch output directory.
  --python PATH               Python executable.
  --vllm-bin PATH             vLLM executable.
  --startup-timeout SECONDS   Health-check timeout (default 7200).
  --allow-shared-gpus         Permit overlapping GPU IDs; memory is not split for you.
  --dry-run                   Print configuration; no servers or model/API calls.
  -h, --help                  Show help.

main.py options such as --overwrite, --analyze-only, --no-confirm, --no-unfold,
--no-recursive, --input-mode dxf|vision and --dpi N are also accepted.
Use -- before input paths that start with a hyphen.

Examples:
  bash experiments.sh --dry-run
  bash experiments.sh --ocr-gpu 4 --reason-gpu 5 /path/to/dxfs
  bash experiments.sh --ocr-mode local --ocr-gpu 4 \
    --reason-mode api --reason-provider anthropic --reason-model claude-sonnet-5 \
    --reason-api-key-env ANTHROPIC_API_KEY /path/to/dxfs
  bash experiments.sh --ocr-mode api --ocr-model YOUR_OCR_MODEL \
    --ocr-base-url https://your-openai-compatible-api/v1 \
    --ocr-api-key-env OCR_API_KEY --reason-mode local --reason-gpu 4 /path/to/dxfs

Keys: CUTPLAN_OCR_API_KEY / CUTPLAN_REASON_API_KEY take precedence over
OPENAI_API_KEY or ANTHROPIC_API_KEY; --ROLE-api-key-env overrides all of them.
Mode, model, GPU, port, provider, base URL and output format also accept
matching CUTPLAN_ROLE_* environment variables.
EOF
}

die() { echo "error: $*" >&2; exit 2; }

set_role_option() {
  local -n config="$1"
  case "$2" in
    mode|model|gpu|port|provider|base_url|api_key_env|output_format) config["$2"]="$3" ;;
    vllm_arg)
      local -n extra_args="${1}_vllm_args"
      extra_args+=("$3")
      ;;
    *) die "unknown option: --${1}-${2//_/-}" ;;
  esac
}

while (( $# )); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) dry_run=1; shift; continue ;;
    --allow-shared-gpus) allow_shared_gpus=1; shift; continue ;;
    --) shift; inputs+=("$@"); break ;;
    --batch|--overwrite|--no-recursive|--no-confirm|--analyze-only|--no-vlm|--no-unfold)
      main_args+=("$1"); shift; continue ;;
    --*)
      option="${1%%=*}"
      if [[ "$1" == *=* ]]; then
        value="${1#*=}"; shift
      else
        (( $# >= 2 )) || die "$1 requires a value"
        # A vLLM argument may itself start with --; other option values may not.
        [[ "$2" != --* || "$option" == *-vllm-arg ]] || die "$1 requires a value"
        value="$2"; shift 2
      fi
      [[ -n "$value" ]] || die "$option requires a nonempty value"
      ;;
    *) inputs+=("$1"); shift; continue ;;
  esac
  case "$option" in
    --ocr-*|--reason-*)
      role="${option#--}"; role="${role%%-*}"
      field="${option#--$role-}"
      set_role_option "$role" "${field//-/_}" "$value"
      ;;
    --output-dir) output_dir="$value" ;;
    --python) python_bin="$value" ;;
    --vllm-bin) vllm_bin="$value" ;;
    --startup-timeout) startup_timeout="$value" ;;
    --units|--tolerance|--max-candidates|--input-mode|--dxf-mode|--dpi|--work-dir|--projection)
      main_args+=("$option" "$value") ;;
    *) die "unknown option: $option (see --help)" ;;
  esac
done

# Validate both roles before starting either server. Only the final settings
# needed by vlm.py are exported; there are no duplicate scalar role variables.
configure_role() {
  local role="$1"
  local -n config="$role"
  local prefix="CUTPLAN_${role^^}_"
  local key_name="${prefix}API_KEY"
  local api_key=""
  local field
  [[ "${config[mode]}" != vllm ]] || config[mode]=local
  [[ "${config[mode]}" == local || "${config[mode]}" == api ]] || die "$role mode must be local or api"
  [[ -n "${config[model]}" ]] || die "$role model is required"
  if [[ "$role" == ocr ]]; then
    case "${config[output_format]}" in
      raw|prompt|json_schema) config[output_format]=raw ;;
      *) die "ocr output-format must be raw (legacy prompt/json_schema also accepted)" ;;
    esac
  else
    [[ "${config[output_format]}" == prompt || "${config[output_format]}" == json_schema ]] || die "$role output-format must be prompt or json_schema"
  fi
  if [[ "${config[mode]}" == local ]]; then
    config[gpu]="${config[gpu]//[[:space:]]/}"
    [[ "${config[gpu]}" =~ ^(0|[1-9][0-9]*)(,(0|[1-9][0-9]*))*$ ]] || die "$role GPU IDs must be comma-separated integers without leading zeroes"
    [[ "${config[port]}" =~ ^[0-9]{1,5}$ ]] && (( 10#${config[port]} >= 1 && 10#${config[port]} <= 65535 )) || die "$role port must be 1..65535"
    config[port]="$((10#${config[port]}))"
    config[provider]=openai
    config[base_url]="http://127.0.0.1:${config[port]}/v1"
  else
    case "${config[provider]}" in
      anthropic)
        config[base_url]="${config[base_url]:-https://api.anthropic.com}"
        api_key="${ANTHROPIC_API_KEY:-}"
        ;;
      openai)
        config[base_url]="${config[base_url]:-https://api.openai.com/v1}"
        api_key="${OPENAI_API_KEY:-}"
        ;;
      *) die "$role provider must be openai or anthropic" ;;
    esac
    api_key="${!key_name:-$api_key}"
    if [[ -n "${config[api_key_env]}" ]]; then
      key_name="${config[api_key_env]}"
      [[ "$key_name" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || die "invalid $role API-key variable name"
      api_key="${!key_name:-}"
      [[ -n "$api_key" || "$dry_run" == 1 ]] || die "API-key variable $key_name is empty or unset"
    fi
    if [[ "${config[provider]}" == anthropic || "${config[base_url]}" =~ ^https?://api\.openai\.com(/|$) ]]; then
      [[ -n "$api_key" || "$dry_run" == 1 ]] || die "$role API key is missing; set --${role}-api-key-env"
    fi
  fi
  for field in provider model base_url output_format; do
    export "${prefix}${field^^}=${config[$field]}"
  done
  export "${prefix}API_KEY=$api_key"
}

[[ "$startup_timeout" =~ ^[1-9][0-9]{0,7}$ ]] || die "startup-timeout must be positive seconds"
[[ "$allow_shared_gpus" == 0 || "$allow_shared_gpus" == 1 ]] || die "CUTPLAN_ALLOW_SHARED_GPUS must be 0 or 1"
configure_role ocr
configure_role reason
if [[ "${ocr[mode]}" == local && "${reason[mode]}" == local ]]; then
  [[ "${ocr[port]}" != "${reason[port]}" ]] || die "local OCR and reasoning need different ports"
  for gpu in ${ocr[gpu]//,/ }; do
    if [[ ",${reason[gpu]}," == *",$gpu,"* && "$allow_shared_gpus" != 1 ]]; then
      die "OCR and reasoning GPU lists overlap; choose different GPUs or use --allow-shared-gpus"
    fi
  done
fi
(( ${#inputs[@]} )) || inputs=("$repo_root/data_v3/synthetic")

for role in ocr reason; do
  declare -n config="$role"
  echo "$role: mode=${config[mode]} model=${config[model]} provider=${config[provider]} output_format=${config[output_format]}"
  if [[ "${config[mode]}" == local ]]; then
    echo "  GPUs=${config[gpu]} port=${config[port]}"
  else
    echo "  endpoint=${config[base_url]}"
  fi
done
unset -n config
if (( dry_run )); then
  echo "Dry run: no servers, API calls, or output files will be created."
  printf 'Batch command: '
  printf '%q ' "$python_bin" "$main_py" --batch --input-mode dxf --output-dir "$output_dir" "${main_args[@]}" "${inputs[@]}"
  printf '\n'
  exit 0
fi
command -v "$python_bin" >/dev/null 2>&1 || die "Python executable not found: $python_bin"

cleanup_servers() {
  local pid
  for pid in "${server_pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup_servers EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_server() {
  local role="$1"
  local -n config="$role"
  local -n extra_args="${role}_vllm_args"
  local ids=()
  local log_file="$output_dir/server_logs/${role}_vllm.log"
  local deadline=$((SECONDS + startup_timeout))
  local next_notice=$((SECONDS + 30))
  local trust_name="CUTPLAN_${role^^}_TRUST_REMOTE_CODE"
  local pid
  local -a args
  command -v "$vllm_bin" >/dev/null 2>&1 || die "vLLM executable not found: $vllm_bin"
  command -v curl >/dev/null 2>&1 || die "curl is required for local vLLM health checks"
  if curl --silent --max-time 1 "http://127.0.0.1:${config[port]}/health" >/dev/null 2>&1; then
    die "port ${config[port]} already has a server; choose --${role}-port or use api mode"
  fi
  IFS=',' read -r -a ids <<< "${config[gpu]}"
  args=(serve "${config[model]}" --host 127.0.0.1 --port "${config[port]}" --tensor-parallel-size "${#ids[@]}")
  [[ "${!trust_name:-0}" != 1 ]] || args+=(--trust-remote-code)
  mkdir -p "$output_dir/server_logs"
  echo "Starting $role vLLM: GPU=${config[gpu]}, TP=${#ids[@]}; log=$log_file"
  CUDA_VISIBLE_DEVICES="${config[gpu]}" \
    VLLM_ENGINE_READY_TIMEOUT_S="${VLLM_ENGINE_READY_TIMEOUT_S:-$startup_timeout}" \
    TRITON_ALLOW_NON_CONSTEXPR_GLOBALS="${TRITON_ALLOW_NON_CONSTEXPR_GLOBALS:-${CUTPLAN_TRITON_ALLOW_NON_CONSTEXPR_GLOBALS:-1}}" \
    "$vllm_bin" "${args[@]}" "${extra_args[@]}" >"$log_file" 2>&1 &
  pid=$!
  server_pids+=("$pid")
  while (( SECONDS < deadline )); do
    if ! kill -0 "$pid" 2>/dev/null; then
      tail -n 70 "$log_file" >&2
      die "$role vLLM exited during startup; inspect $log_file"
    fi
    if curl --fail --silent --max-time 1 "http://127.0.0.1:${config[port]}/health" >/dev/null 2>&1; then
      echo "$role vLLM ready: ${config[base_url]}"
      return
    fi
    if (( SECONDS >= next_notice )); then
      echo "Waiting for $role vLLM; log=$log_file"
      next_notice=$((SECONDS + 30))
    fi
    sleep 1
  done
  die "$role vLLM startup timed out; inspect $log_file"
}

for role in ocr reason; do
  declare -n config="$role"
  [[ "${config[mode]}" != local ]] || start_server "$role"
done
# An api role may intentionally reuse the other role's managed vLLM server.
for role in ocr reason; do
  declare -n config="$role"
  if [[ "${config[mode]}" == api && "${config[base_url]}" =~ ^https?://(localhost|127\.0\.0\.1|\[::1\])(:[0-9]+)?(/|$) ]]; then
    command -v curl >/dev/null 2>&1 || die "curl is required to check a loopback API endpoint"
    curl --silent --show-error --max-time 3 --output /dev/null "${config[base_url]%/}/models" || \
      die "$role API is unreachable: ${config[base_url]}; start the server or change --${role}-base-url"
  fi
done

"$python_bin" "$main_py" --batch --input-mode dxf --output-dir "$output_dir" "${main_args[@]}" "${inputs[@]}"
