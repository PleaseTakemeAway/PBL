#!/usr/bin/env bash
# 도면 1장을 판독 13단계로 나눠 차례로 돌리고, 단계마다 결과를 파일로 남긴다.
# 단계 결과는 <작업 폴더>/stages/NN_<단계>.json, 그림은 <작업 폴더>/analysis/ 에 생긴다.
# 단계별로 읽는 것과 남기는 것은 docs/reader/stages.md 에 있다.
#
# 사용: ./experiments/run_stages.sh [DXF 파일] [작업 폴더]
#   기본값은 data_v3/synthetic/cone_0019/cone_0019.dxf 와 runs/reader/check/<도면 이름>
#   NO_VLM=1 이면 모델 없이 돈다. 모델 단계(03, 04, 06, 09, 12)는 skipped 로 남는다.
#   모델 서버(OCR 8000, 추론 8001)는 ./experiments/serve.sh 로 미리 띄워 둔다. 이 스크립트는 서버를 띄우지 않는다.
#   serve.sh 가 쓴 runs/vllm/*.env 를 source 했으면 그 모델과 주소를 쓴다.
#
# 한 단계씩 손으로 돌리려면 레포 루트에서 '준비'와 '서버 확인' 블록을 셸에 붙여 넣고,
# 원하는 단계 줄만 실행한다.
# 단계는 앞 단계가 남긴 파일을 읽으므로 처음에는 01 부터 순서대로 돌린다.
# 한 단계를 다시 돌리면 그 뒤 단계의 stages/ 파일은 지워진다.
# 파이썬 명령과 옵션은 bash 와 zsh 둘 다에서 되도록 배열("${PY[@]}", "${O[@]}")로 넘긴다.
set -euo pipefail

# ---- 준비 ----
# 레포 루트로 이동한다 (스크립트 위치 기준, 붙여 넣을 때는 현재 폴더 기준)
cd "$(git -C "$(dirname -- "${BASH_SOURCE[0]:-.}")" rev-parse --show-toplevel)"
# cutplan_agent 는 설치하지 않는 패키지라 레포 루트를 import 경로에 넣는다
export PYTHONPATH=.
# 판독기를 돌릴 파이썬. 기본은 레포의 uv 환경이고, CUTPLAN_PYTHON 에 다른 파이썬 경로를 줄 수 있다
if [[ -n "${CUTPLAN_PYTHON:-}" ]]; then PY=("$CUTPLAN_PYTHON"); else PY=(uv run python); fi
# 판독할 DXF 도면
DXF="${1:-data_v3/synthetic/cone_0019/cone_0019.dxf}"
# 단계 결과를 쓸 작업 폴더
W="${2:-runs/reader/check/$(basename "$DXF" .dxf)}"
# OCR 모델과 서버 주소 (experiments.sh 기본값과 같다)
OCR_URL="${CUTPLAN_OCR_BASE_URL:-http://127.0.0.1:8000/v1}"
O=(--ocr-model "${CUTPLAN_OCR_MODEL:-deepseek-ai/DeepSeek-OCR-2}" --ocr-base-url "$OCR_URL")
# 추론 모델과 서버 주소 (experiments.sh 기본값과 같다)
REASON_URL="${CUTPLAN_REASON_BASE_URL:-http://127.0.0.1:8001/v1}"
R=(--reason-model "${CUTPLAN_REASON_MODEL:-Qwen/Qwen3.6-27B}" --reason-base-url "$REASON_URL")
# NO_VLM=1 이면 두 모델을 끈다
if [[ "${NO_VLM:-0}" == 1 ]]; then O=(--no-vlm); R=(--no-vlm); fi

# ---- 서버 확인 ----
# 모델 단계는 서버에 연결하지 못해도 done 으로 끝나고 실패는 trace 에만 남으므로, 단계 전에 둘 다 ok 인지 본다
servers=ok
# OCR 서버가 응답하는지 확인한다
curl -sf --max-time 3 -o /dev/null "$OCR_URL/models" && echo "ocr ok" || { echo "ocr 응답 없음: $OCR_URL"; servers=down; }
# 추론 서버가 응답하는지 확인한다
curl -sf --max-time 3 -o /dev/null "$REASON_URL/models" && echo "reason ok" || { echo "reason 응답 없음: $REASON_URL"; servers=down; }

