#!/usr/bin/env bash
# Run reader main.py --batch on N disjoint subsets of the drawings at once, against
# vLLM servers that are already up (experiments/serve.sh). One server batches the
# requests of all subsets. Each subset writes <out>/shardK/; score the whole run with
#   uv run python scripts/reader/score_synthetic.py <out>
#
# usage: experiments/batch_parallel.sh <data dir> <out dir> [N=3] [main.py options ...]
# Run from anywhere; paths are taken relative to the current directory.
# The servers are read from runs/vllm/{ocr,reason}.env, or from CUTPLAN_SERVE_DIR
# when several serve.sh pairs run at once (serve.sh --serve-dir).
# More than 3 subsets made the shared Qwen3.6-27B server on mlic slower overall
# (docs/v3_upgrade.md 3.1절), so 3 is the default.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
data="$(realpath "$1")"
out="$(realpath -m "$2")"
n="${3:-3}"
shift $(( $# < 3 ? $# : 3 ))
serve_dir="${CUTPLAN_SERVE_DIR:-$repo_root/runs/vllm}"
for env in "$serve_dir/ocr.env" "$serve_dir/reason.env"; do
  if [[ -f "$env" ]]; then . "$env"; else echo "missing $env: start experiments/serve.sh first" >&2; exit 1; fi
done
# requests wait in the server queue while other subsets run; 120 s was not enough
export CUTPLAN_OCR_TIMEOUT="${CUTPLAN_OCR_TIMEOUT:-900}"
export CUTPLAN_REASON_TIMEOUT="${CUTPLAN_REASON_TIMEOUT:-900}"
mapfile -t dxfs < <(find "$data" -mindepth 2 -maxdepth 2 -name '*.dxf' | sort)
mkdir -p "$out"
cd "$repo_root"
pids=()
for ((k = 0; k < n; k++)); do
  part=()
  for ((i = k; i < ${#dxfs[@]}; i += n)); do part+=("${dxfs[i]}"); done
  ((${#part[@]})) || continue
  PYTHONPATH=. uv run python cutplan_agent/reader/main.py --batch --input-mode dxf \
    --overwrite "$@" --output-dir "$out/shard$k" "${part[@]}" >"$out/shard$k.log" 2>&1 &
  pids+=($!)
done
status=0
for pid in "${pids[@]}"; do wait "$pid" || status=1; done
echo "done: $out (logs $out/shard*.log)"
exit "$status"
