import importlib.util
import json
import re
import unittest
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from drawing_io import load_drawing
from geometry import segment_covered
from main import main
from models import DrawingDocument, ReconstructionCandidate
from pipeline import ReconstructionPipeline
from step4 import CandidateEvaluator
from step6 import ReconstructionExporter

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "box.json"


class ReconstructionTests(unittest.TestCase):
    def source(self):
        return json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_three_view_box_and_input_preservation(self):
        drawing = DrawingDocument.from_dict(self.source())
        original = deepcopy(asdict(drawing))
        result = ReconstructionPipeline().run(drawing)
        candidate = result.candidates[0]
        self.assertEqual((len(candidate.vertices), len(candidate.edges)), (8, 12))
        self.assertEqual(candidate.extents, (100.0, 60.0, 2.0))
        self.assertTrue(result.evaluations[0].valid)
        self.assertEqual(result.evaluations[0].checks["reprojection"].status, "pass")
        self.assertEqual(
            result.evaluations[0].checks["manufacturability"].status, "unknown"
        )
        self.assertEqual(result.review_request["status"], "needs_review")
        self.assertEqual(asdict(drawing), original)

    def test_units_scale_and_annotations_without_axis(self):
        value = self.source()
        value["metadata"].update(
            units="cm",
            drawing_scale=0.5,
            dimensions={"x": 10, "y": 6, "z": 0.2},
            sheet_thickness=0.2,
        )
        for view in value["views"]:
            view["origin"] = [v / 20 for v in view["origin"]]
            for primitive in view["primitives"]:
                primitive["points"] = [
                    [v / 20 for v in point] for point in primitive["points"]
                ]
        value["views"][0]["annotations"] = [{"kind": "dimension", "value": 10}]
        result = ReconstructionPipeline().run(DrawingDocument.from_dict(value))
        for actual, expected in zip(result.candidates[0].extents, (100, 60, 2)):
            self.assertAlmostEqual(actual, expected)
        self.assertTrue(result.evaluations[0].valid)
        self.assertEqual(result.candidates[0].parameters["sheet_thickness"], 2)

    def test_inconsistent_third_view_is_rejected(self):
        value = self.source()
        for primitive in value["views"][2]["primitives"]:
            for point in primitive["points"]:
                if point[0] == 190:
                    point[0] = 191
        result = ReconstructionPipeline().run(DrawingDocument.from_dict(value))
        self.assertFalse(any(e.valid for e in result.evaluations))

    def test_segment_gaps_are_not_treated_as_coverage(self):
        self.assertFalse(
            segment_covered(
                (0, 0), (10, 0), [((0, 0), (4, 0)), ((6, 0), (10, 0))], 0.01
            )
        )
        self.assertTrue(
            segment_covered(
                (0, 0), (10, 0), [((0, 0), (5, 0)), ((5, 0), (10, 0))], 0.01
            )
        )

    def test_circle_feature_remains_a_reviewable_hypothesis(self):
        value = self.source()
        value["views"][0]["primitives"].append(
            {"id": "circle", "kind": "circle", "center": [60, 11], "radius": 0.5}
        )
        result = ReconstructionPipeline().run(DrawingDocument.from_dict(value))
        feature_candidate = next(c for c in result.candidates if c.features)
        self.assertTrue(feature_candidate.features[0]["requires_review"])
        self.assertEqual(len(feature_candidate.vertices), 8)
        self.assertIn(
            "feature_topology",
            {i["kind"] for i in result.review_request["ambiguities"]},
        )
        limited = ReconstructionPipeline(max_candidates=1).run(
            DrawingDocument.from_dict(value)
        )
        self.assertEqual(len(limited.candidates), 1)
        self.assertIn(
            "feature_topology",
            {i["kind"] for i in limited.review_request["ambiguities"]},
        )

    def test_cli_exports_and_step_reference_integrity(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(main([str(EXAMPLE), "--output-dir", str(root)]), 0)
            step = (root / "reconstruction.step").read_text(encoding="utf-8")
            definitions = re.findall(r"^#(\d+)=", step, re.MULTILINE)
            references = re.findall(r"#(\d+)", step)
            self.assertEqual(len(definitions), len(set(definitions)))
            self.assertTrue(set(references) <= set(definitions))
            self.assertEqual(step.count("CARTESIAN_POINT("), 8)
            self.assertEqual(step.count("POLYLINE("), 12)
            self.assertIn("GEOMETRICALLY_BOUNDED_WIREFRAME_SHAPE_REPRESENTATION", step)
            self.assertNotIn("MANIFOLD_SOLID_BREP", step)
            parameters = json.loads(
                (root / "parameters.json").read_text(encoding="utf-8")
            )
            self.assertEqual(parameters["extents"], {"x": 100, "y": 60, "z": 2})
            provenance = json.loads(
                (root / "provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(provenance["review_request"]["status"], "needs_review")
            self.assertTrue(provenance["metadata"]["source_sha256"])

    def test_dimension_failure_does_not_export_step(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = self.source()
            value["metadata"]["dimensions"]["x"] = 101
            source = root / "bad.json"
            source.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(
                main([str(source), "--output-dir", str(root / "output")]), 2
            )
            self.assertFalse((root / "output" / "reconstruction.step").exists())
            self.assertTrue((root / "output" / "report.md").exists())

    def test_invalid_input_and_edges(self):
        for bad in (0.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                ReconstructionPipeline(tolerance=bad)
        candidate = ReconstructionCandidate("bad", [(0, 0, 0), (1, 0, 0)], [(0, 2)])
        self.assertEqual(
            CandidateEvaluator().validate_geometry(candidate).status, "fail"
        )
        with self.assertRaises(ValueError):
            ReconstructionExporter().export_step(candidate, "unused.step")
        value = self.source()
        value["metadata"]["sheet_thickness"] = float("nan")
        with self.assertRaises(ValueError):
            ReconstructionPipeline().run(DrawingDocument.from_dict(value))

    def test_output_reuse_and_stale_step_removal(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "output"
            self.assertEqual(main([str(EXAMPLE), "--output-dir", str(out)]), 0)
            before = (out / "reconstruction.step").read_bytes()
            self.assertEqual(main([str(EXAMPLE), "--output-dir", str(out)]), 1)
            self.assertEqual((out / "reconstruction.step").read_bytes(), before)
            bad = self.source()
            bad["metadata"]["dimensions"]["x"] = 101
            source = root / "bad.json"
            source.write_text(json.dumps(bad), encoding="utf-8")
            self.assertEqual(
                main([str(source), "--output-dir", str(out), "--overwrite"]), 2
            )
            self.assertFalse((out / "reconstruction.step").exists())
            self.assertFalse((out / "parameters.json").exists())

    @unittest.skipUnless(
        importlib.util.find_spec("ezdxf"), "Optional DXF dependency unavailable"
    )
    def test_dxf_layer_adapter(self):
        import ezdxf

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "box.dxf"
            document = ezdxf.new()
            document.header["$INSUNITS"] = 4
            for view in self.source()["views"]:
                layer = view["name"].upper()
                document.layers.add(layer)
                points = [primitive["points"][0] for primitive in view["primitives"]]
                document.modelspace().add_lwpolyline(
                    points, close=True, dxfattribs={"layer": layer}
                )
            document.saveas(path)
            result = ReconstructionPipeline().run(load_drawing(path))
            self.assertEqual(result.candidates[0].extents, (100, 60, 2))
            self.assertEqual(len(result.candidates[0].edges), 12)
            self.assertTrue(result.evaluations[0].valid)
            self.assertIn(
                "view_alignment",
                {i["kind"] for i in result.review_request["ambiguities"]},
            )


if __name__ == "__main__":
    unittest.main()
