"""Stage 00 convert: the drawing file the read stage will open. No model.

in : a DXF or DWG file
out: stages/00_convert.json (source and its sha256, the DXF to read and its sha256, converter,
     model-space entity count), and for a DWG input/<name>.dxf in the workspace

A DXF is used as given. A DXF saved by AutoCAD is the most faithful input, so ask for DXF
when you can. A DWG is converted with GNU LibreDWG dwg2dxf (found from --dwg2dxf, the DWG2DXF
environment variable, PATH, then ~/.local/bin; scripts/install_libredwg.sh installs it).
LibreDWG 0.14 cannot read some DWG files and then often writes an empty or truncated DXF with
exit code 0, so the stage opens the result with ezdxf and fails when it cannot be opened or its
model space is empty.

This stage is optional and sits before the DXF chain: main.py --batch and stages/run.py still
start at read with a DXF. When 00 exists, read uses its DXF if no drawing is given. Saving 00
deletes the files of stages 01-13.

PYTHONPATH=. python cutplan_agent/reader/stages/convert.py <drawing.dwg|.dxf> <work> [--dwg2dxf PATH]
"""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import ezdxf

from cutplan_agent.reader.stages.workspace import (
    Workspace,
    cli,
    stage_function,
    stage_parser,
)

STAGE = "convert"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_dwg2dxf(explicit: str | None = None) -> Path:
    for candidate in (
        explicit,
        os.environ.get("DWG2DXF"),
        shutil.which("dwg2dxf"),
        Path.home() / ".local" / "bin" / "dwg2dxf",
    ):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise FileNotFoundError(
        "dwg2dxf not found: give --dwg2dxf, set DWG2DXF, or run scripts/install_libredwg.sh"
    )


def converter_version(exe: Path) -> str:
    out = subprocess.run(
        [str(exe), "--version"], capture_output=True, text=True, timeout=30
    )
    lines = (out.stdout or out.stderr).strip().splitlines()
    return lines[0] if lines else ""


@stage_function(STAGE)
def run(ws: Workspace, drawing: str | Path, dwg2dxf: str | None = None) -> dict:
    source = Path(drawing)
    kind = source.suffix.lower()
    if kind == ".dxf":
        dxf, converter = source, None
    elif kind == ".dwg":
        exe = find_dwg2dxf(dwg2dxf)
        dxf = ws.root / "input" / f"{source.stem}.dxf"
        dxf.parent.mkdir(parents=True, exist_ok=True)
        dxf.unlink(missing_ok=True)
        done = subprocess.run(
            [str(exe), "-y", "-o", str(dxf), str(source)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        converter = {
            "program": str(exe),
            "version": converter_version(exe),
            "exit_code": done.returncode,
            "stderr_tail": done.stderr.strip().splitlines()[-5:],
        }
        if not dxf.is_file():
            raise RuntimeError(f"dwg2dxf wrote no DXF (exit {done.returncode})")
    else:
        raise ValueError(f"expected a .dxf or .dwg file, got {source.name}")
    try:
        entities = len(ezdxf.readfile(dxf).modelspace())
    except Exception as exc:
        raise RuntimeError(
            f"ezdxf cannot open {dxf.name} ({type(exc).__name__}: {exc}); "
            "LibreDWG may not read this DWG: ask for a DXF saved by AutoCAD or use the PDF"
        ) from exc
    if entities == 0:
        raise RuntimeError(
            f"{dxf.name} has an empty model space; "
            "LibreDWG may not read this DWG: ask for a DXF saved by AutoCAD or use the PDF"
        )
    return ws.save(
        STAGE,
        {
            "status": "done",
            "source": str(source),
            "source_kind": kind[1:],
            "source_sha256": sha256(source),
            "dxf": str(dxf),
            "dxf_sha256": sha256(dxf),
            "converter": converter,
            "modelspace_entities": entities,
        },
    )


def describe(record: dict) -> str:
    how = (
        "DXF as given"
        if record["converter"] is None
        else f"converted with {record['converter']['version'] or record['converter']['program']}"
    )
    return f"{record['source_kind']}: {how}; {record['modelspace_entities']} model-space entities -> {record['dxf']}"


def main(argv: list[str] | None = None) -> int:
    parser = stage_parser(__doc__, drawing=True)
    parser.add_argument("--dwg2dxf", help="dwg2dxf executable")
    args = parser.parse_args(argv)
    return cli(args.work, lambda: run(args.work, args.drawing, args.dwg2dxf), describe)


if __name__ == "__main__":
    raise SystemExit(main())
