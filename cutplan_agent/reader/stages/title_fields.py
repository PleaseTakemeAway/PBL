"""Stage 04 title_fields: the reasoning model turns the OCR transcription into the missing
title-block fields. Model: reasoning.

in : stages/02_title_regex.json, stages/03_title_ocr.json
out: stages/04_title_fields.json (model reply, final title_block, model call)

PYTHONPATH=. python cutplan_agent/reader/stages/title_fields.py <work> --reason-model ... --reason-base-url ...
"""

from cutplan_agent.reader.dxf_adapter import TITLE_BLOCK_PROMPT, apply_title_fields
from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    clients_from_args,
    fresh,
    stage_function,
    stage_parser,
    title_from_json,
)
from cutplan_agent.reader.vlm import VLMClient, structure_ocr_text

STAGE = "title_fields"


@stage_function(STAGE)
def run(ws: Workspace, *, reason: VLMClient | None = None) -> dict:
    reason = fresh(reason, "reason")
    regex = ws.load("title_regex")
    ocr = ws.load("title_ocr")
    title = title_from_json(regex["title_block"])
    text = ocr.get("text")
    skip = None
    if ocr["status"] != "done":
        skip = "title_ocr did not run the OCR model"
    elif not isinstance(text, str) or not text.strip():
        skip = "the OCR model returned no text"
    elif not reason.enabled:
        skip = "no reasoning model configured"
    if skip:
        # the regex title block passes through unchanged
        return ws.save(
            STAGE,
            {"status": "skipped", "reason": skip, "title_block": title.as_dict()},
        )
    fields = structure_ocr_text(
        reason,
        text,
        [ocr["image"]],
        task="title_block",
        instructions=TITLE_BLOCK_PROMPT,
    )
    if isinstance(fields, dict):
        apply_title_fields(
            title,
            fields,
            regex["missing"],
            f"vlm_reason:{reason.config.model}+vlm_ocr:{ocr['model']}",
        )
    return ws.save(
        STAGE,
        {
            "status": "done",
            "model": reason.config.model,
            "fields": fields,
            "title_block": title.as_dict(),
            "trace": {"reason": reason.trace},
        },
    )


def describe(record: dict) -> str:
    title = record["title_block"]
    filled = {
        k: title[k] for k, src in title["sources"].items() if src.startswith("vlm_")
    }
    return f"model reply: {record['fields']}\nfilled from the model: {filled}"


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__, models=("reason",)).parse_args(argv)
    _, reason = clients_from_args(args)
    return cli(args.work, lambda: run(args.work, reason=reason), describe)


if __name__ == "__main__":
    raise SystemExit(main())
