"""Shared VLM protocol and transport regressions; never call external models."""
import json
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from vlm import VLMClient, VLMConfig, extract_json, read_ocr_task
from vlm_output import PART_CLASSES, normalize_response, response_schema


def title_response():
    return normalize_response({"drawing_no": "SYN-00009", "material": "SUS304",
                               "thickness_mm": 3.0, "scale": "1/1", "projection": "third"},
                              "reason", "title_block")[0]


def reason_response():
    return normalize_response({
        "projection": "third", "part_class": "bent_sheet",
        "part_class_scores": {name: (4.0 if name == "bent_sheet" else 0.0) for name in PART_CLASSES},
        "reconstructable_from_views": True,
        "views": [{"id": 1, "type": "front", "confidence": 0.9, "reason": "main view"}],
        "notes": "One straight bend is visible.",
    }, "reason", "view_labels")[0]


class SharedVLMOutputTests(unittest.TestCase):
    def test_reasoning_defaults_to_server_constrained_json(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(VLMConfig().output_format, "json_schema")
            self.assertEqual(VLMConfig.from_env("reason").output_format, "json_schema")
            self.assertEqual(VLMConfig.from_env("ocr").output_format, "raw")
        for provider in ("openai", "anthropic"):
            with self.subTest(provider=provider):
                response = reason_response()
                reply = Mock(ok=True)
                reply.json.return_value = (
                    {"choices": [{"message": {"content": json.dumps(response)}, "finish_reason": "stop"}]}
                    if provider == "openai" else {"content": [{"type": "text", "text": json.dumps(response)}]}
                )
                client = VLMClient(VLMConfig(provider=provider, model="reason"), "reason")
                with patch("requests.post", return_value=reply) as post:
                    self.assertIsNotNone(client.ask("Classify.", task="view_labels"))
                body = post.call_args.kwargs["json"]
                if provider == "openai":
                    self.assertTrue(body["response_format"]["json_schema"]["strict"])
                else:
                    self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
                self.assertTrue(client.trace[-1]["structured_output_requested"])

    def test_constrained_output_rejects_legacy_prose_and_partial_envelopes(self):
        envelope = reason_response()
        partial = dict(envelope)
        del partial["notes"]
        for raw in (json.dumps(envelope["reasoning"]), json.dumps(partial),
                    "```json\n"+json.dumps(envelope)+"\n```",
                    "Here is the result: "+json.dumps(envelope),
                    json.dumps(envelope)+" trailing text"):
            with self.subTest(raw=raw[:60]):
                client = VLMClient(VLMConfig(model="reason"), "reason")
                with patch.object(client, "_call_openai", return_value=raw) as call:
                    self.assertIsNone(client.ask("Classify.", task="view_labels"))
                call.assert_called_once()
                self.assertTrue(client.trace[-1]["structured_output_requested"])
                self.assertFalse(client.trace[-1]["ok"])
                self.assertIsNone(client.trace[-1]["response"])

    def test_unsupported_schema_is_reported_without_unconstrained_retry(self):
        for provider in ("openai", "anthropic"):
            with self.subTest(provider=provider):
                reply = Mock(ok=False, status_code=400, text="json_schema is not supported")
                client = VLMClient(VLMConfig(provider=provider, model="reason"), "reason")
                with patch("requests.post", return_value=reply) as post:
                    self.assertIsNone(client.ask("Classify.", task="view_labels"))
                post.assert_called_once()
                self.assertIn("json_schema is not supported", client.trace[-1]["error"])
                self.assertTrue(client.trace[-1]["structured_output_requested"])

    @unittest.skipUnless(importlib.util.find_spec("xgrammar"), "XGrammar is supplied by the vLLM server environment")
    def test_real_xgrammar_compiles_task_schemas_and_rejects_invalid_class(self):
        import xgrammar as xgr

        # CPU-only byte vocabulary: no model download, GPU or inference server.
        tokenizer = xgr.TokenizerInfo([bytes([i]) for i in range(256)]+[b"<eos>"], stop_token_ids=256)
        compiler = xgr.GrammarCompiler(tokenizer, max_threads=1)
        texts, _ = normalize_response([{"text": "100", "bbox": [1, 2, 30, 12], "kind": "dimension"}],
                                      "reason", "text_extraction")
        confirmation, _ = normalize_response({"pick": 1, "confidence": 0.8, "reason": "matches"},
                                             "reason", "candidate_confirmation")
        for response in (texts, title_response(), reason_response(), confirmation):
            with self.subTest(task=response["task"]):
                compiled = compiler.compile_json_schema(response_schema("reason", response["task"]))
                matcher = xgr.GrammarMatcher(compiled)
                self.assertTrue(matcher.accept_string(json.dumps(response)))
                self.assertTrue(matcher.accept_token(256))
        compiled = compiler.compile_json_schema(response_schema("reason", "view_labels"))
        bad = reason_response()
        bad["reasoning"]["part_class"] = "banana"
        self.assertFalse(xgr.GrammarMatcher(compiled).accept_string(json.dumps(bad)))
        self.assertFalse(xgr.GrammarMatcher(compiled).accept_string('```json\n'))

    def test_ocr_is_raw_for_all_providers_and_legacy_output_settings(self):
        raw = "품명 BENT_SHEET\nMATERIAL SA516-70, 2t\n" + "unstructured text { [\n" * 300
        for provider in ("openai", "anthropic"):
            for mode in ("raw", "prompt", "json_schema"):
                with self.subTest(provider=provider, mode=mode):
                    reply = Mock(ok=True)
                    reply.json.return_value = (
                        {"choices": [{"message": {"content": raw}, "finish_reason": "stop"}]}
                        if provider == "openai" else {"content": [{"type": "text", "text": raw}]}
                    )
                    client = VLMClient(VLMConfig(provider=provider, model="ocr", output_format=mode), "ocr")
                    with patch("requests.post", return_value=reply) as post, \
                         patch("vlm.extract_json", side_effect=AssertionError("OCR must not parse JSON")):
                        result = client.ask("Free OCR.", task="title_block")
                    self.assertEqual(result, raw)
                    self.assertEqual(client.trace[-1]["raw"], raw)
                    self.assertEqual(client.trace[-1]["output_format"], "raw")
                    self.assertTrue(client.trace[-1]["ok"])
                    self.assertFalse(client.trace[-1]["structured_output_requested"])
                    body = post.call_args.kwargs["json"]
                    self.assertEqual(body["messages"][-1]["content"][0]["text"], "Free OCR.")
                    self.assertNotIn("response_format", body)
                    self.assertNotIn("output_config", body)

    def test_ocr_failure_or_empty_text_never_calls_reasoner(self):
        for raw in ("", "   "):
            with self.subTest(raw=raw):
                ocr = VLMClient(VLMConfig(model="ocr"), "ocr")
                reason = VLMClient(VLMConfig(model="reason"), "reason")
                with patch.object(ocr, "_call_openai", return_value=raw), \
                     patch.object(reason, "_call_openai") as reason_call:
                    self.assertIsNone(read_ocr_task(ocr, reason, [], task="title_block", instructions="Read fields."))
                reason_call.assert_not_called()
                self.assertFalse(ocr.trace[-1]["ok"])
        ocr = VLMClient(VLMConfig(model="ocr"), "ocr")
        reason = VLMClient(VLMConfig(model="reason"), "reason")
        with patch.object(ocr, "_call_openai", side_effect=RuntimeError("connection failed")), \
             patch.object(reason, "_call_openai") as reason_call:
            self.assertIsNone(read_ocr_task(ocr, reason, [], task="title_block", instructions="Read fields."))
        reason_call.assert_not_called()

    def test_reasoning_format_failure_does_not_invalidate_successful_raw_ocr(self):
        ocr = VLMClient(VLMConfig(model="ocr"), "ocr")
        reason = VLMClient(VLMConfig(model="reason"), "reason")
        with patch.object(ocr, "_call_openai", return_value="MATERIAL SS400, 2t"), \
             patch.object(reason, "_call_openai", return_value='{"type":"title_block"}'):
            self.assertIsNone(read_ocr_task(ocr, reason, [], task="title_block", instructions="Read fields."))
        self.assertTrue(ocr.trace[-1]["ok"])
        self.assertFalse(reason.trace[-1]["ok"])
        self.assertIn("complete task envelope", reason.trace[-1]["error"])

    def test_unavailable_reasoner_uses_tesseract_not_fabricated_text_positions(self):
        from vision_reader import read_texts, TextItem

        for reason in (None, VLMClient(VLMConfig(model=""), "reason")):
            with self.subTest(reason=reason):
                ocr = VLMClient(VLMConfig(model="ocr"), "ocr")
                fallback = [TextItem("100", (1, 2, 30, 12), "dimension")]
                with patch.object(ocr, "_call_openai", return_value="100"), \
                     patch("vision_reader.tiles", return_value=[(0, 0, 100, 100)]), \
                     patch("vision_reader.crop", return_value=Path("tile.png")), \
                     patch("vision_reader.ocr_tesseract", return_value=fallback) as tesseract:
                    texts, source = read_texts(Mock(), ocr, Path("unused"), reason=reason)
                self.assertEqual(texts, fallback)
                self.assertEqual(source, "tesseract")
                self.assertTrue(ocr.trace[-1]["ok"])
                tesseract.assert_called_once()

    def test_reasoning_text_boxes_outside_tile_are_not_used(self):
        from vision_reader import ocr_vlm

        response, _ = normalize_response([
            {"text": "100", "bbox": [1, 2, 30, 12], "kind": "dimension"},
            {"text": "200", "bbox": [50, 50, 150, 60], "kind": "dimension"},
        ], "reason", "text_extraction")
        ocr = VLMClient(VLMConfig(model="ocr"), "ocr")
        reason = VLMClient(VLMConfig(model="reason"), "reason")
        with patch.object(ocr, "_call_openai", return_value="100 200"), \
             patch.object(reason, "_call_openai", return_value=json.dumps(response)), \
             patch("vision_reader.tiles", return_value=[(100, 200, 200, 300)]), \
             patch("vision_reader.crop", return_value=Path("tile.png")):
            items = ocr_vlm(Mock(), ocr, Path("unused"), reason=reason)
        self.assertEqual([item.text for item in items], ["100"])

    def test_all_roles_and_tasks_share_top_level_keys(self):
        ocr = title_response()
        reason = reason_response()
        confirmation, _ = normalize_response({"pick": 1, "confidence": 0.8,
                                              "reason": "matches", "problems": []},
                                             "reason", "candidate_confirmation")
        self.assertEqual(ocr.keys(), reason.keys())
        self.assertEqual(reason.keys(), confirmation.keys())
        self.assertIsNone(ocr["reasoning"])
        self.assertIsNone(reason["title_block"])
        self.assertIsNone(confirmation["reasoning"])
        self.assertEqual(confirmation["confirmation"]["pick"], 1)
        texts, _ = normalize_response([{"text": "100", "bbox": [1, 2, 30, 12], "kind": "dimension"}],
                                      "ocr", "text_extraction")
        self.assertEqual(texts.keys(), ocr.keys())

    def test_text_extraction_legacy_array_and_invalid_boxes(self):
        legacy = [{"text": "100", "bbox": [1, 2, 30, 12], "kind": "dimension"}]
        result, converted = normalize_response(legacy, "ocr", "text_extraction")
        self.assertTrue(converted)
        self.assertEqual(result["text_extraction"]["items"], legacy)
        for box in ([1, 2, 3], [3, 2, 1, 5], [-1, 0, 10, 10], [1, 2, True, 4]):
            legacy[0]["bbox"] = box
            with self.subTest(box=box), self.assertRaises(ValueError):
                normalize_response(legacy, "ocr", "text_extraction")

    def test_vision_ocr_raw_is_structured_by_reasoner_and_offsets_tile_coordinates(self):
        from vision_reader import ocr_vlm

        response, _ = normalize_response([{"text": "100", "bbox": [1, 2, 30, 12], "kind": "dimension"}],
                                         "reason", "text_extraction")
        client = VLMClient(VLMConfig(model="test"), "ocr")
        reason = VLMClient(VLMConfig(model="test-reason"), "reason")
        with patch.object(client, "_call_openai", return_value="100") as ocr_call, \
             patch.object(reason, "_call_openai", return_value=json.dumps(response)) as reason_call, \
             patch("vision_reader.tiles", return_value=[(100, 200, 200, 300)]), \
             patch("vision_reader.crop", return_value=Path("tile.png")):
            items = ocr_vlm(Mock(), client, Path("unused"), reason=reason)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].bbox, (101, 202, 130, 212))
        self.assertEqual(client.trace[-1]["raw"], "100")
        self.assertEqual(ocr_call.call_args.args[0], "Free OCR.")
        self.assertIn('"100"', reason_call.call_args.args[0])
        self.assertEqual(reason.trace[-1]["response"], response)

    def test_title_adapters_structure_raw_ocr_with_reasoning_model(self):
        from dxf_adapter import parse_title_block
        from vision_adapter import parse_title
        from vision_reader import TextItem

        response = title_response()
        for adapter in ("dxf", "vision"):
            with self.subTest(adapter=adapter):
                client = VLMClient(VLMConfig(model="test"), "ocr")
                reason = VLMClient(VLMConfig(model="test-reason"), "reason")
                raw = "DW'G NO SYN-00009\nMATERIAL SUS304, 3t\nSCALE 1/1"
                with patch.object(client, "_call_openai", return_value=raw) as ocr_call, \
                     patch.object(reason, "_call_openai", return_value=json.dumps(response)) as reason_call:
                    if adapter == "dxf":
                        with patch("dxf_adapter.render", return_value=Path("title.png")):
                            title = parse_title_block([], None, client, Path("unused"), reason=reason)
                    else:
                        sheet = Mock(width=1000, height=1000)
                        with patch("vision_adapter.crop", return_value=Path("title.png")):
                            title = parse_title([TextItem("PART NAME", (10, 10, 100, 30), "title")],
                                                sheet, client, Path("unused"), reason=reason)
                self.assertEqual(title.drawing_no, "SYN-00009")
                self.assertEqual(title.thickness_mm, 3.0)
                self.assertEqual(title.scale, 1.0)
                self.assertEqual(client.trace[-1]["raw"], raw)
                self.assertEqual(client.trace[-1]["output_format"], "raw")
                self.assertEqual(reason.trace[-1]["response"], response)
                self.assertEqual(ocr_call.call_args.args[0], "Free OCR.")
                self.assertIn(json.dumps(raw), reason_call.call_args.args[0])
                self.assertIn("vlm_reason:test-reason", title.sources["drawing_no"])

    def test_vision_reasoning_and_confirmation_consume_common_envelopes(self):
        from drawing_io import load_drawing
        from pipeline import ReconstructionPipeline
        from vision_adapter import (TitleInfo, VisionView, confirm_candidates,
                                    label_views_vlm)

        response = reason_response()
        response["reasoning"]["views"][0]["overall_width_mm"] = 120.0
        response["reasoning"]["views"][0]["overall_height_mm"] = 100.0
        client = VLMClient(VLMConfig(model="test"), "reason")
        view = VisionView(1, (10, 20, 200, 300), 1000)
        with patch.object(client, "_call_openai", return_value=json.dumps(response)), \
             patch("vision_adapter.save_debug", return_value=Path("views.png")):
            decision = label_views_vlm([view], Mock(width=1000, height=1000), TitleInfo(), client, Path("unused"))
        self.assertEqual(decision["part_class"], "bent_sheet")
        self.assertEqual(view.overall_mm["overall_width_mm"], 120.0)
        confirmation, _ = normalize_response({"pick": 1, "confidence": 0.8, "reason": "matches", "problems": []},
                                             "reason", "candidate_confirmation")
        result = ReconstructionPipeline().run(load_drawing(Path(__file__).resolve().parents[1]/"examples"/"box.json"))
        with TemporaryDirectory() as tmp, \
             patch.object(client, "_call_openai", return_value=json.dumps(confirmation)):
            decision = confirm_candidates(result, client, Path(tmp))
        self.assertEqual(decision["pick"], result.candidates[0].id)
        self.assertEqual(decision["response"], confirmation)
        self.assertEqual(client.trace[-1]["response"], confirmation)

    def test_legacy_reply_is_normalized_without_inventing_missing_facts(self):
        result, legacy = normalize_response({"drawing_no": "SYN-1"}, "ocr", "title_block")
        self.assertTrue(legacy)
        self.assertEqual(result["title_block"]["drawing_no"], "SYN-1")
        self.assertIsNone(result["title_block"]["thickness_mm"])

    def test_empty_or_unrelated_json_is_not_an_ocr_success(self):
        for data in ({}, {"answer": "nothing"}, [], None):
            with self.subTest(data=data), self.assertRaises(ValueError):
                normalize_response(data, "ocr", "title_block")

    def test_schema_rejects_wrong_envelope_and_payload_types(self):
        for key, value in (("schema_version", True), ("role", "ocr"), ("task", "title_block"),
                           ("title_block", {}), ("notes", 12)):
            result = reason_response()
            result[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                normalize_response(result, "reason", "view_labels")
        bad = title_response()
        del bad["title_block"]["units"]
        with self.assertRaises(ValueError):
            normalize_response(bad, "reason", "title_block")

    def test_bad_scores_and_boolean_dimensions_are_rejected(self):
        for value in (float("nan"), float("inf"), "0.9", True):
            result = reason_response()
            result["reasoning"]["part_class_scores"]["flat"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_response(result, "reason", "view_labels")
        result = title_response()
        result["title_block"]["thickness_mm"] = True
        with self.assertRaises(ValueError):
            normalize_response(result, "reason", "title_block")

    def test_invalid_confidence_and_view_types_are_rejected(self):
        for key, value in (("id", True), ("id", 0), ("type", "banana"),
                           ("confidence", 1.1), ("overall_width_mm", -2)):
            result = reason_response()
            result["reasoning"]["views"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                normalize_response(result, "reason", "view_labels")

    def test_zero_scale_denominator_is_rejected(self):
        result = title_response()
        result["title_block"]["scale"] = "1/0"
        with self.assertRaises(ValueError):
            normalize_response(result, "reason", "title_block")

    def test_inline_thinking_is_not_parsed_as_final_json(self):
        self.assertEqual(extract_json('<think>{"pick":99}</think>\n{"pick":1}'), {"pick": 1})
        with self.assertRaises(ValueError):
            extract_json('<think>{"pick":99}')

    def test_reasoning_tasks_providers_and_output_modes_use_the_same_schema(self):
        texts, _ = normalize_response([{"text": "100", "bbox": [1, 2, 30, 12], "kind": "dimension"}],
                                      "reason", "text_extraction")
        confirmation, _ = normalize_response({"pick": None, "confidence": 0.2, "reason": "unclear", "problems": []},
                                             "reason", "candidate_confirmation")
        for provider in ("openai", "anthropic"):
            for mode in ("prompt", "json_schema"):
                for response in (title_response(), reason_response(), texts, confirmation):
                    role, task = response["role"], response["task"]
                    with self.subTest(provider=provider, mode=mode, role=role):
                        wire_response = ({"choices": [{"message": {"content": json.dumps(response)},
                                                       "finish_reason": "stop"}]}
                                         if provider == "openai" else
                                         {"content": [{"type": "thinking", "thinking": "private"},
                                                      {"type": "text", "text": json.dumps(response)}]})
                        reply = Mock(ok=True)
                        reply.json.return_value = wire_response
                        client = VLMClient(VLMConfig(provider=provider, model="test-vlm", output_format=mode), role)
                        with patch("requests.post", return_value=reply) as post:
                            result = client.ask("Read this drawing.", task=task)
                        self.assertIsNotNone(result, client.trace)
                        self.assertEqual(client.trace[-1]["response"], response)
                        self.assertFalse(client.trace[-1]["legacy_response"])
                        body = post.call_args.kwargs["json"]
                        prompt = body["messages"][-1]["content"][-1]["text"]
                        self.assertIn("OUTPUT CONTRACT", prompt)
                        if mode == "json_schema":
                            actual = (body["response_format"]["json_schema"]["schema"] if provider == "openai"
                                      else body["output_config"]["format"]["schema"])
                            self.assertEqual(actual, response_schema(role, task))
                        else:
                            self.assertNotIn("response_format", body)
                            self.assertNotIn("output_config", body)

    def test_failed_schema_validation_is_traced_without_success(self):
        response = reason_response()
        response["reasoning"]["reconstructable_from_views"] = "true"
        client = VLMClient(VLMConfig(model="test"), "reason")
        with patch.object(client, "_call_openai", return_value=json.dumps(response)):
            self.assertIsNone(client.ask("Classify.", task="view_labels"))
        trace = client.trace[-1]
        self.assertFalse(trace["ok"])
        self.assertIsNone(trace["response"])
        self.assertIn("ValueError", trace["error"])
        self.assertIn("reconstructable_from_views", trace["raw"])

    def test_legacy_reply_is_explicitly_marked_in_trace(self):
        client = VLMClient(VLMConfig(model="test", output_format="prompt"), "reason")
        with patch.object(client, "_call_openai", return_value='{"drawing_no":"SYN-1"}'):
            result = client.ask("Read.", task="title_block")
        self.assertEqual(result["drawing_no"], "SYN-1")
        self.assertTrue(client.trace[-1]["legacy_response"])

    def test_empty_content_distinguishes_reasoning_only_or_token_limit(self):
        reply = Mock()
        reply.json.return_value = {"choices": [{"message": {"content": None, "reasoning_content": "thinking"},
                                                "finish_reason": "length"}]}
        client = VLMClient(VLMConfig(model="test"), "reason")
        with patch("requests.post", return_value=reply):
            self.assertIsNone(client.ask("Read.", task="title_block"))
        self.assertIn("empty final content", client.trace[-1]["error"])
        self.assertIn("finish_reason='length'", client.trace[-1]["error"])

    def test_openai_text_content_blocks_are_normalized(self):
        response = title_response()
        reply = Mock()
        reply.json.return_value = {"choices": [{"message": {"content": [
            {"type": "text", "text": json.dumps(response)}]}, "finish_reason": "stop"}]}
        client = VLMClient(VLMConfig(model="test"), "reason")
        with patch("requests.post", return_value=reply):
            self.assertIsNotNone(client.ask("Read.", task="title_block"))
        self.assertEqual(client.trace[-1]["response"], response)

    def test_environment_sets_independent_output_formats(self):
        with patch.dict(os.environ, {"CUTPLAN_OCR_OUTPUT_FORMAT": "prompt",
                                     "CUTPLAN_REASON_OUTPUT_FORMAT": "json_schema"}):
            self.assertEqual(VLMConfig.from_env("ocr").output_format, "prompt")
            self.assertEqual(VLMConfig.from_env("reason").output_format, "json_schema")


if __name__ == "__main__":
    unittest.main()
