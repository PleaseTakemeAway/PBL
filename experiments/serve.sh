#!/usr/bin/env bash
set -euo pipefail

# Start the reader's local vLLM servers and keep them up until Ctrl-C, so that
# main.py, the stage scripts and experiments.sh can run against them many times.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
. "$script_dir/vllm_common.sh"
serve_dir="${CUTPLAN_SERVE_DIR:-$repo_root/runs/vllm}"
roles=()
env_files=()

usage() {
  cat <<'EOF'
Usage: bash serve.sh [options] [ocr] [reason]
Start local vLLM servers and keep them running until Ctrl-C. With no role named,
start both: DeepSeek-OCR-2 on GPU 0 (port 8000) and Qwen3.6-27B pipelined over
GPUs 1,2,3 (port 8001), with the same vLLM settings as experiments.sh.

When a server is ready, SERVE_DIR/ROLE.env is written; it is removed on exit.
Source it in another shell, at the repo root, to use the running servers:
  . runs/vllm/ocr.env; . runs/vllm/reason.env
  PYTHONPATH=. python cutplan_agent/reader/stages/run.py DXF WORK_DIR
  PYTHONPATH=. python cutplan_agent/reader/main.py --batch --input-mode dxf ...
  ./experiments/experiments.sh --output-dir runs/reader/NEW_DIR
The files set CUTPLAN_ROLE_MODE=api, so experiments.sh starts no server for a
sourced role.

Role options (replace ROLE with ocr or reason):
  --ROLE-model MODEL           Model ID for that role.
  --ROLE-gpu IDS               GPU IDs, e.g. 0 or 1,2,3; count sets the parallel size.
  --ROLE-parallel tensor|pipeline
  --ROLE-port PORT             Local server port (OCR 8000, reason 8001).
  --reason-output-format prompt|json_schema
                               Written to reason.env (default json_schema).
  --ROLE-vllm-arg ARG          Repeat to append vLLM options; use = for flags:
                               --reason-vllm-arg=--max-num-seqs=8

Other options:
  --serve-dir DIR             Server logs and .env files (default runs/vllm).
  --vllm-bin PATH             vLLM executable.
  --startup-timeout SECONDS   Health-check timeout (default 7200).
  --allow-shared-gpus         Permit overlapping GPU IDs; memory is not split for you.
  --dry-run                   Print the vLLM commands; start nothing.
  -h, --help                  Show help.

The matching CUTPLAN_ROLE_* environment variables also work, as in experiments.sh.
CUTPLAN_ROLE_MODE is ignored: this script only starts local servers.
EOF
}

# The reader reads these variables (vlm.py). MODE is for experiments.sh, and the
# empty API key keeps vlm.py from sending OPENAI_API_KEY to the local server.
write_env_file() {
  local role="$1"
  local -n config="$role"
  local prefix="CUTPLAN_${role^^}_"
  local file="$serve_dir/$role.env"
  {
    echo "# experiments/serve.sh: $role vLLM server. Removed when the server stops."
    printf 'export %s=%q\n' \
      "${prefix}MODE" api \
      "${prefix}PROVIDER" "${config[provider]}" \
      "${prefix}MODEL" "${config[model]}" \
      "${prefix}BASE_URL" "${config[base_url]}" \
      "${prefix}OUTPUT_FORMAT" "${config[output_format]}"
    echo "export ${prefix}API_KEY="
  } >"$file.tmp"
  mv "$file.tmp" "$file"
  env_files+=("$file")
  echo "  . ${file#"$repo_root"/}"
}

cleanup() {
  local file
  for file in "${env_files[@]}"; do
    rm -f "$file"
  done
  cleanup_servers
}

while (( $# )); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) dry_run=1; shift; continue ;;
    --allow-shared-gpus) allow_shared_gpus=1; shift; continue ;;
    ocr|reason)
      [[ " ${roles[*]} " == *" $1 "* ]] || roles+=("$1")
      shift; continue ;;
    --*) parse_option_value "$@"; shift "$option_shift" ;;
    *) die "unknown argument: $1 (roles are ocr and reason; see --help)" ;;
  esac
  case "$option" in
    --ocr-mode|--reason-mode|--ocr-provider|--reason-provider|--ocr-base-url|--reason-base-url|--ocr-api-key-env|--reason-api-key-env)
      die "$option does not apply: serve.sh only starts local vLLM servers" ;;
    --ocr-*|--reason-*) set_role_flag "$option" "$value" ;;
    --serve-dir) serve_dir="$value" ;;
    --vllm-bin) vllm_bin="$value" ;;
    --startup-timeout) startup_timeout="$value" ;;
    *) die "unknown option: $option (see --help)" ;;
  esac
done
(( ${#roles[@]} )) || roles=(ocr reason)

check_server_settings
for role in "${roles[@]}"; do
  set_role_option "$role" mode local
  configure_role "$role"
done
(( ${#roles[@]} < 2 )) || check_local_overlap

for role in "${roles[@]}"; do
  print_role "$role"
done
if (( dry_run )); then
  echo "Dry run: no servers will be started."
  for role in "${roles[@]}"; do
    server_command "$role"
    printf '%s: ' "$role"
    printf '%q ' env "${server_env[@]}" "$vllm_bin" "${server_argv[@]}"
    printf '\n'
  done
  exit 0
fi

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

server_log_dir="$serve_dir"
for role in "${roles[@]}"; do
  start_server "$role"
  write_env_file "$role"
done
echo "Servers are running. Source the files above in another shell; Ctrl-C stops them."

# Stay up until a server stops or this script is interrupted.
status=0
wait -n || status=$?
for i in "${!server_pids[@]}"; do
  if ! kill -0 "${server_pids[i]}" 2>/dev/null; then
    role="${server_roles[i]}"
    tail -n 70 "$server_log_dir/${role}_vllm.log" >&2
    die "$role vLLM stopped (exit status $status); inspect $server_log_dir/${role}_vllm.log"
  fi
done
die "a vLLM server stopped (exit status $status)"
