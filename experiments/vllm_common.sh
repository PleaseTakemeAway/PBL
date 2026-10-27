# Shared by experiments.sh and serve.sh: the two model roles (ocr, reason), their
# validation, and the local vLLM server lifecycle. Source this file; do not run it.
# The caller sets server_log_dir before start_server and may set dry_run=1.

# A role's settings come in layers, each overriding the one before:
#   1. the role defaults below (ports, output format, where the role runs),
#   2. the model profile, experiments/models/NAME.sh (model ID, vLLM limits),
#   3. CUTPLAN_ROLE_* environment variables,
#   4. CLI flags.
# load_role applies them. API keys stay in the environment.
models_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/models"
role_fields=(mode model gpu parallel port provider base_url api_key_env output_format trust_remote_code)
declare -A ocr=(
  [profile]="${CUTPLAN_OCR_PROFILE:-deepseek-ocr-2}"
  [mode]=local
  [model]=""
  [gpu]=0
  [parallel]=tensor
  [port]=8000
  [provider]=openai
  [base_url]=""
  [api_key_env]=""
  [output_format]=raw
  [trust_remote_code]=0
)
declare -A reason=(
  [profile]="${CUTPLAN_REASON_PROFILE:-qwen3.6-27b}"
  [mode]=local
  [model]=""
  [gpu]=1
  [parallel]=tensor
  [port]=8001
  [provider]=openai
  [base_url]=""
  [api_key_env]=""
  [output_format]=json_schema
  [trust_remote_code]=0
)
# CLI values, kept apart until load_role puts them on top.
declare -A ocr_cli=() reason_cli=()
ocr_cli_vllm_args=()
reason_cli_vllm_args=()
# vLLM options a role needs whatever the model: json_schema output needs XGrammar.
# Without disable_any_whitespace the grammar lets the model fill the reply with
# blank lines until max_tokens cuts the JSON (docs/v3_upgrade.md 4절 #13).
ocr_role_vllm_args=()
reason_role_vllm_args=(--structured-outputs-config.backend=xgrammar
                       --structured-outputs-config.disable_any_whitespace=true)
# Final vLLM options, set by load_role: profile, then role, then CLI. Repeated
# --*-vllm-arg options come last and can override any of these values.
ocr_vllm_args=()
reason_vllm_args=()
vllm_bin="${CUTPLAN_VLLM_BIN:-vllm}"
startup_timeout="${CUTPLAN_VLLM_STARTUP_TIMEOUT:-7200}"
allow_shared_gpus="${CUTPLAN_ALLOW_SHARED_GPUS:-0}"
dry_run=0
server_pids=()
server_roles=()

die() { echo "error: $*" >&2; exit 2; }

# Split "--name=value" or "--name value" into $option and $value and set
# $option_shift to the number of arguments used.
parse_option_value() {
  option="${1%%=*}"
  if [[ "$1" == *=* ]]; then
    value="${1#*=}"
    option_shift=1
  else
    (( $# >= 2 )) || die "$1 requires a value"
    # A vLLM argument may itself start with --; other option values may not.
    [[ "$2" != --* || "$option" == *-vllm-arg ]] || die "$1 requires a value"
    value="$2"
    option_shift=2
  fi
  [[ -n "$value" ]] || die "$option requires a nonempty value"
}

set_role_option() {
  local -n cli="${1}_cli"
  case "$2" in
    profile|mode|model|gpu|parallel|port|provider|base_url|api_key_env|output_format) cli["$2"]="$3" ;;
    vllm_arg)
      local -n extra_args="${1}_cli_vllm_args"
      extra_args+=("$3")
      ;;
    *) die "unknown option: --${1}-${2//_/-}" ;;
  esac
}

# --ocr-FIELD or --reason-FIELD with its value.
set_role_flag() {
  local role="${1#--}"
  role="${role%%-*}"
  local field="${1#--$role-}"
  set_role_option "$role" "${field//-/_}" "$2"
}

# Print the profile names in experiments/models.
list_profiles() {
  local file
  for file in "$models_dir"/*.sh; do
    [[ -e "$file" ]] || continue
    file="${file##*/}"
    echo "  ${file%.sh}"
  done
}

