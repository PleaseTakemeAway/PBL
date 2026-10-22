"""판독 단계를 번호로 골라 실행한다. 단계는 show_stages.py 와 같은 방식으로 고른다.

사용 (레포 루트에서):
  PYTHONPATH=. uv run python scripts/reader/run_stages.py <작업 폴더> [단계 ...] [--dxf <도면.dxf>] [--show]
  PYTHONPATH=. uv run python scripts/reader/run_stages.py <작업 폴더> 0 --drawing <도면.dwg 또는 .dxf>

  단계는 번호(6), 이름(view_labels), 범위(6-9, 0-13)로 준다. 없으면 1–13 전부 (--drawing 을 주면 0–13).
  00(convert)은 DWG 를 dwg2dxf 로 DXF 로 바꾸고 (DXF 는 그대로) 열리는지 검사한다. --drawing 으로 도면을 준다.
  01(read)은 --dxf 로 도면을 준다. 00 이 있으면 00 의 DXF 를 읽고, 01 결과가 있으면 그때 읽은 도면을 다시 쓴다.
  --show  돌린 단계를 show_stages.py 로 바로 보여 준다 (표와 그림).
  모델은 runs/vllm/*.env 를 source 하거나 --ocr-model, --reason-model 등으로 정한다. --no-vlm 이면 모델 없이.
  그 밖의 옵션(--no-vlm, --analyze-only, --tolerance ...)은 cutplan_agent/reader/stages/run.py 에 그대로 넘긴다.

이어지는 단계(6-9)는 run.py --from 6 --to 9 한 번으로 돈다. 단계를 다시 돌리면 그 뒤 단계 파일은
지워지므로, 6 9 처럼 떨어진 단계를 주면 9 는 08 이 없어서 멈춘다.
"""

import argparse
import json
import sys
from pathlib import Path

from cutplan_agent.reader.stages import convert
from cutplan_agent.reader.stages import run as runner
from cutplan_agent.reader.stages.workspace import CONVERT, STAGES, Workspace
from scripts.reader.show_stages import STAGE_NAMES, parse_steps, report

# run.py 에 그대로 넘기는 옵션
VALUE_OPTIONS = [
    "--ocr-model",
    "--ocr-base-url",
    "--ocr-provider",
    "--reason-model",
    "--reason-base-url",
    "--reason-provider",
    "--units",
    "--tolerance",
    "--max-candidates",
    "--projection",
]
FLAG_OPTIONS = ["--no-vlm", "--analyze-only", "--no-unfold", "--no-confirm"]


def groups(steps: list[int]) -> list[tuple[int, int]]:
    """[1, 2, 3, 6, 7] -> [(1, 3), (6, 7)]"""
    out: list[tuple[int, int]] = []
    for n in steps:
        if out and out[-1][1] == n - 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def previous_dxf(work: Path) -> str | None:
    f = work / "stages" / "01_read.json"
    if not f.is_file():
        return None
    return json.loads(f.read_text()).get("source")


def previous_source(work: Path) -> str | None:
    f = work / "stages" / "00_convert.json"
    if not f.is_file():
        return None
    return json.loads(f.read_text()).get("source")


def main(argv: list[str] | None = None) -> int:
    assert STAGE_NAMES == list(STAGES), (
        "show_stages.STAGE_NAMES 를 workspace.STAGES 에 맞춘다"
    )
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("work", type=Path, help="작업 폴더")
    ap.add_argument("steps", nargs="*", help="단계 번호, 이름, 범위(6-9). 없으면 전부")
    ap.add_argument("--dxf", help="01(read) 에서 읽을 DXF")
    ap.add_argument("--drawing", help="00(convert) 에 줄 DWG 또는 DXF")
    ap.add_argument("--dwg2dxf", help="00(convert) 에서 쓸 dwg2dxf 실행 파일")
    ap.add_argument(
        "--show", action="store_true", help="돌린 단계를 표와 그림으로 보기"
    )
    for opt in VALUE_OPTIONS:
        ap.add_argument(opt, help="run.py 에 넘긴다")
    for opt in FLAG_OPTIONS:
        ap.add_argument(opt, action="store_true", help="run.py 에 넘긴다")
    a = ap.parse_args(argv)

    steps = parse_steps(a.steps) or list(range(0 if a.drawing else 1, len(STAGES) + 1))
    passthrough: list[str] = []
    for opt in VALUE_OPTIONS:
        value = getattr(a, opt[2:].replace("-", "_"))
        if value is not None:
            passthrough += [opt, value]
    for opt in FLAG_OPTIONS:
        if getattr(a, opt[2:].replace("-", "_")):
            passthrough.append(opt)

    code = 0
    if 0 in steps:
        drawing = a.drawing or previous_source(a.work)
        if drawing is None:
            ap.error("00(convert) 을 돌리려면 --drawing <도면.dwg 또는 .dxf> 를 준다")
        args = [drawing, str(a.work)] + (["--dwg2dxf", a.dwg2dxf] if a.dwg2dxf else [])
        code = convert.main(args)
        steps = [n for n in steps if n != 0]
        if code:
            steps = []

    dxf = a.dxf
    if 1 in steps and dxf is None and not Workspace(a.work).has(CONVERT):
        dxf = previous_dxf(a.work)
        if dxf is None:
            ap.error(
                "01(read) 을 돌리려면 --dxf <도면.dxf> 를 주거나, DWG 는 0 --drawing <도면.dwg> 로 먼저 바꾼다"
            )
        print(f"도면: {dxf} (01_read.json 에 기록된 것)")

    for first, last in groups(steps):
        args = [str(a.work), "--from", STAGES[first - 1], "--to", STAGES[last - 1]]
        if first == 1 and dxf is not None:
            args.insert(0, str(dxf))
        code = runner.main(args + passthrough)
        if code:
            break
    if a.show:
        print()
        report(a.work, steps)
    return code


if __name__ == "__main__":
    sys.exit(main())
