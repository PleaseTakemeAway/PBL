#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
main_py="$repo_root/cutplan_agent/reader/main.py"
# cutplan_agent 는 설치하지 않는 패키지라 레포 루트를 import 경로에 넣는다
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"

: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY before running this script}"

export CUTPLAN_OCR_PROVIDER="anthropic"
export CUTPLAN_OCR_BASE_URL="https://api.anthropic.com"
export CUTPLAN_OCR_MODEL="claude-haiku-4-5-20251001"
export CUTPLAN_OCR_API_KEY="$ANTHROPIC_API_KEY"

export CUTPLAN_REASON_PROVIDER="anthropic"
export CUTPLAN_REASON_BASE_URL="https://api.anthropic.com"
export CUTPLAN_REASON_MODEL="claude-sonnet-5"
export CUTPLAN_REASON_API_KEY="$ANTHROPIC_API_KEY"

output_dir="$repo_root/runs/reader/data_v3_claude_batch_10141611"
if (( $# == 0 )); then
  set -- "$repo_root/data_v3/synthetic"
fi

python3 "$main_py" \
  "$@" \
  --batch \
  --input-mode dxf \
  --output-dir "$output_dir"
