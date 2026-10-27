"""Skill loading, class → dimensions → flat-pattern stage; never calls external models."""

import json
import os
import unittest
from math import pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cutplan_agent.reader.knowledge import (
    STAGE_TOPICS,
    load_domain_prompt,
    skill_system_prompt,
    topics,
)
from cutplan_agent.reader.unfold import (
    develop,
    evaluate_against_label,
    extract_params,
    run_unfold,
)
from cutplan_agent.reader.vlm import VLMClient, VLMConfig
from cutplan_agent.reader.vlm_output import normalize_response, response_schema


def unfold_reply(**fields):
    base = {
        "part_type": "cylinder",
        "thickness": None,
        "inner_dia": None,
        "length": None,
        "large_inner_dia": None,
        "small_inner_dia": None,
        "cone_height": None,
        "width": None,
        "segments": [],
        "bend_angles": [],
        "bend_radii": [],
        "outline": [],
        "head_type": None,
        "straight_flange": None,
        "holes": [],
        "part_name": None,
        "material": None,
        "quantity": None,
        "confidence": "high",
    }
    base.update(fields)
    return base


class FakeReason:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.enabled = True
        self.config = SimpleNamespace(model="fake-reasoner")

    def ask(
        self,
        prompt,
        images=None,
        system=None,
        want_json=True,
        *,
        task=None,
        skills=None,
    ):
        self.calls.append(
            {"prompt": prompt, "task": task, "skills": skills, "system": system}
        )
        return {**self.reply, "notes": "OD 100 → ID 94"}


class SkillLoadingTests(unittest.TestCase):
    def test_stage_topics_resolve_to_project_skill_files(self):
        found = topics()
        for stage, names in STAGE_TOPICS.items():
            for name in names:
                with self.subTest(stage=stage, topic=name):
                    self.assertIn(name, found)
                    doc = load_domain_prompt(name)
                    self.assertTrue(doc["text"].strip())
                    self.assertEqual(Path(doc["path"]).parent.parent.name, "skills")
        self.assertNotIn("~$README", found)

    def test_unknown_topic_and_custom_dir(self):
        with self.assertRaises(FileNotFoundError):
            load_domain_prompt("no_such_topic")
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "a").mkdir()
            (Path(tmp) / "a" / "custom.md").write_text("rule X", encoding="utf-8")
            with patch.dict(os.environ, {"CUTPLAN_SKILLS_DIR": tmp}):
                guide, records = skill_system_prompt(["custom"])
        self.assertIn("rule X", guide)
        self.assertEqual(records[0]["topic"], "custom")

    def test_reasoning_call_puts_skills_in_system_prompt_and_trace(self):
        response = normalize_response(
            unfold_reply(inner_dia=94, length=100, thickness=3),
            "reason",
            "unfold_params",
        )[0]
        for provider in ("openai", "anthropic"):
            with self.subTest(provider=provider):
                reply = Mock(ok=True)
                content = json.dumps(response)
                reply.json.return_value = (
                    {"choices": [{"message": {"content": content}}]}
                    if provider == "openai"
                    else {"content": [{"type": "text", "text": content}]}
                )
                client = VLMClient(
                    VLMConfig(provider=provider, model="m", api_key="k"), "reason"
                )
                with patch("requests.post", return_value=reply) as post:
                    data = client.ask(
                        "read",
                        task="unfold_params",
                        system="base",
                        skills=STAGE_TOPICS["unfold_params"],
                    )
                body = post.call_args.kwargs["json"]
                system = (
                    body["messages"][0]["content"]
                    if provider == "openai"
                    else body["system"]
                )
                self.assertIn('<skill topic="unfold_extract">', system)
                self.assertIn('<skill topic="drawing_conventions_kr">', system)
                self.assertTrue(system.endswith("base"))
                self.assertEqual(data["inner_dia"], 94)
                self.assertEqual(
                    [s["topic"] for s in client.trace[-1]["skills"]],
                    list(STAGE_TOPICS["unfold_params"]),
                )

    def test_view_labels_request_part_class_skills(self):
        from cutplan_agent.reader.vision_adapter import label_views_vlm

        reason = Mock(enabled=True, config=SimpleNamespace(model="m"))
        reason.ask.return_value = None
        view = SimpleNamespace(
            id=1, bbox_px=(0, 0, 10, 10), text_items=[], counts=lambda: {}
        )
        title = SimpleNamespace(as_dict=lambda: {})
        with (
            TemporaryDirectory() as tmp,
            patch(
                "cutplan_agent.reader.vision_adapter.save_debug",
                return_value=Path(tmp) / "x.png",
            ),
        ):
            label_views_vlm(
                [view], SimpleNamespace(width=10, height=10), title, reason, Path(tmp)
            )
        self.assertEqual(
            reason.ask.call_args.kwargs["skills"], STAGE_TOPICS["part_class"]
        )


