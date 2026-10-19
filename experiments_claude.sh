#!/usr/bin/env bash
set -euo pipefail

: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY before running this script}"

export CUTPLAN_OCR_PROVIDER="anthropic"
export CUTPLAN_OCR_BASE_URL="https://api.anthropic.com"
export CUTPLAN_OCR_MODEL="claude-haiku-4-5-20251001"
export CUTPLAN_OCR_API_KEY="$ANTHROPIC_API_KEY"

export CUTPLAN_REASON_PROVIDER="anthropic"
export CUTPLAN_REASON_BASE_URL="https://api.anthropic.com"
export CUTPLAN_REASON_MODEL="claude-sonnet-5"
export CUTPLAN_REASON_API_KEY="$ANTHROPIC_API_KEY"

output_dir="data_v3_claude_batch_10141611"
if (( $# == 0 )); then
  set -- /home/hwang/yechanhwang/PBL_2026/data_v3/synthetic
fi

python3 main.py \
  "$@" \
  --batch \
  --input-mode dxf \
  --output-dir "$output_dir"
