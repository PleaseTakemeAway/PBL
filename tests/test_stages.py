"""Stage scripts (cutplan_agent/reader/stages/): one file per stage, same results as --batch."""

import json
import re
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from test_dxf_adapter import synthetic_sheet

from cutplan_agent.reader.batch import run_batch
from cutplan_agent.reader.stages import (
    confirm,
    convert,
    develop,
    document,
    export,
    read,
    reconstruct,
    sheet,
    title_fields,
    title_ocr,
    title_regex,
    unfold_params,
    view_labels,
    views,
)
from cutplan_agent.reader.stages.run import run_drawing
from cutplan_agent.reader.stages.workspace import (
    STAGES,
    THREE_D,
    THREE_D_OFF,
    StageNotReady,
    Workspace,
)
from cutplan_agent.reader.vlm import PART_CLASSES, VLMClient, VLMConfig
from cutplan_agent.reader.vlm_output import normalize_response

REPLIES = {
    "title_block": {"part_name": "PLATE", "projection": "third", "weight_kg": 1.5},
    "view_labels": {
        "projection": "third",
        "part_class": "flat",
        "part_class_scores": {n: (4 if n == "flat" else 0) for n in PART_CLASSES},
        "reconstructable_from_views": True,
        "views": [
            {"id": 1, "type": "top", "confidence": 0.9, "reason": "above"},
            {"id": 2, "type": "front", "confidence": 0.9, "reason": "front"},
            {"id": 3, "type": "right", "confidence": 0.9, "reason": "right"},
        ],
    },
    "unfold_params": {
        "part_type": "flat",
        "thickness": 2.0,
        "outline": [[0, 0], [100, 0], [100, 60], [0, 60]],
        "segments": [],
        "bend_angles": [],
        "bend_radii": [],
        "holes": [],
        "confidence": "medium",
    },
    "candidate_confirmation": {"pick": 1, "confidence": 0.8, "reason": "matches"},
}


class Scripted(VLMClient):
    """OCR returns fixed text; the reasoning role answers each task with REPLIES."""

    def __init__(self, role):
        super().__init__(VLMConfig(model=f"mock-{role}", output_format="prompt"), role)

    def _call_openai(self, prompt, images, system, **kwargs):
        if self.role == "ocr":
            return "PART NAME PLATE\nSCALE 1/2"
        task = re.search(r'task="(\w+)"', prompt).group(1)
        return json.dumps(normalize_response(REPLIES[task], "reason", task)[0])


def clients():
    return Scripted("ocr"), Scripted("reason")


