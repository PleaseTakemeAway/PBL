"""scripts/build_synthetic.py: 같은 입력이면 같은 파일, 정답 식의 검산, reader 와의 대조."""

import importlib.util
import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cutplan_agent.reader.dxf_adapter import load_dxf_document
from cutplan_agent.reader.dxf_reader import read_dxf
from cutplan_agent.reader.unfold import develop, fallback_params
from cutplan_agent.reader.vlm import VLMClient, VLMConfig

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_synthetic", ROOT / "scripts" / "build_synthetic.py"
)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def reader_params(label: dict) -> tuple[str, dict]:
    """label 의 형상 치수를 reader 전개 함수(unfold.develop)의 입력으로 바꾼다. reader 는 안지름을 받는다."""
    p, t = label["params"], label["thickness"]
    cls = label["class"]
    if cls == "flat":
        L, W = p["length"], p["width"]
        return "flat", {"outline": [[0, 0], [L, 0], [L, W], [0, W]], "thickness": t}
    if cls == "bent_sheet":
        return "bent_sheet", {
            "width": p["width"],
            "segments": [p["leg_a"], p["leg_b"]],
            "bend_angles": [90.0],
            "bend_radii": [p["bend_radius"]],
            "thickness": t,
        }
    if cls == "cylinder":
        return "cylinder", {
            "inner_dia": p["outer_diameter"] - 2 * t,
            "length": p["length"],
            "thickness": t,
        }
    if cls == "cone":
        big, small, h = (
            p["large_outer_diameter"],
            p["small_outer_diameter"],
            p["height"],
        )
        across = t / math.cos(math.atan((big - small) / 2 / h))  # 가로로 잰 판 두께
        return "cone_frustum", {
            "large_inner_dia": big - 2 * across,
            "small_inner_dia": small - 2 * across,
            "cone_height": p["height"],
            "thickness": t,
        }
    return "head", {
        "inner_dia": p["outer_diameter"] - 2 * t,
        "thickness": t,
        "straight_flange": p["straight_flange"],
    }


READER_KEYS = {
    "flat": (("length", "length"), ("width", "width")),
    "bent_sheet": (("length", "length"), ("width", "width")),
    "cylinder": (("length", "length"), ("width", "width")),
    "cone_frustum": (
        ("outer_radius", "sector_outer_radius"),
        ("inner_radius", "sector_inner_radius"),
        ("angle_deg", "sector_angle_deg"),
    ),
    "head": (("blank_diameter", "blank_diameter"),),
}


class BuildSyntheticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "a"
        gen.main(["--out", str(cls.out), "--no-png", "-q"])
        cls.labels = {
            p.parent.name: json.loads(p.read_text(encoding="utf-8"))
            for p in cls.out.glob("*/label.json")
        }

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_thirty_drawings_and_same_files_every_run(self):
        self.assertEqual(len(self.labels), 30)
        again = Path(self.tmp.name) / "b"
        gen.main(["--out", str(again), "--no-png", "-q"])
        for path in sorted(self.out.rglob("*.*")):
            other = again / path.relative_to(self.out)
            self.assertEqual(path.read_bytes(), other.read_bytes(), path.name)

    def test_cone_sector_closes_on_the_mean_circumference(self):
        for label in self.labels.values():
            if label["class"] != "cone":
                continue
            fp = label["flat_pattern"]
            d1 = fp["mean_diameters"][0]
            arc = fp["sector_outer_radius"] * math.radians(fp["sector_angle_deg"])
            self.assertAlmostEqual(arc, math.pi * d1, delta=0.05, msg=label["id"])
        fp = self.labels["cone_0019"]["flat_pattern"]
        self.assertEqual(
            (
                fp["sector_outer_radius"],
                fp["sector_inner_radius"],
                fp["sector_angle_deg"],
            ),
            (443.87, 291.8, 59.18),
        )

    def test_head_is_a_half_ellipse_on_a_short_straight_flange(self):
        label = self.labels["press_formed_0027"]
        self.assertEqual(label["params"]["straight_flange"], 6)  # 안지름 188 의 3%
        self.assertEqual(label["extents"], [200, 200, 59])  # SF + 안쪽 깊이 188/4 + t
        # 두께 가운데 반타원 (반축 97, 50) 의 길이 236.85 + 2 × SF
        self.assertEqual(label["flat_pattern"]["blank_diameter"], 248.85)
        dxf = self.out / "press_formed_0027" / "press_formed_0027.dxf"
        entities, _ = read_dxf(dxf)
        ellipse = [e for e in entities if e.attributes.get("source") == "ellipse"]
        self.assertTrue(ellipse)
        self.assertFalse(
            [e for e in entities if e.kind == "arc" and e.layer == "OUTLINE"]
        )
        self.assertTrue([e for e in entities if e.layer == "PHANTOM"])  # TL

    def test_reader_measures_the_straight_flange(self):
        off = VLMClient(VLMConfig(model=""), "ocr")
        for name, label in sorted(self.labels.items()):
            if label["class"] != "press_formed":
                continue
            with TemporaryDirectory() as work:
                doc = load_dxf_document(self.out / name / f"{name}.dxf", off, off, work)
            title = {"title_block": {"thickness_mm": label["thickness"]}}
            params, _ = fallback_params("head", title, doc)
            self.assertEqual(
                params["straight_flange"], label["params"]["straight_flange"], name
            )

    def test_formulas_reproduce_the_practitioner_answers(self):
        # data_v3/20261027example 의 정답 전개도 (docs/v3_upgrade.md 5.2절). 안지름 1000, t 20
        head = gen.head_blank(
            {"outer_diameter": 1040, "thickness": 20, "straight_flange": 30}
        )
        self.assertAlmostEqual(head["blank_diameter"], 1301.6, delta=0.05)
        cone = gen.cone_blank(
            {
                "large_outer_diameter": 1000 + 2 * 20 / math.cos(math.radians(30)),
                "small_outer_diameter": 422.6 + 2 * 20 / math.cos(math.radians(30)),
                "height": (1000 - 422.6) / 2 / math.tan(math.radians(30)),
                "thickness": 20,
            }
        )
        self.assertAlmostEqual(cone["sector_outer_radius"], 1023.09, delta=0.01)
        self.assertAlmostEqual(cone["sector_angle_deg"], 180.0, delta=0.01)
        shell = gen.cylinder_blank(
            {"outer_diameter": 1040, "length": 1500, "thickness": 20}
        )
        self.assertEqual((shell["length"], shell["width"]), (3204.42, 1500))

    def test_bent_sheet_uses_the_company_k_factor(self):
        fp = self.labels["bent_sheet_0007"]["flat_pattern"]
        self.assertEqual(fp["k_factor"], 0.33)  # R/t = 0 < 1
        self.assertEqual(fp["length"], 197.04)

    def test_reader_reads_dimensions_and_hole_notes(self):
        for name in ("flat_0001", "bent_sheet_0008", "cone_0019"):
            label = self.labels[name]
            entities, _ = read_dxf(self.out / name / label["files"]["dxf"])
            measured = sorted(e.measurement for e in entities if e.kind == "dimension")
            self.assertEqual(
                measured, sorted(d["value"] for d in label["dimensions"]), name
            )
            texts = {e.text for e in entities if e.kind == "text"}
            for note in label["hole_notes"].values():
                self.assertIn(note, texts)
            self.assertFalse([t for t in texts if t and "Ã" in t])

    def test_no_duplicate_lines(self):
        for name in ("flat_0001", "bent_sheet_0008"):
            entities, _ = read_dxf(self.out / name / f"{name}.dxf")
            lines = [
                (e.layer, *sorted(tuple(round(v, 6) for v in p) for p in e.points))
                for e in entities
                if e.kind == "line"
            ]
            self.assertEqual(len(lines), len(set(lines)), name)

    def test_reader_development_matches_the_labels(self):
        # 생성기와 reader 는 전개 식을 따로 구현했다. 같은 치수를 넣으면 같은 값이 나와야 한다 (30장).
        for label in self.labels.values():
            part_type, params = reader_params(label)
            blank = develop(part_type, params)["blank"]
            for mine, theirs in READER_KEYS[part_type]:
                self.assertAlmostEqual(
                    blank[mine],
                    label["flat_pattern"][theirs],
                    delta=0.01,
                    msg=f"{label['id']} {theirs}",
                )


if __name__ == "__main__":
    unittest.main()
