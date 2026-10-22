"""Each stage runs alone from the files of earlier stages, and the chain equals main.py."""

import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from test_dxf_adapter import synthetic_sheet

from cutplan_agent.reader.main import main as reader_main
from cutplan_agent.reader.stages import (
    document,
    label,
    read,
    reconstruct,
    segment,
    title,
    unfold,
)

LATER = (title, segment, label, document, unfold, reconstruct)


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = fn(*args)
    return code, err.getvalue()


def chain(dxf: Path, out: Path) -> list[int]:
    codes = [quiet(read.main, [str(dxf), "--output-dir", str(out)])[0]]
    for stage in LATER:
        codes.append(quiet(stage.main, ["--output-dir", str(out), "--no-vlm"])[0])
    return codes


def tree(root: Path) -> dict[str, object]:
    """Files under root; JSON parsed with the root path masked."""
    files = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        if path.suffix == ".json":
            files[rel] = json.loads(path.read_text().replace(str(root), "<ROOT>"))
        elif path.suffix == ".step":
            files[rel] = "step"  # the STEP header carries the export time
        else:
            files[rel] = path.read_bytes().replace(str(root).encode(), b"<ROOT>")
    return files


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dxf = synthetic_sheet(self.root / "plate.dxf")

    def test_stages_one_by_one_equal_main(self):
        whole, staged = self.root / "main" / "plate", self.root / "stages" / "plate"
        code, _ = quiet(
            reader_main,
            [str(self.dxf), "--input-mode", "dxf", "--no-vlm"]
            + ["--output-dir", str(whole)],
        )
        self.assertIn(code, (0, 2))
        self.assertEqual(chain(self.dxf, staged), [0] * 7)
        self.assertEqual(tree(whole), tree(staged))
        for name in ("entities", "title", "views", "document", "unfold", "reconstruct"):
            self.assertTrue((staged / "analysis" / f"{name}.json").is_file(), name)

    def test_stage_names_the_missing_earlier_stage(self):
        code, err = quiet(title.main, ["--output-dir", str(self.root / "x")])
        self.assertEqual(code, 1)
        self.assertIn("run the read stage first", err)

    def test_rerun_needs_overwrite_and_clears_later_outputs(self):
        out = self.root / "plate"
        chain(self.dxf, out)
        work = out / "analysis"
        before = (work / "views.json").read_text()
        code, err = quiet(segment.main, ["--output-dir", str(out)])
        self.assertEqual(code, 1)
        self.assertIn("--overwrite", err)
        self.assertTrue((work / "document.json").is_file())
        code, _ = quiet(segment.main, ["--output-dir", str(out), "--overwrite"])
        self.assertEqual(code, 0)
        self.assertEqual((work / "views.json").read_text(), before)
        for gone in (
            work / "sheet_analysis.json",
            work / "document.json",
            out / "provenance.json",
        ):
            self.assertFalse(gone.exists(), gone)

    def test_document_uses_labels_edited_in_sheet_analysis(self):
        out = self.root / "plate"
        chain(self.dxf, out)
        path = out / "analysis" / "sheet_analysis.json"
        analysis = json.loads(path.read_text())
        right = next(v for v in analysis["views"] if v["label"] == "right")
        right["label"] = "other"
        path.write_text(json.dumps(analysis))
        code, _ = quiet(
            document.main, ["--output-dir", str(out), "--overwrite", "--no-vlm"]
        )
        self.assertEqual(code, 0)
        saved = json.loads((out / "analysis" / "document.json").read_text())
        names = [v["name"] for v in saved["document"]["views"]]
        self.assertNotIn("right", names)
        self.assertIn("front", names)


if __name__ == "__main__":
    unittest.main()
