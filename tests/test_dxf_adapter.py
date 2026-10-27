import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cutplan_agent.reader.drawing_io import load_drawing
from cutplan_agent.reader.dxf_adapter import analyze_dxf
from cutplan_agent.reader.main import main
from cutplan_agent.reader.vlm import (
    PART_CLASSES,
    VLMClient,
    VLMConfig,
    extract_json,
    softmax_class_scores,
)
from cutplan_agent.reconstruct.pipeline import ReconstructionPipeline


def _pair(code, value):
    return f"{code}\n{value}\n"


def _line(x1, y1, x2, y2, layer="0", lt="BYLAYER"):
    return (
        "0\nLINE\n"
        + _pair(8, layer)
        + _pair(6, lt)
        + _pair(10, x1)
        + _pair(20, y1)
        + _pair(30, 0)
        + _pair(11, x2)
        + _pair(21, y2)
        + _pair(31, 0)
    )


def _rect(x, y, w, h, layer="0"):
    return (
        _line(x, y, x + w, y, layer)
        + _line(x + w, y, x + w, y + h, layer)
        + _line(x + w, y + h, x, y + h, layer)
        + _line(x, y + h, x, y, layer)
    )


def _text(x, y, s, h=3.5):
    return (
        "0\nTEXT\n"
        + _pair(8, "TEXT")
        + _pair(10, x)
        + _pair(20, y)
        + _pair(30, 0)
        + _pair(40, h)
        + _pair(1, s)
    )


def _arc(cx, cy, r, a1, a2):
    return (
        "0\nARC\n"
        + _pair(8, "0")
        + _pair(10, cx)
        + _pair(20, cy)
        + _pair(30, 0)
        + _pair(40, r)
        + _pair(50, a1)
        + _pair(51, a2)
    )


def _dim(x1, y1, x2, y2, tx, ty, value, horizontal=True):
    # DIMENSION + its exploded block so axis inference has geometry to look at
    blk = f"D{int(x1)}{int(y1)}"
    ent = (
        "0\nDIMENSION\n"
        + _pair(8, "DIM")
        + _pair(2, blk)
        + _pair(10, x2)
        + _pair(20, y2)
        + _pair(30, 0)
        + _pair(11, tx)
        + _pair(21, ty)
        + _pair(31, 0)
        + _pair(70, 0)
        + _pair(1, "<>")
        + _pair(42, value)
        + _pair(13, x1)
        + _pair(23, y1)
        + _pair(33, 0)
        + _pair(14, x2)
        + _pair(24, y2)
        + _pair(34, 0)
    )
    geom = _line(x1, y1, x2, y2, "DIM") if horizontal else _line(x1, y1, x2, y2, "DIM")
    block = (
        "0\nBLOCK\n"
        + _pair(8, "0")
        + _pair(2, blk)
        + _pair(70, 1)
        + _pair(10, 0)
        + _pair(20, 0)
        + _pair(30, 0)
        + _pair(3, blk)
        + geom
        + "0\nENDBLK\n"
    )
    return ent, block


