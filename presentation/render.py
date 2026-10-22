"""Render a deck to PDF and one PNG per slide in presentation/build/, to check the layout.

PYTHONPATH=. uv run python presentation/render.py presentation/reader_orchestrator.pptx

Needs LibreOffice (soffice). Korean text renders with whatever Korean font fontconfig has
(NanumGothic on mlic, in ~/.local/share/fonts); PowerPoint uses Malgun Gothic, so line
breaks can differ slightly. build/ is not committed.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

BUILD = Path(__file__).with_name("build")


def render(deck: Path, dpi: int = 110) -> list[Path]:
    BUILD.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                "soffice",
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(BUILD),
                str(deck),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
    pdf = BUILD / f"{deck.stem}.pdf"
    for old in BUILD.glob(f"{deck.stem}-*.png"):
        old.unlink()
    pages = []
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            out = BUILD / f"{deck.stem}-{i:02d}.png"
            page.get_pixmap(dpi=dpi).save(out)
            pages.append(out)
    return pages


if __name__ == "__main__":
    for path in render(Path(sys.argv[1])):
        print(path)
