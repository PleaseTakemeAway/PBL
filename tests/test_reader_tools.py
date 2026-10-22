"""Reader stages as tools (reader/tools.py), without a model server."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from test_dxf_adapter import synthetic_sheet

from cutplan_agent.reader.stages.workspace import STAGES
from cutplan_agent.reader.tools import ReaderTools
from cutplan_agent.reader.vlm import VLMClient, VLMConfig


def no_models():
    return VLMClient(VLMConfig(model=""), "ocr"), VLMClient(
        VLMConfig(model=""), "reason"
    )


def sheet(tmp: str) -> Path:
    (Path(tmp) / "in").mkdir()
    return synthetic_sheet(Path(tmp) / "in" / "sheet.dxf", with_arc_detail=False)


class ReaderToolsTest(unittest.TestCase):
    def test_tool_list_covers_every_stage(self):
        tools = ReaderTools("out", no_models())
        for stage in STAGES:
            self.assertIn(f"run_{stage}", tools.tools)
        self.assertEqual(
            tools.tools["run_read"].parameters["required"], ["work", "drawing"]
        )
        self.assertIn("Reads", tools.tools["run_view_labels"].description)

    def test_bad_calls_come_back_as_errors(self):
        with TemporaryDirectory() as tmp:
            tools = ReaderTools(Path(tmp) / "out", no_models())
            self.assertIn("error", tools.call("run_nothing", {}))
            self.assertIn("error", tools.call("run_views", {}))
            self.assertIn("error", tools.call("run_views", {"work": "a", "x": 1}))
            outside = tools.call("stage_status", {"work": "../elsewhere"})
            self.assertIn("under", outside["error"])
            early = tools.call("run_views", {"work": "a"})
            self.assertEqual(early["status"], "not_ready")

    def test_stage_tools_write_the_stage_files(self):
        with TemporaryDirectory() as tmp:
            dxf = sheet(tmp)
            tools = ReaderTools(Path(tmp) / "out", no_models(), Path(tmp) / "in")
            (found,) = tools.call("list_drawings", {})["drawings"]
            self.assertEqual(found["id"], "sheet")
            work = found["work"]
            read = tools.call("run_read", {"work": "sheet", "drawing": str(dxf)})
            self.assertEqual(read["status"], "done")
            self.assertLess(len(json.dumps(read)), 1000)  # not the entity list
            rest = tools.call(
                "run_stages", {"work": work, "first": "title_regex", "last": "sheet"}
            )
            self.assertEqual(rest["status"], "done")
            self.assertEqual(
                [s["stage"] for s in rest["stages"]],
                list(STAGES[1 : STAGES.index("sheet") + 1]),
            )
            ocr = next(s for s in rest["stages"] if s["stage"] == "title_ocr")
            self.assertEqual(ocr["status"], "skipped")  # no OCR model
            status = tools.call("stage_status", {"work": work})["stages"]
            self.assertTrue(status["sheet"].startswith("done"))
            self.assertEqual(status["document"], "not run")
            shown = tools.call("show_stage", {"work": work, "stage": "view_labels"})
            self.assertEqual(shown["status"], "done")


if __name__ == "__main__":
    unittest.main()
