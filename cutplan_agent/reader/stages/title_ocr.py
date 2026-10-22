"""Stage 03 title_ocr: the OCR model transcribes the title-block image. Model: OCR.

Runs only when the regex stage left a field empty and an OCR model is configured.
in : stages/01_read.json, stages/02_title_regex.json
out: stages/03_title_ocr.json (raw transcription, model call), analysis/title_block.png

PYTHONPATH=. python cutplan_agent/reader/stages/title_ocr.py <work> --ocr-model ... --ocr-base-url ...
"""

from cutplan_agent.reader.dxf_adapter import render_title_block
from cutplan_agent.reader.stages.workspace import (
    Workspace,
    box,
    cli,
    clients_from_args,
    fresh,
    stage_function,
    stage_parser,
)
from cutplan_agent.reader.vlm import VLMClient, ocr_text

STAGE = "title_ocr"


@stage_function(STAGE)
def run(ws: Workspace, *, ocr: VLMClient | None = None) -> dict:
    ocr = fresh(ocr, "ocr")
    regex = ws.load("title_regex")
    if not regex["missing"]:
        return ws.save(
            STAGE,
            {"status": "skipped", "reason": "regex filled every title-block field"},
        )
    if not ocr.enabled:
        return ws.save(
            STAGE, {"status": "skipped", "reason": "no OCR model configured"}
        )
    image = render_title_block(
        ws.entities(), box(regex["title_region"]), ws.analysis_dir
    )
    text = ocr_text(ocr, [image], task="title_block")
    return ws.save(
        STAGE,
        {
            "status": "done",
            "model": ocr.config.model,
            "image": str(image),
            "text": text,
            "trace": {"ocr": ocr.trace},
        },
    )


def describe(record: dict) -> str:
    text = record["text"]
    shown = text if text is None else text[:300] + ("…" if len(text) > 300 else "")
    return f"model={record['model']} image={record['image']}\n{shown}"


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__, models=("ocr",)).parse_args(argv)
    ocr, _ = clients_from_args(args)
    return cli(args.work, lambda: run(args.work, ocr=ocr), describe)


if __name__ == "__main__":
    raise SystemExit(main())