class DevelopTests(unittest.TestCase):
    def test_cylinder_mean_diameter(self):
        b = develop("cylinder", {"inner_dia": 94, "length": 100, "thickness": 3})[
            "blank"
        ]
        self.assertAlmostEqual(b["length"], pi * 97)
        self.assertEqual(b["width"], 100)

    def test_cone_sector_arc_matches_mean_circumference(self):
        b = develop(
            "cone_frustum",
            {
                "large_inner_dia": 142,
                "small_inner_dia": 92,
                "cone_height": 150,
                "thickness": 4,
            },
        )["blank"]
        s = sqrt(150**2 + 25**2)
        self.assertAlmostEqual(b["outer_radius"], s * 146 / 50)
        self.assertAlmostEqual(b["outer_radius"] - b["inner_radius"], s)
        self.assertAlmostEqual(b["outer_radius"] * b["angle_deg"] * pi / 180, pi * 146)

    def test_bent_sheet_setback_and_k_factor(self):
        b = develop(
            "bent_sheet",
            {
                "segments": [120, 150],
                "bend_angles": [90],
                "bend_radii": [0],
                "width": 100,
                "thickness": 6,
            },
        )["blank"]
        self.assertAlmostEqual(b["length"], 120 + 150 - 12 + pi / 2 * 0.33 * 6)
        self.assertEqual(b["k_factors"], [0.33])
        with self.assertRaises(ValueError):
            develop(
                "bent_sheet",
                {
                    "segments": [120],
                    "bend_angles": [90],
                    "bend_radii": [0],
                    "width": 100,
                    "thickness": 6,
                },
            )

    def test_head_blank_and_missing_parameters(self):
        b = develop("head", {"inner_dia": 200, "thickness": 6, "straight_flange": 10})[
            "blank"
        ]
        self.assertAlmostEqual(
            b["blank_diameter"], 1.2 * (200 + 6) + 20
        )  # 2:1, Dm = ID + t
        with self.assertRaisesRegex(ValueError, "inner_dia"):
            develop("head", {"inner_dia": 0, "thickness": 6})


class StageTests(unittest.TestCase):
    def test_model_values_win_and_fallback_fills_gaps(self):
        drawing = SimpleNamespace(
            metadata={"dimensions": {"x": 100, "y": 100, "z": 100}}, views=[]
        )
        analysis = {
            "part_class": "cylinder",
            "title_block": {"thickness_mm": 3},
            "views": [],
        }
        reason = FakeReason(unfold_reply(inner_dia=94, thickness=3))
        record = extract_params("cylinder", analysis, drawing, reason)
        self.assertEqual(record["params"]["inner_dia"], 94)
        self.assertEqual(record["sources"]["inner_dia"], "vlm_reason:fake-reasoner")
        self.assertEqual(record["params"]["length"], 100)
        self.assertEqual(record["sources"]["length"], "overall_dimensions")
        self.assertEqual(reason.calls[0]["skills"], STAGE_TOPICS["unfold_params"])
        self.assertEqual(reason.calls[0]["task"], "unfold_params")
        self.assertIn("Decided part_type: cylinder", reason.calls[0]["prompt"])

    def test_run_unfold_writes_artifacts_and_skips_unknown_class(self):
        drawing = SimpleNamespace(
            metadata={"dimensions": {"x": 120, "y": 100, "z": 150}}, views=[]
        )
        analysis = {
            "part_class": "bent_sheet",
            "title_block": {"thickness_mm": 6},
            "views": [],
        }
        with TemporaryDirectory() as tmp:
            record = run_unfold(analysis, drawing, None, tmp)
            self.assertEqual(record["status"], "developed")
            for key in ("json", "dxf"):
                self.assertTrue(Path(record["artifacts"][key]).is_file())
            self.assertIn("BEND", Path(record["artifacts"]["dxf"]).read_text())
            self.assertEqual(
                run_unfold({"part_class": "other"}, drawing, None, tmp)["status"],
                "skipped",
            )
            failed = run_unfold(
                {"part_class": "cone", "title_block": {}, "views": []},
                drawing,
                None,
                tmp,
            )
            self.assertEqual(failed["status"], "failed")

    def test_label_evaluation(self):
        record = {"part_type": "cylinder", "blank": {"length": 304.73, "width": 100}}
        ev = evaluate_against_label(
            record,
            {"class": "cylinder", "flat_pattern": {"length": 304.73, "width": 100}},
        )
        self.assertTrue(ev["within_1pct"])
        self.assertIsNone(evaluate_against_label(record, {}))

    def test_schema_rejects_bad_unfold_reply(self):
        schema = response_schema("reason", "unfold_params")
        self.assertIn("unfold", schema["properties"])
        with self.assertRaises(ValueError):
            normalize_response(
                unfold_reply(part_type="sphere"), "reason", "unfold_params"
            )
        with self.assertRaises(ValueError):
            normalize_response(
                unfold_reply(outline=[[0, 0, 0]]), "reason", "unfold_params"
            )


if __name__ == "__main__":
    unittest.main()
