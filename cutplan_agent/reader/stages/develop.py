"""Stage 10 develop: apply the development formulas in code and write the flat pattern. No model.

in : stages/09_unfold_params.json
out: stages/10_develop.json, flat_pattern.json, flat_pattern.dxf, flat_pattern.png

PYTHONPATH=. python cutplan_agent/reader/stages/develop.py <work>
"""

from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    stage_function,
    stage_parser,
)
from cutplan_agent.reader.unfold import develop_unfold

STAGE = "develop"


@stage_function(STAGE)
def run(ws: Workspace) -> dict:
    params = ws.load("unfold_params")
    if "record" not in params:
        return ws.save(
            STAGE, {"status": "skipped", "reason": "unfold_params produced no record"}
        )
    ready = params["record"]["status"] == "params_read"
    record = develop_unfold(params["record"], ws.root)
    if not ready:
        status = {"status": "skipped", "reason": "unfold_params read no parameters"}
    elif record["status"] == "developed":
        status = {"status": "done"}
    else:
        status = {"status": "failed", "error": record["error"]}
    # the record is passed on even when nothing was developed: batch reports it as flat_pattern
    return ws.save(STAGE, {**status, "record": record})


def describe(record: dict) -> str:
    r = record["record"]
    blank = ", ".join(
        f"{k}={v:.2f}" for k, v in r["blank"].items() if isinstance(v, (int, float))
    )
    return (
        f"{r['part_type']}: {r['blank']['formula']}\n{blank}\n"
        f"warnings: {r['warnings']}\n{r['artifacts']}"
    )


def main(argv: list[str] | None = None) -> int:
    args = stage_parser(__doc__).parse_args(argv)
    return cli(args.work, lambda: run(args.work), describe)


if __name__ == "__main__":
    raise SystemExit(main())