def synthetic_sheet(
    path: Path, *, third_angle=True, with_arc_detail=True, geometry_scale=0.5
):
    """A3-like sheet: frame, three views of a 100x60x2 plate at scale 1/2, title block, BOM texts, one detail with arcs."""
    s = geometry_scale
    fx, fy = 60, 120  # front view (x,z): 100 x 2 -> 50 x 1
    front = _rect(fx, fy, 100 * s, 2 * s)
    top_y = fy + 2 * s + 40 if third_angle else fy - 40 - 60 * s
    top = _rect(fx, top_y, 100 * s, 60 * s)  # (x,y)
    right_x = fx + 100 * s + 40 if third_angle else fx - 40 - 60 * s
    right = _rect(right_x, fy, 60 * s, 2 * s)  # (y,z)
    ents, blocks = "", ""
    d, b = _dim(fx, fy - 10, fx + 100 * s, fy - 10, fx + 20, fy - 14, 100.0)
    ents += d
    blocks += b
    d, b = _dim(fx - 10, fy, fx - 10, fy + 2 * s, fx - 16, fy, 2.0, horizontal=False)
    ents += d
    blocks += b
    d, b = _dim(
        fx - 10,
        top_y,
        fx - 10,
        top_y + 60 * s,
        fx - 16,
        top_y + 10,
        60.0,
        horizontal=False,
    )
    ents += d
    blocks += b
    detail = ""
    if with_arc_detail:
        detail = (
            _arc(230, 230, 8, 0, 180)
            + _line(222, 230, 222, 210)
            + _line(238, 230, 238, 210)
            + _line(222, 210, 238, 210)
            + _text(220, 200, "DETAIL A", 2.5)
        )
    frame = _rect(5, 5, 410, 287)
    title = (
        _rect(300, 10, 110, 50)
        + _text(305, 50, "PART NAME  PLATE")
        + _text(305, 42, "MATERIAL  SS400, 2.0t")
        + _text(305, 34, "SCALE")
        + _text(330, 34, "1/2")
        + _text(360, 34, "DIM   mm")
        + _text(305, 24, "DW'G NO")
        + _text(340, 20, "76K3-99999", 6.0)
        + _text(305, 14, "ISSUE 00")
    )
    bom = (
        _rect(300, 65, 110, 20)
        + _text(305, 78, "ITEM  PART NO.  PART NAME  QTY")
        + _text(305, 70, "1   S241-100000  NUT-WELD  2")
    )
    body = (
        "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n"
        "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n0\nLAYER\n2\n0\n6\nCONTINUOUS\n0\nLAYER\n2\nDIM\n6\nCONTINUOUS\n0\nLAYER\n2\nTEXT\n6\nCONTINUOUS\n0\nENDTAB\n0\nENDSEC\n"
        "0\nSECTION\n2\nBLOCKS\n" + blocks + "0\nENDSEC\n"
        "0\nSECTION\n2\nENTITIES\n"
        + frame
        + front
        + top
        + right
        + ents
        + detail
        + title
        + bom
        + "0\nENDSEC\n0\nEOF\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


class MockReason(VLMClient):
    """Replaces the HTTP call with canned JSON so the validation logic is exercised."""

    def __init__(self, reply):
        super().__init__(
            VLMConfig(model="mock-reasoner", output_format="prompt"), "reason"
        )
        self.reply = reply

    def _call_openai(self, prompt, images, system):
        self.last_prompt = prompt
        return "```json\n" + json.dumps(self.reply) + "\n```"


class DxfAdapterTests(unittest.TestCase):
    def test_analysis_routes_raw_ocr_to_reasoning_title_and_view_tasks(self):
        raw = (
            "PART NAME PLATE\nMATERIAL SS400, 2t\nSCALE 1/2\nDIM mm\nDW'G NO 76K3-99999"
        )
        ocr = VLMClient(VLMConfig(model="mock-ocr", output_format="json_schema"), "ocr")
        reason = VLMClient(VLMConfig(model="mock-reason"), "reason")
        from cutplan_agent.reader.vlm_output import normalize_response

        title_reply, _ = normalize_response(
            {"part_name": "PLATE", "projection": "third"}, "reason", "title_block"
        )
        view_reply, _ = normalize_response(
            {
                "part_class": "flat",
                "projection": "third",
                "views": [
                    {
                        "id": 1,
                        "type": "front",
                        "confidence": 0.8,
                        "reason": "plate edge",
                    },
                ],
            },
            "reason",
            "view_labels",
        )
        with (
            TemporaryDirectory() as tmp,
            patch.object(ocr, "_call_openai", return_value=raw) as ocr_call,
            patch.object(
                reason,
                "_call_openai",
                side_effect=[json.dumps(title_reply), json.dumps(view_reply)],
            ) as reason_call,
        ):
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            analysis = analyze_dxf(dxf, ocr, reason, Path(tmp) / "work")["analysis"]
            saved = json.loads((Path(tmp) / "work" / "sheet_analysis.json").read_text())
        self.assertEqual(ocr_call.call_args.args[0], "Free OCR.")
        self.assertNotIn("schema", ocr_call.call_args.kwargs)
        self.assertIn(json.dumps(raw), reason_call.call_args_list[0].args[0])
        self.assertEqual(analysis["title_block"]["part_name"], "PLATE")
        self.assertEqual(analysis["part_class"], "flat")
        self.assertEqual(saved["vlm_trace"][0]["raw"], raw)
        self.assertTrue(all(item["ok"] for item in saved["vlm_trace"]))
        self.assertEqual(
            [item["task"] for item in reason.trace], ["title_block", "view_labels"]
        )
        self.assertTrue(
            all(item["response"]["role"] == "reason" for item in reason.trace)
        )

    @unittest.skipUnless(
        importlib.util.find_spec("ezdxf"), "Optional DXF dependency unavailable"
    )
    def test_ezdxf_reader_handles_text_mtext_and_ellipse(self):
        import ezdxf

        from cutplan_agent.reader.dxf_reader import _read_with_ezdxf

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "entities.dxf"
            document = ezdxf.new("R2010")
            modelspace = document.modelspace()
            modelspace.add_text("TEXT sample", height=2.5)
            modelspace.add_mtext("MTEXT sample", dxfattribs={"char_height": 3.5})
            modelspace.add_ellipse((0, 0), major_axis=(10, 0), ratio=0.5)
            document.saveas(path)

            entities, _ = _read_with_ezdxf(path)
            texts = [(e.text, e.height) for e in entities if e.kind == "text"]
            self.assertEqual(texts, [("TEXT sample", 2.5), ("MTEXT sample", 3.5)])
            self.assertTrue(
                any(e.attributes.get("source") == "ellipse" for e in entities)
            )

    def test_extract_json_handles_fences_and_prose(self):
        self.assertEqual(
            extract_json('Sure! ```json\n{"a": [1, {"b": "x}y"}]}\n``` done')["a"][1][
                "b"
            ],
            "x}y",
        )

    def test_class_score_softmax_is_stable_and_normalized(self):
        probabilities = softmax_class_scores(
            {name: (1000 if name == "cone" else -1000) for name in PART_CLASSES}
        )
        self.assertIsNotNone(probabilities)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0)
        self.assertEqual(max(probabilities, key=probabilities.get), "cone")
        self.assertIsNone(softmax_class_scores({"flat": 1}))

    def test_deterministic_analysis_third_angle(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf")
            off = VLMClient(VLMConfig(model=""), "ocr")
            a = analyze_dxf(dxf, off, off, Path(tmp) / "work")["analysis"]
            labels = {v["label"] for v in a["views"]}
            self.assertTrue({"front", "top", "right"} <= labels, a["views"])
            self.assertEqual(a["projection"], "third")
            tb = a["vlm_decision"]
            json.loads(
                (Path(tmp) / "work" / "sheet_analysis.json").read_text(encoding="utf-8")
            )
            self.assertEqual(a["entity_counts"]["arc"], 1)
            self.assertTrue((Path(tmp) / "work" / "sheet.png").exists())
            self.assertFalse(tb["used"])
            self.assertTrue(any("no reasoning VLM" in r["issue"] for r in a["review"]))

    def test_title_block_regex(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf")
            off = VLMClient(VLMConfig(model=""), "ocr")
            t = analyze_dxf(dxf, off, off, Path(tmp) / "work")["title"]
            self.assertEqual(t.scale, 0.5)
            self.assertEqual(t.thickness_mm, 2.0)
            self.assertEqual(t.units, "mm")
            self.assertEqual(t.drawing_no, "76K3-99999")
            self.assertEqual(t.sources["scale"], "regex")

    def test_document_feeds_pipeline(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            doc = load_drawing(dxf, work_dir=Path(tmp) / "work")
            self.assertEqual(doc.metadata["drawing_scale"], 0.5)
            self.assertEqual(doc.metadata["sheet_thickness"], 2.0)
            self.assertEqual(doc.metadata.get("dimensions", {}).get("x"), 100.0)
            result = ReconstructionPipeline().run(doc)
            best = result.candidates[0]
            self.assertEqual((len(best.vertices), len(best.edges)), (8, 12))
            self.assertEqual(
                tuple(round(e, 6) for e in best.extents), (100.0, 60.0, 2.0)
            )
            self.assertTrue(result.evaluations[0].valid)

    def test_model_space_coordinates_do_not_apply_title_scale_twice(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(
                Path(tmp) / "model_space.dxf", with_arc_detail=False, geometry_scale=1.0
            )
            doc = load_drawing(dxf, work_dir=Path(tmp) / "work")
            self.assertEqual(doc.metadata["reported_drawing_scale"], 0.5)
            self.assertEqual(doc.metadata["drawing_scale"], 1.0)
            self.assertEqual(doc.metadata["geometry_scale_mode"], "model_space")
            result = ReconstructionPipeline().run(doc)
            self.assertEqual(result.candidates[0].extents, (100.0, 60.0, 2.0))
            self.assertTrue(result.evaluations[0].valid)

    def test_first_angle_fallback_mirrors_views(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(
                Path(tmp) / "sheet.dxf", third_angle=False, with_arc_detail=False
            )
            doc = load_drawing(
                dxf, work_dir=Path(tmp) / "work", projection_default="first"
            )
            self.assertEqual({v.name for v in doc.views}, {"front", "top", "right"})
            self.assertEqual(
                ReconstructionPipeline().run(doc).candidates[0].extents,
                (100.0, 60.0, 2.0),
            )

    def test_vlm_labels_are_validated(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf")
            off = VLMClient(VLMConfig(model=""), "ocr")
            reply = {
                "projection": "third",
                "part_class": "flat",
                "reconstructable_from_views": True,
                "part_class_scores": {
                    "flat": 4,
                    "cylinder": 0,
                    "cone": -1,
                    "press_formed": -1,
                    "bent_sheet": 1,
                    "other": -2,
                },
                "views": [
                    {"id": 1, "type": "front", "confidence": 0.9, "reason": "largest"},
                    {"id": 2, "type": "top", "confidence": 0.8, "reason": "above"},
                    {"id": 3, "type": "right", "confidence": 0.7, "reason": "right"},
                    {
                        "id": 4,
                        "type": "detail",
                        "confidence": 0.6,
                        "reason": "rounded detail",
                    },
                    {
                        "id": 99,
                        "type": "front",
                        "confidence": 1.0,
                        "reason": "bogus id",
                    },
                ],
            }
            a = analyze_dxf(dxf, off, MockReason(reply), Path(tmp) / "work")["analysis"]
            d = a["vlm_decision"]
            self.assertTrue(d["used"])
            self.assertEqual(len(a["views"]), 4)
            self.assertEqual(len(d["rejected"]), 1)
            self.assertEqual(a["part_class"], "flat")
            self.assertAlmostEqual(sum(a["part_class_probabilities"].values()), 1.0)
            self.assertEqual(
                max(
                    a["part_class_probabilities"], key=a["part_class_probabilities"].get
                ),
                "flat",
            )
            by_id = {v["id"]: v for v in a["views"]}
            self.assertEqual(by_id[4]["label"], "detail")
            self.assertTrue(by_id[1]["source"].startswith("vlm_reason:"))
            self.assertEqual(by_id[1]["confidence"], 0.9)
            # the model contradicted the geometry-based fallback for some ids: that must surface as review items
            self.assertTrue(
                any("position fallback said" in r["issue"] for r in a["review"])
            )

            # A type outside the shared schema is rejected before domain-level
            # region validation; raw reply and the schema error remain in trace.
            reply["views"].append(
                {"id": 2, "type": "banana", "confidence": 1.0, "reason": "bad type"}
            )
            invalid = analyze_dxf(dxf, off, MockReason(reply), Path(tmp) / "invalid")[
                "analysis"
            ]
            self.assertEqual(invalid["vlm_decision"]["error"], "invalid reply")
            self.assertFalse(invalid["vlm_trace"][-1]["ok"])

    def test_shared_envelope_drives_dxf_view_labels(self):
        from cutplan_agent.reader.vlm_output import normalize_response

        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            payload = {
                "projection": "third",
                "part_class": "flat",
                "reconstructable_from_views": True,
                "part_class_scores": {
                    name: (4 if name == "flat" else 0) for name in PART_CLASSES
                },
                "views": [
                    {"id": 1, "type": "front", "confidence": 0.9, "reason": "front"},
                    {"id": 2, "type": "top", "confidence": 0.8, "reason": "top"},
                    {"id": 3, "type": "right", "confidence": 0.7, "reason": "right"},
                ],
            }
            envelope, _ = normalize_response(payload, "reason", "view_labels")
            reason = MockReason(envelope)
            analysis = analyze_dxf(
                dxf, VLMClient(VLMConfig(model="")), reason, Path(tmp) / "work"
            )["analysis"]
            self.assertEqual(analysis["part_class"], "flat")
            self.assertEqual(analysis["vlm_decision"]["accepted"], [1, 2, 3])
            self.assertEqual(reason.trace[-1]["response"], envelope)
            self.assertFalse(reason.trace[-1]["legacy_response"])

    def test_vlm_duplicate_front_keeps_higher_confidence(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf")
            off = VLMClient(VLMConfig(model=""), "ocr")
            reply = {
                "projection": "third",
                "views": [
                    {"id": 1, "type": "front", "confidence": 0.5},
                    {"id": 2, "type": "front", "confidence": 0.9},
                ],
            }
            a = analyze_dxf(dxf, off, MockReason(reply), Path(tmp) / "work")["analysis"]
            by_id = {v["id"]: v for v in a["views"]}
            self.assertEqual(by_id[2]["label"], "front")
            self.assertEqual(by_id[1]["label"], "other")

    def test_cli_analyze_only_and_reconstruct(self):
        with TemporaryDirectory() as tmp:
            dxf = synthetic_sheet(Path(tmp) / "sheet.dxf", with_arc_detail=False)
            self.assertEqual(
                main(
                    [
                        str(dxf),
                        "--analyze-only",
                        "--no-vlm",
                        "--output-dir",
                        str(Path(tmp) / "out"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        str(dxf),
                        "--no-vlm",
                        "--with-3d",
                        "--output-dir",
                        str(Path(tmp) / "out"),
                    ]
                ),
                0,
            )
            self.assertTrue((Path(tmp) / "out" / "reconstruction.step").exists())
            prov = json.loads(
                (Path(tmp) / "out" / "provenance.json").read_text(encoding="utf-8")
            )
            self.assertIn("sheet_analysis", json.dumps(prov))

    def test_cli_batch_discovers_nested_dxf_and_aggregates_reconstruction(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one").mkdir()
            (root / "two").mkdir()
            synthetic_sheet(root / "one" / "part_a.dxf", with_arc_detail=False)
            synthetic_sheet(root / "two" / "part_b.dxf", with_arc_detail=False)
            output = root / "batch_output"
            self.assertEqual(
                main(
                    [
                        str(root),
                        "--batch",
                        "--input-mode",
                        "dxf",
                        "--no-vlm",
                        "--with-3d",
                        "--output-dir",
                        str(output),
                    ]
                ),
                0,
            )

            predictions = json.loads(
                (output / "predictions.json").read_text(encoding="utf-8")
            )
            reconstruction = json.loads(
                (output / "reconstruction.json").read_text(encoding="utf-8")
            )
            self.assertEqual(predictions["total"], 2)
            self.assertEqual(
                predictions["predictions"][0]["prediction"]["drawing_no"], "76K3-99999"
            )
            self.assertEqual(reconstruction["summary"]["reconstructed"], 2)
            self.assertEqual(
                {item["id"] for item in reconstruction["items"]}, {"part_a", "part_b"}
            )
            self.assertTrue((output / "part_a" / "prediction.json").exists())
            self.assertTrue((output / "part_a" / "reconstruction.step").exists())
            self.assertTrue((output / "part_b" / "reconstruction.step").exists())

            prediction_output = root / "prediction_only_output"
            self.assertEqual(
                main(
                    [
                        str(root / "one"),
                        "--batch",
                        "--analyze-only",
                        "--input-mode",
                        "dxf",
                        "--no-vlm",
                        "--output-dir",
                        str(prediction_output),
                    ]
                ),
                0,
            )
            prediction_only = json.loads(
                (prediction_output / "predictions.json").read_text(encoding="utf-8")
            )
            self.assertEqual(prediction_only["status_counts"], {"predicted": 1})
            self.assertFalse(
                (prediction_output / "part_a" / "reconstruction.step").exists()
            )

    def test_batch_accuracy_uses_sibling_labels_after_prediction(self):
        from cutplan_agent.reader.batch import run_batch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder, label in (("one", "flat"), ("two", "bent_sheet")):
                sample = root / folder
                sample.mkdir()
                synthetic_sheet(sample / f"{folder}.dxf", with_arc_detail=False)
                (sample / "label.json").write_text(
                    json.dumps({"class": label}), encoding="utf-8"
                )
            reply = {
                "projection": "third",
                "part_class": "flat",
                "part_class_scores": {
                    "flat": 5,
                    "cylinder": 0,
                    "cone": 0,
                    "press_formed": 0,
                    "bent_sheet": 1,
                    "other": -1,
                },
                "reconstructable_from_views": True,
                "views": [
                    {"id": 1, "type": "top", "confidence": 0.9},
                    {"id": 2, "type": "front", "confidence": 0.9},
                    {"id": 3, "type": "right", "confidence": 0.9},
                ],
            }
            off = VLMClient(VLMConfig(model=""), "ocr")
            result = run_batch(
                [root],
                (off, MockReason(reply)),
                root / "out",
                analyze_only=True,
                input_mode="dxf",
            )
            accuracy = result["accuracy"]
            self.assertEqual(
                (
                    accuracy["correct"],
                    accuracy["labeled_count"],
                    accuracy["accuracy_pct"],
                ),
                (1, 2, 50.0),
            )
            by_label = {row["label"]: row for row in accuracy["by_label"]}
            self.assertEqual(
                (by_label["flat"]["count"], by_label["flat"]["correct"]), (1, 1)
            )
            self.assertEqual(
                (by_label["bent_sheet"]["count"], by_label["bent_sheet"]["correct"]),
                (1, 0),
            )
            self.assertIsNone(by_label["other"]["accuracy"])
            self.assertIn(
                "| flat | 1 | 1 | 100.00% |",
                (root / "out" / "accuracy.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()


REAL_NESTING = Path(__file__).resolve().parent / "fixtures" / "KD23041_CP.dxf"


@unittest.skipUnless(REAL_NESTING.exists(), "real nesting sample not present")
class RealNestingSheetTests(unittest.TestCase):
    def test_two_up_cutting_plan_yields_nine_captioned_plates(self):
        with TemporaryDirectory() as tmp:
            off = VLMClient(VLMConfig(model=""), "ocr")
            a = analyze_dxf(REAL_NESTING, off, off, Path(tmp) / "work")["analysis"]
            self.assertEqual(a["sheet_type"], "nesting")
            self.assertEqual(len(a["frames"]), 2)
            self.assertEqual(len(a["plates"]), 9)
            self.assertTrue(
                all(
                    "caption" in p and p["caption_matches_outline"] for p in a["plates"]
                ),
                a["plates"],
            )
            self.assertEqual(sum(p["thickness"] == 16 for p in a["plates"]), 2)
            self.assertEqual(
                main(
                    [
                        str(REAL_NESTING),
                        "--no-vlm",
                        "--output-dir",
                        str(Path(tmp) / "out"),
                    ]
                ),
                3,
            )
