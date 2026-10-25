#!/usr/bin/env bash
set -euo pipefail

# Role defaults live in vllm_common.sh and model settings in experiments/models.
# Precedence: CLI > CUTPLAN_* environment > model profile > role defaults.
# API keys stay in the environment.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
main_py="$repo_root/cutplan_agent/reader/main.py"
# cutplan_agent 는 설치하지 않는 패키지라 레포 루트를 import 경로에 넣는다
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"
. "$script_dir/vllm_common.sh"
output_dir="${CUTPLAN_BATCH_OUTPUT:-$repo_root/runs/reader/deepseek_ocr_qwen_reasoning_skills}"
python_bin="${CUTPLAN_PYTHON:-python}"
inputs=()
main_args=()

usage() {
  cat <<'EOF'
Usage: bash experiments.sh [options] [DXF files/directories]
No arguments: local OCR on GPU 0 + local Qwen3.6-27B pipelined over GPUs 1,2,3;
             process data_v3/synthetic as one batch.

Role options (replace ROLE with ocr or reason):
  --ROLE-profile NAME|FILE     Model profile: experiments/models/NAME.sh or a file
                               of that form. Default: OCR deepseek-ocr-2,
                               reason qwen3.6-27b. The flags below override it.
  --ROLE-mode local|api         local starts vLLM; api uses an existing endpoint.
  --ROLE-model MODEL           Model ID; keeps the profile's vLLM options.
  --ROLE-gpu IDS               GPU IDs, e.g. 0 or 1,2,3; count sets the parallel size.
  --ROLE-parallel tensor|pipeline
                               How vLLM splits the model over those GPUs.
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
  bash experiments.sh --reason-profile qwen3.6-27b-fp8 --reason-gpu 1,2 /path/to/dxfs
  bash experiments.sh --reason-profile qwen3.6-27b-fp8 --reason-mode api \
    --reason-base-url http://127.0.0.1:8001/v1 /path/to/dxfs
  bash experiments.sh --ocr-gpu 4 --reason-gpu 5 /path/to/dxfs
  bash experiments.sh --ocr-mode local --ocr-gpu 4 \
    --reason-mode api --reason-provider anthropic --reason-model claude-sonnet-5 \
    --reason-api-key-env ANTHROPIC_API_KEY /path/to/dxfs
  bash experiments.sh --ocr-mode api --ocr-model YOUR_OCR_MODEL \
    --ocr-base-url https://your-openai-compatible-api/v1 \
    --ocr-api-key-env OCR_API_KEY --reason-mode local --reason-gpu 4 /path/to/dxfs

Keys: CUTPLAN_OCR_API_KEY / CUTPLAN_REASON_API_KEY take precedence over
OPENAI_API_KEY or ANTHROPIC_API_KEY; --ROLE-api-key-env overrides all of them.
Profile, mode, model, GPU, parallel, port, provider, base URL, output format and
trust_remote_code also accept matching CUTPLAN_ROLE_* environment variables.
EOF
}

while (( $# )); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) dry_run=1; shift; continue ;;
    --allow-shared-gpus) allow_shared_gpus=1; shift; continue ;;
    --) shift; inputs+=("$@"); break ;;
    --batch|--overwrite|--no-recursive|--no-confirm|--analyze-only|--no-vlm|--no-unfold)
      main_args+=("$1"); shift; continue ;;
    --*) parse_option_value "$@"; shift "$option_shift" ;;
    *) inputs+=("$1"); shift; continue ;;
  esac
  case "$option" in
    --ocr-*|--reason-*) set_role_flag "$option" "$value" ;;
    --output-dir) output_dir="$value" ;;
    --python) python_bin="$value" ;;
    --vllm-bin) vllm_bin="$value" ;;
    --startup-timeout) startup_timeout="$value" ;;
    --units|--tolerance|--max-candidates|--input-mode|--dxf-mode|--dpi|--work-dir|--projection)
      main_args+=("$option" "$value") ;;
    *) die "unknown option: $option (see --help)" ;;
  esac
done

check_server_settings
load_role ocr
load_role reason
configure_role ocr
configure_role reason
if [[ "${ocr[mode]}" == local && "${reason[mode]}" == local ]]; then
  check_local_overlap
fi
(( ${#inputs[@]} )) || inputs=("$repo_root/data_v3/synthetic")

print_role ocr
print_role reason
if (( dry_run )); then
  echo "Dry run: no servers, API calls, or output files will be created."
  printf 'Batch command: '
  printf '%q ' "$python_bin" "$main_py" --batch --input-mode dxf --output-dir "$output_dir" "${main_args[@]}" "${inputs[@]}"
  printf '\n'
  exit 0
fi
command -v "$python_bin" >/dev/null 2>&1 || die "Python executable not found: $python_bin"

trap cleanup_servers EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

server_log_dir="$output_dir/server_logs"
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
