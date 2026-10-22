import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cutplan_agent.reader.drawing_io import load_drawing
from cutplan_agent.reader.main import main
from cutplan_agent.reader.vision_adapter import analyze_image, confirm_candidates
from cutplan_agent.reader.vision_reader import TextItem, classify_text
from cutplan_agent.reader.vlm import VLMClient, VLMConfig
from cutplan_agent.reconstruct.pipeline import ReconstructionPipeline


def synthetic_scan(
    path: Path, *, third_angle=True, dpi=200, with_title=True, scale=1.0
):
    """A4 landscape sheet of a 100 x 60 x 2 plate: frame, three views, dimension texts, title block. Pixel/mm is known from dpi."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    W, H = 297, 210
    fig = plt.figure(figsize=(W / 25.4, H / 25.4), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    k = dict(fill=False, lw=1.2, ec="black")
    ax.add_patch(Rectangle((10, 10), W - 20, H - 20, **k))
    s = scale
    fx, fy = (40, 80) if third_angle else (130, 110)
    ax.add_patch(Rectangle((fx, fy), 100 * s, 2 * s, **k))  # front (x,z)
    ty = fy + 2 * s + 25 if third_angle else fy - 25 - 60 * s
    ax.add_patch(Rectangle((fx, ty), 100 * s, 60 * s, **k))  # top (x,y)
    rx = fx + 100 * s + 30 if third_angle else fx - 30 - 60 * s
    ax.add_patch(Rectangle((rx, fy), 60 * s, 2 * s, **k))  # right (y,z)
    ax.plot(
        [fx + 30 * s, fx + 30 * s], [ty, ty + 60 * s], "k", lw=0.8, dashes=(6, 4)
    )  # a hidden line in top view
    f = dict(fontsize=11, family="DejaVu Sans", color="black")
    ax.text(fx + 50 * s, ty + 60 * s + 3, "100", ha="center", va="bottom", **f)
    ax.text(fx - 4, ty + 30 * s, "60", ha="right", va="center", rotation=90, **f)
    ax.text(rx + 30 * s, fy + 2 * s + 3, "60", ha="center", va="bottom", **f)
    ax.text(fx + 50 * s, fy - 4, "100", ha="center", va="top", **f)
    if with_title:
        ax.add_patch(Rectangle((236, 10), 51, 38, **k))
        for i, line in enumerate(
            [
                "PART NAME  PLATE",
                "MATERIAL  SS400, 2.0t",
                f"SCALE  {'1/1' if scale == 1 else '1/2'}    DIM  mm",
                "DWG NO  76K3-99999",
                "A4 (210x297)",
            ]
        ):
            ax.text(
                238,
                44 - i * 7,
                line,
                ha="left",
                va="top",
                fontsize=7,
                family="DejaVu Sans",
            )
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)
    return path


OFF = VLMClient(VLMConfig(model=""), "ocr")


class MockReason(VLMClient):
    def __init__(self, reply):
        super().__init__(
            VLMConfig(model="mock-reasoner", output_format="prompt"), "reason"
        )
        self.reply, self.prompts = reply, []

    def _call_openai(self, prompt, images, system):
        self.prompts.append(prompt)
        r = self.reply(prompt) if callable(self.reply) else self.reply
        return json.dumps(r)


class VisionReaderTests(unittest.TestCase):
    def test_text_classification(self):
        t = classify_text(TextItem("2-Ø13.7", (0, 0, 10, 10)))
        self.assertEqual(
            (t.kind, t.value, t.feature, t.count), ("dimension", 13.7, "diameter", 2)
        )
        self.assertEqual(
            classify_text(TextItem("R5", (0, 0, 10, 10))).feature, "radius"
        )
        self.assertEqual(
            classify_text(TextItem("t16 x 970 x 4220 - 1 SH'T", (0, 0, 10, 10))).kind,
            "caption",
        )
        self.assertEqual(
            classify_text(TextItem("MATERIAL SPCC,3.0t", (0, 0, 10, 10))).kind, "title"
        )
        self.assertEqual(
            classify_text(TextItem("SUPPORT WA", (0, 0, 10, 10))).kind, "label"
        )


class VisionAdapterTests(unittest.TestCase):
    def test_tesseract_only_analysis_and_calibration(self):
        with TemporaryDirectory() as tmp:
            png = synthetic_scan(Path(tmp) / "scan.png")
            a = analyze_image(png, OFF, OFF, Path(tmp) / "work")["analysis"]
            self.assertEqual(a["ocr_source"], "tesseract")
            self.assertEqual(a["sheet_type"], "orthographic")
            labels = {v["label"] for v in a["views"]}
            self.assertTrue({"front", "top", "right"} <= labels, a["views"])
            tb = a["title_block"]
            self.assertEqual(tb["scale"], 1.0)
            self.assertEqual(tb["thickness_mm"], 2.0)
            self.assertEqual(tuple(tb["paper_mm"]), (210, 297))
            ppm = a["calibration"]["px_per_mm"]
            self.assertAlmostEqual(ppm, 200 / 25.4, delta=0.35, msg=a["calibration"])
            self.assertTrue((Path(tmp) / "work" / "sheet.png").exists())

    def test_document_reconstructs_box_from_pixels(self):
        with TemporaryDirectory() as tmp:
            png = synthetic_scan(Path(tmp) / "scan.png")
            doc = load_drawing(png, work_dir=Path(tmp) / "work")
            self.assertEqual({v.name for v in doc.views}, {"front", "top", "right"})
            top = next(v for v in doc.views if v.name == "top")
            self.assertTrue(
                any(p.line_type == "hidden" for p in top.primitives),
                "dashed line should be classified hidden",
            )
            tol = doc.metadata["suggested_tolerance_mm"]
            result = ReconstructionPipeline(tol).run(doc)
            self.assertTrue(result.candidates, result.review_request)
            ext = result.candidates[0].extents
            for got, want in zip(ext, (100.0, 60.0, 2.0)):
                self.assertLess(abs(got - want), max(0.03 * want, 0.6), ext)

    def test_first_angle_layout(self):
        with TemporaryDirectory() as tmp:
            png = synthetic_scan(Path(tmp) / "scan.png", third_angle=False)
            doc = load_drawing(
                png, work_dir=Path(tmp) / "work", projection_default="first"
            )
            self.assertEqual({v.name for v in doc.views}, {"front", "top", "right"})
            ext = (
                ReconstructionPipeline(doc.metadata["suggested_tolerance_mm"])
                .run(doc)
                .candidates[0]
                .extents
            )
            self.assertLess(abs(ext[0] - 100), 3)
            self.assertLess(abs(ext[1] - 60), 2)

    def test_reasoning_vlm_labels_and_overall_dims_drive_calibration(self):
        with TemporaryDirectory() as tmp:
            png = synthetic_scan(
                Path(tmp) / "scan.png", with_title=False
            )  # no paper size / scale -> dimensions must calibrate

            def reply(prompt):
                regions = json.loads(prompt.split("Regions: ")[1].split("\n\n")[0])
                by_area = sorted(
                    regions, key=lambda r: -r["size_px"][0] * r["size_px"][1]
                )
                top, front, right = by_area[0], by_area[1], by_area[2]
                return {
                    "projection": "third",
                    "part_class": "flat",
                    "reconstructable_from_views": True,
                    "views": [
                        {
                            "id": front["id"],
                            "type": "front",
                            "confidence": 0.9,
                            "reason": "thin strip",
                            "overall_width_mm": 100,
                            "overall_height_mm": 2,
                        },
                        {
                            "id": top["id"],
                            "type": "top",
                            "confidence": 0.9,
                            "reason": "above",
                            "overall_width_mm": 100,
                            "overall_height_mm": 60,
                        },
                        {
                            "id": right["id"],
                            "type": "right",
                            "confidence": 0.8,
                            "reason": "right",
                            "overall_width_mm": 60,
                            "overall_height_mm": 2,
                        },
                    ],
                }

            reason = MockReason(reply)
            a = analyze_image(png, OFF, reason, Path(tmp) / "work")["analysis"]
            self.assertTrue(a["vlm_decision"]["used"])
            self.assertEqual(a["calibration"]["method"], "dimensions")
            self.assertAlmostEqual(a["calibration"]["px_per_mm"], 200 / 25.4, delta=0.4)
            self.assertEqual(a["part_class"], "flat")

    def test_candidate_confirmation_records_pick_and_disagreement(self):
        with TemporaryDirectory() as tmp:
            png = synthetic_scan(Path(tmp) / "scan.png")
            doc = load_drawing(png, work_dir=Path(tmp) / "work")
            result = ReconstructionPipeline(doc.metadata["suggested_tolerance_mm"]).run(
                doc
            )
            reason = MockReason(
                {"pick": 1, "confidence": 0.7, "reason": "matches", "problems": []}
            )
            rec = confirm_candidates(result, reason, Path(tmp) / "work")
            self.assertTrue(rec["used"])
            self.assertEqual(rec["pick"], result.candidates[0].id)
            self.assertTrue((Path(tmp) / "work" / "candidates.png").exists())
            reason2 = MockReason(
                {"pick": None, "confidence": 0.2, "reason": "none", "problems": ["x"]}
            )
            self.assertEqual(
                confirm_candidates(result, reason2, Path(tmp) / "work").get("error"),
                "no usable pick",
            )

    def test_cli_image_end_to_end(self):
        with TemporaryDirectory() as tmp:
            png = synthetic_scan(Path(tmp) / "scan.png")
            self.assertEqual(
                main(
                    [
                        str(png),
                        "--analyze-only",
                        "--no-vlm",
                        "--output-dir",
                        str(Path(tmp) / "out"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main([str(png), "--no-vlm", "--output-dir", str(Path(tmp) / "out")]), 0
            )
            params = json.loads(
                (Path(tmp) / "out" / "parameters.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                (Path(tmp) / "out" / "reconstruction.step").exists(), params
            )


if __name__ == "__main__":
    unittest.main()


SCANS = Path(__file__).resolve().parent / "fixtures"


@unittest.skipUnless(
    (SCANS / "hce_76K3-42510_plate.png").exists(), "real scans not present"
)
class RealScanTests(unittest.TestCase):
    def test_plate_scan_three_views_no_tables(self):
        with TemporaryDirectory() as tmp:
            a = analyze_image(
                SCANS / "hce_76K3-42510_plate.png", OFF, OFF, Path(tmp) / "w"
            )["analysis"]
            self.assertEqual(a["sheet_type"], "orthographic")
            labels = [v["label"] for v in a["views"]]
            self.assertTrue({"front", "top", "right"} <= set(labels), labels)
            self.assertLessEqual(
                len(a["views"]), 4, labels
            )  # 3 views + at most the weld/projection symbol
            self.assertEqual(a["title_block"]["thickness_mm"], 4.0)
            self.assertEqual(tuple(a["title_block"]["paper_mm"]), (297, 420))
            ppm = a["calibration"]["px_per_mm"]
            self.assertTrue(
                ppm and 1.5 < ppm < 2.6, a["calibration"]
            )  # A3 @ ~141 dpi, scale 1/3 -> ~1.85 px/mm

    def test_cover_scan_finds_main_views(self):
        with TemporaryDirectory() as tmp:
            a = analyze_image(
                SCANS / "hce_74K4-60241_cover.png", OFF, OFF, Path(tmp) / "w"
            )["analysis"]
            self.assertEqual(a["sheet_type"], "orthographic")
            self.assertGreaterEqual(
                sum(1 for v in a["views"] if v["label"] != "other"), 3
            )
            self.assertEqual(a["title_block"]["thickness_mm"], 3.0)