# ---- 스크립트로 돌릴 때만 (붙여 넣지 않는다. exit 가 셸을 닫는다) ----
# 도면 파일이 없으면 멈춘다
[[ -f "$DXF" ]] || { echo "DXF 가 없다: $DXF" >&2; exit 2; }
# 모델을 쓰는데 서버가 응답하지 않으면 멈춘다 (NO_VLM=1 이면 그대로 돈다)
[[ "$servers" == ok || "${NO_VLM:-0}" == 1 ]] || { echo "./experiments/serve.sh 로 서버를 띄우거나 NO_VLM=1 로 돌린다" >&2; exit 2; }
echo "도면: $DXF"
echo "작업 폴더: $W"

# ---- 단계 ----
# 01 DXF 엔티티를 레이어와 상관없이 모두 읽는다 (모델 없음)
"${PY[@]}" cutplan_agent/reader/stages/read.py "$DXF" "$W"
# 02 표제란 위치를 찾고 정규식으로 필드를 읽는다 (모델 없음)
"${PY[@]}" cutplan_agent/reader/stages/title_regex.py "$W"
# 03 표제란 그림을 OCR 모델이 받아쓴다 → analysis/title_block.png
"${PY[@]}" cutplan_agent/reader/stages/title_ocr.py "$W" "${O[@]}"
# 04 추론 모델이 OCR 원문을 필드로 정리하고, 02 가 못 읽은 필드만 채운다
"${PY[@]}" cutplan_agent/reader/stages/title_fields.py "$W" "${R[@]}"
# 05 뷰 후보를 나누고 도면 종류(정투상/네스팅/기타)를 정한다 (모델 없음)
"${PY[@]}" cutplan_agent/reader/stages/views.py "$W"
# 06 추론 모델이 뷰 종류·투상법·형상·복원 가능 여부를 정한다 → analysis/sheet_labeled.png
"${PY[@]}" cutplan_agent/reader/stages/view_labels.py "$W" "${R[@]}"
# 07 01–06 을 합쳐 analysis/sheet_analysis.json 과 sheet.png 를 쓴다 (모델 없음)
"${PY[@]}" cutplan_agent/reader/stages/sheet.py "$W"
# 08 라벨 붙은 뷰를 3D 복원용 front/top/right 와 치수로 바꾼다 (모델 없음, 네스팅 도면은 여기서 멈춤)
"${PY[@]}" cutplan_agent/reader/stages/document.py "$W"
# 09 추론 모델이 형상별 전개 파라미터를 읽는다
"${PY[@]}" cutplan_agent/reader/stages/unfold_params.py "$W" "${R[@]}"
# 10 전개 공식을 코드로 계산하고 flat_pattern.json/.dxf/.png 를 쓴다 (모델 없음)
"${PY[@]}" cutplan_agent/reader/stages/develop.py "$W"
# 11 3D 와이어프레임 후보를 만들고 순위를 매긴다 (모델 없음, 06 이 복원 불가로 보면 건너뜀)
"${PY[@]}" cutplan_agent/reader/stages/reconstruct.py "$W"
# 12 추론 모델이 원래 뷰와 후보 투영을 비교해 하나를 고른다 → analysis/candidates.png
"${PY[@]}" cutplan_agent/reader/stages/confirm.py "$W" "${R[@]}"
# 13 provenance.json, report.md, 유효 후보가 있으면 reconstruction.step 을 쓴다 (모델 없음)
"${PY[@]}" cutplan_agent/reader/stages/export.py "$W"

# ---- 요약 ----
# 단계마다 상태와 건너뛴 이유·오류를 한 줄씩 출력한다
"${PY[@]}" - "$W" <<'EOF'
import json, pathlib, sys
for f in sorted(pathlib.Path(sys.argv[1], "stages").glob("*.json")):
    d = json.loads(f.read_text())
    print(f"{f.name:24s} {d['status']:8s} {d.get('reason') or d.get('error') or ''}")
EOF

# 한 단계부터 다시 돌리는 예: 06 부터 끝까지 (01–05 는 작업 폴더의 파일을 그대로 쓴다)
#   "${PY[@]}" cutplan_agent/reader/stages/run.py "$W" --from view_labels "${O[@]}" "${R[@]}"
# 모델 원문 응답은 stages/03, 04, 06, 09, 12 파일의 "trace" 에 있다
