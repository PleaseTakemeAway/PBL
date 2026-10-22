"""The fixed stage order for one DXF drawing. main.py and batch.py run it.

1 read → 2 title → 3 segment → 4 label → 5 document → 6 unfold → 7 reconstruct

Each stage is also a script of its own (cutplan_agent/reader/stages/<name>.py), so a
person or an orchestrating model can run, inspect and rerun any stage alone.
"""

from __future__ import annotations

from pathlib import Path

from cutplan_agent.reader.stages import label, read, segment, title, workdir


def analyze(
    source: str | Path,
    work_dir: str | Path,
    clients,
    *,
    output_dir: str | Path | None = None,
    projection_default: str = "third",
    gap_ratio: float = 0.008,
) -> dict:
    """Stages 1-4 on a DXF; returns the sheet analysis (sheet_analysis.json).

    Earlier outputs in the work directory are replaced, as main.py always did.
    """
    kw = {"output_dir": output_dir, "overwrite": True}
    read.run(work_dir, source=source, **kw)
    title.run(work_dir, clients=clients, **kw)
    segment.run(work_dir, gap_ratio=gap_ratio, **kw)
    label.run(work_dir, clients=clients, projection_default=projection_default, **kw)
    return workdir.read_json(Path(work_dir), "sheet_analysis.json")