# Apply the profile, environment and CLI layers to a role. A profile is a name
# in experiments/models or a path to a file of the same form. It may set any
# role field and the array vllm_args; config[profile_mode] records the mode the
# profile itself set, so serve.sh can refuse an API-only profile.
load_role() {
  local _role="$1"
  local -n _config="$_role"
  local -n _cli="${_role}_cli"
  local -n _role_args="${_role}_role_vllm_args"
  local -n _cli_args="${_role}_cli_vllm_args"
  local -n _final_args="${_role}_vllm_args"
  local _profile="${_cli[profile]:-${_config[profile]}}"
  local _file _field _variable
  local mode model gpu parallel port provider base_url api_key_env output_format trust_remote_code
  local -a vllm_args=()
  if [[ "$_profile" == */* || "$_profile" == *.sh ]]; then
    _file="$_profile"
  else
    _file="$models_dir/$_profile.sh"
  fi
  if [[ ! -f "$_file" ]]; then
    echo "error: $_role profile not found: $_profile. Profiles in experiments/models:" >&2
    list_profiles >&2
    exit 2
  fi
  . "$_file"
  _config[profile]="$_profile"
  _config[profile_mode]="${mode:-}"
  for _field in "${role_fields[@]}"; do
    [[ -z "${!_field:-}" ]] || _config[$_field]="${!_field}"
  done
  for _field in "${role_fields[@]}"; do
    _variable="CUTPLAN_${_role^^}_${_field^^}"
    [[ -z "${!_variable:-}" ]] || _config[$_field]="${!_variable}"
  done
  for _field in "${!_cli[@]}"; do
    _config[$_field]="${_cli[$_field]}"
  done
  _final_args=("${vllm_args[@]}" "${_role_args[@]}" "${_cli_args[@]}")
}

check_server_settings() {
  [[ "$startup_timeout" =~ ^[1-9][0-9]{0,7}$ ]] || die "startup-timeout must be positive seconds"
  [[ "$allow_shared_gpus" == 0 || "$allow_shared_gpus" == 1 ]] || die "CUTPLAN_ALLOW_SHARED_GPUS must be 0 or 1"
}

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
    [[ "${config[parallel]}" == tensor || "${config[parallel]}" == pipeline ]] || die "$role parallel must be tensor or pipeline"
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

# Two local roles must not share a port or, unless allowed, a GPU.
check_local_overlap() {
  local gpu
  [[ "${ocr[port]}" != "${reason[port]}" ]] || die "local OCR and reasoning need different ports"
  for gpu in ${ocr[gpu]//,/ }; do
    if [[ ",${reason[gpu]}," == *",$gpu,"* && "$allow_shared_gpus" != 1 ]]; then
      die "OCR and reasoning GPU lists overlap; choose different GPUs or use --allow-shared-gpus"
    fi
  done
}

print_role() {
  local -n config="$1"
  echo "$1: profile=${config[profile]} mode=${config[mode]} model=${config[model]} provider=${config[provider]} output_format=${config[output_format]}"
  if [[ "${config[mode]}" == local ]]; then
    echo "  GPUs=${config[gpu]} parallel=${config[parallel]} port=${config[port]}"
  else
    echo "  endpoint=${config[base_url]}"
  fi
}

# Fill server_env and server_argv with the environment and arguments of the
# vLLM process for a local role, and server_size with its number of GPUs.
server_command() {
  local role="$1"
  local -n config="$role"
  local -n extra_args="${role}_vllm_args"
  local ids=()
  IFS=',' read -r -a ids <<< "${config[gpu]}"
  server_size="${#ids[@]}"
  # FlashInfer's sampler is JIT-compiled with nvcc on first use and fails where no
  # CUDA toolkit matches the wheel. vlm.py samples at temperature 0, so vLLM's
  # PyTorch sampler gives the same greedy output.
  server_env=(
    "CUDA_VISIBLE_DEVICES=${config[gpu]}"
    "VLLM_ENGINE_READY_TIMEOUT_S=${VLLM_ENGINE_READY_TIMEOUT_S:-$startup_timeout}"
    "VLLM_USE_FLASHINFER_SAMPLER=${VLLM_USE_FLASHINFER_SAMPLER:-0}"
    "TRITON_ALLOW_NON_CONSTEXPR_GLOBALS=${TRITON_ALLOW_NON_CONSTEXPR_GLOBALS:-${CUTPLAN_TRITON_ALLOW_NON_CONSTEXPR_GLOBALS:-1}}"
  )
  server_argv=(serve "${config[model]}" --host 127.0.0.1 --port "${config[port]}" "--${config[parallel]}-parallel-size" "$server_size")
  [[ "${config[trust_remote_code]}" != 1 ]] || server_argv+=(--trust-remote-code)
  server_argv+=("${extra_args[@]}")
}

cleanup_servers() {
  local pid
  for pid in "${server_pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}

start_server() {
  local role="$1"
  local -n config="$role"
  local log_file="$server_log_dir/${role}_vllm.log"
  local deadline=$((SECONDS + startup_timeout))
  local next_notice=$((SECONDS + 30))
  local pid
  command -v "$vllm_bin" >/dev/null 2>&1 || die "vLLM executable not found: $vllm_bin"
  command -v curl >/dev/null 2>&1 || die "curl is required for local vLLM health checks"
  if curl --silent --max-time 1 "http://127.0.0.1:${config[port]}/health" >/dev/null 2>&1; then
    die "port ${config[port]} already has a server; choose --${role}-port or use api mode"
  fi
  server_command "$role"
  mkdir -p "$server_log_dir"
  echo "Starting $role vLLM: GPU=${config[gpu]}, ${config[parallel]} parallel=$server_size; log=$log_file"
  env "${server_env[@]}" "$vllm_bin" "${server_argv[@]}" >"$log_file" 2>&1 &
  pid=$!
  server_pids+=("$pid")
  server_roles+=("$role")
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
