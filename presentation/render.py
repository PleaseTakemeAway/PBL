"""Render a deck to PDF and one PNG per slide in presentation/build/, to check the layout.

PYTHONPATH=. uv run python presentation/render.py presentation/reader_orchestrator.pptx

Needs LibreOffice (soffice) and a Korean font. The preview swaps the decks' Malgun Gothic
for NanumGothic (on mlic in ~/.local/share/fonts), so line breaks can differ slightly from
PowerPoint. build/ is not committed.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pymupdf

BUILD = Path(__file__).with_name("build")
PREVIEW_FONT = "NanumGothic"  # installed on mlic; the decks use Malgun Gothic


def with_preview_font(deck: Path, out: Path) -> None:
    """Copy the deck with Malgun Gothic replaced by PREVIEW_FONT. Without it LibreOffice
    picks a fallback per text run and some runs come out as empty boxes."""
    with zipfile.ZipFile(deck) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith(".xml"):
                data = data.replace(b"Malgun Gothic", PREVIEW_FONT.encode())
            dst.writestr(info, data)


def render(deck: Path, dpi: int = 110) -> list[Path]:
    BUILD.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / deck.name
        with_preview_font(deck, copy)
        subprocess.run(
            [
                "soffice",
                f"-env:UserInstallation=file://{tmp}/profile",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(BUILD),
                str(copy),
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
