"""Stage 6 unfold: part class → development parameters → flat pattern.

The reasoning model reads the parameters of the decided part_class with the unfold
skills; overall dimensions of the document fill what it leaves empty, and code computes
the blank (reader/unfold.run_unfold). Products: flat_pattern.json/.dxf/.png in the output
directory. unfold.json in the work directory keeps the record and the model call,
which sheet_analysis.json does not have because it is written before this stage.

Uses document.json when it exists, otherwise sheet_analysis.json only (as
main.py --analyze-only does).

PYTHONPATH=. python cutplan_agent/reader/stages/unfold.py --output-dir out/part [model options]
"""

from __future__ import annotations

from pathlib import Path

from cutplan_agent.reader.stages import workdir
from cutplan_agent.reader.unfold import run_unfold


def run(
    work_dir: str | Path,
    *,
    clients=None,
    use_document: bool | None = None,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    """Returns run_unfold's record. use_document=None means: if document.json exists."""
    from cutplan_agent.reader.vlm import make_clients

    work_dir = Path(work_dir)
    output_dir = Path(output_dir) if output_dir else work_dir.parent
    if use_document is None:
        use_document = (work_dir / "document.json").is_file()
    if use_document:
        drawing = workdir.load_document(work_dir)
        analysis = drawing.metadata.get("sheet_analysis", {})
    else:
        drawing = None
        analysis = workdir.read_json(work_dir, "sheet_analysis.json")
    workdir.prepare("unfold", work_dir, output_dir, overwrite=overwrite)
    ocr, reason = clients or make_clients()
    marks = workdir.trace_marks((ocr, reason))
    record = run_unfold(analysis, drawing, reason, output_dir)
    workdir.write_json(
        work_dir / "unfold.json",
        {
            "used_document": use_document,
            "record": record,
            "trace": workdir.trace_since((ocr, reason), marks),
        },
    )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = workdir.stage_parser(
        "Stage 6: read development parameters and draw the flat pattern"
    )
    parser.add_argument(
        "--no-document",
        action="store_true",
        help="Ignore document.json and use sheet_analysis.json only",
    )
    args = parser.parse_args(argv)
    return workdir.cli(
        run,
        args,
        clients=workdir.clients_from_args(args),
        use_document=False if args.no_document else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