def files(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def without_timing(data: bytes) -> bytes:
    data = re.sub(rb'"seconds": [0-9.]+', b'"seconds": 0', data)
    return re.sub(rb"'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ'", b"'T'", data)


class StageTests(unittest.TestCase):
    def test_stage_scripts_one_by_one_match_batch(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "in").mkdir()
            dxf = synthetic_sheet(root / "in" / "sheet.dxf", with_arc_detail=False)
            out = root / "out"
            run_batch([dxf], clients(), out, input_mode="dxf", three_d=True)
            batch = files(out / "sheet")
            shutil.rmtree(out)

            ws = out / "sheet"
            ocr, reason = clients()
            read.run(ws, dxf)
            title_regex.run(ws)
            title_ocr.run(ws, ocr=ocr)
            title_fields.run(ws, reason=reason)
            views.run(ws)
            view_labels.run(ws, reason=reason)
            sheet.run(ws)
            document.run(ws)
            unfold_params.run(ws, reason=reason)
            develop.run(ws)
            reconstruct.run(ws)
            confirm.run(ws, reason=reason)
            export.run(ws)
            by_hand = files(ws)

            self.assertEqual(set(batch) - set(by_hand), {"prediction.json"})
            self.assertEqual(set(by_hand) - set(batch), set())
            for name in by_hand:
                self.assertEqual(
                    without_timing(batch[name]), without_timing(by_hand[name]), name
                )
            statuses = {
                s: json.loads((ws / "stages" / f"{i + 1:02d}_{s}.json").read_text())[
                    "status"
                ]
                for i, s in enumerate(STAGES)
            }
            self.assertEqual(set(statuses.values()), {"done"}, statuses)

    def test_3d_stages_are_skipped_unless_asked_for(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            ws = Workspace(Path(tmp) / "work")
            records = run_drawing(dxf, ws.root, clients())
            self.assertEqual(records["develop"]["status"], "done")
            for stage in THREE_D:
                self.assertEqual(ws.load(stage)["status"], "skipped")
                self.assertEqual(ws.load(stage)["reason"], THREE_D_OFF)
            self.assertFalse((ws.root / "report.md").exists())
            out = Path(tmp) / "out"
            result = run_batch([dxf], clients(), out, input_mode="dxf")
            self.assertEqual(result["reconstruction"]["summary"]["predicted"], 1)

    def test_unfold_params_stage_keeps_the_model_reply(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            ws = Workspace(Path(tmp) / "work")
            run_drawing(dxf, ws.root, clients(), last="unfold_params")
            stage = ws.load("unfold_params")
            (call,) = stage["trace"]["reason"]
            self.assertEqual(call["task"], "unfold_params")
            self.assertTrue(call["ok"])
            self.assertIn('"outline"', call["raw"])
            self.assertEqual(
                stage["record"]["sources"]["outline"], "vlm_reason:mock-reason"
            )

    def test_batch_options_leave_skipped_stage_files(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            off = (
                VLMClient(VLMConfig(model=""), "ocr"),
                VLMClient(VLMConfig(model=""), "reason"),
            )
            run_batch(
                [dxf], off, Path(tmp) / "out", input_mode="dxf", analyze_only=True
            )
            ws = Workspace(Path(tmp) / "out" / "sheet")
            self.assertEqual(ws.load("title_ocr")["reason"], "no OCR model configured")
            self.assertEqual(ws.load("document")["reason"], "--analyze-only")
            self.assertEqual(ws.load("export")["status"], "skipped")

    def test_rerun_drops_later_stages_and_missing_inputs_are_reported(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            ws = Workspace(Path(tmp) / "work")
            with self.assertRaises(StageNotReady):
                views.run(ws)
            run_drawing(dxf, ws.root, clients(), last="sheet")
            self.assertTrue(ws.has("sheet"))
            views.run(ws)
            self.assertTrue(ws.has("views"))
            self.assertFalse(ws.has("view_labels"))
            self.assertFalse(ws.has("sheet"))
            with self.assertRaises(StageNotReady):
                sheet.run(ws)

    def test_failed_stage_is_recorded_and_blocks_the_next_one(self):
        with TemporaryDirectory() as tmp:
            ws = Workspace(Path(tmp) / "work")
            with self.assertRaises(OSError):
                read.run(ws, Path(tmp) / "missing.dxf")
            self.assertEqual(
                json.loads(ws.path("read").read_text())["status"], "failed"
            )
            with self.assertRaises(StageNotReady):
                title_regex.run(ws)

    def test_convert_stage_feeds_read_and_rejects_unreadable_files(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            ws = Workspace(Path(tmp) / "work")
            record = convert.run(ws, dxf)
            self.assertEqual(record["step"], 0)
            self.assertEqual(ws.path("convert").name, "00_convert.json")
            self.assertIsNone(record["converter"])
            self.assertEqual(read.run(ws)["source"], str(dxf))
            self.assertIn("stages/00_convert.json", ws.load("read")["inputs"])
            # saving 00 again drops 01-13, as any stage drops the stages after it
            convert.run(ws, dxf)
            self.assertFalse(ws.has("read"))

            broken = Path(tmp) / "broken.dxf"
            broken.write_text("0\nSECTION\n")
            with self.assertRaises(RuntimeError):
                convert.run(ws, broken)
            self.assertEqual(
                json.loads(ws.path("convert").read_text())["status"], "failed"
            )
            with self.assertRaises(ValueError):
                convert.run(ws, Path(tmp) / "sheet.pdf")


if __name__ == "__main__":
    unittest.main()
