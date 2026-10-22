"""Structured reasoning output contract (legacy OCR envelopes remain readable).

OCR model calls return raw text; the reasoning model structures that text using
the text_extraction/title_block tasks defined here.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from math import isfinite
from typing import Any

PART_CLASSES = ("flat", "cylinder", "cone", "press_formed", "bent_sheet", "other")
VIEW_TYPES = (
    "front",
    "top",
    "bottom",
    "right",
    "left",
    "back",
    "section",
    "detail",
    "flat_pattern",
    "isometric",
    "table",
    "other",
)
TASK_BLOCKS = {
    "text_extraction": "text_extraction",
    "title_block": "title_block",
    "view_labels": "reasoning",
    "candidate_confirmation": "confirmation",
    "unfold_params": "unfold",
}
# part_type names of skills/02_prompts/unfold_extract.md (+ head from unfold_rules.md)
UNFOLD_PART_TYPES = (
    "cylinder",
    "cone_frustum",
    "bent_sheet",
    "flat",
    "head",
    "unknown",
)
UNFOLD_CONFIDENCE = ("high", "medium", "estimated", "unreadable")


def _object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


_STRING = {"type": "string"}
_NUMBER = {"type": "number"}
_PROJECTION = {"type": "string", "enum": ["first", "third"]}
TEXT_SCHEMA = _object(
    {
        "items": {
            "type": "array",
            "items": _object(
                {
                    "text": _STRING,
                    "bbox": {"type": "array", "items": _NUMBER},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "dimension",
                            "label",
                            "note",
                            "title",
                            "table",
                            "caption",
                            "other",
                        ],
                    },
                }
            ),
        },
    }
)
TITLE_SCHEMA = _object(
    {
        "drawing_no": _nullable(_STRING),
        "part_name": _nullable(_STRING),
        "material": _nullable(_STRING),
        "thickness_mm": _nullable(_NUMBER),
        "scale": _nullable(_STRING),
        "units": _nullable({"type": "string", "enum": ["mm", "inch"]}),
        "projection": _nullable(_PROJECTION),
        "weight_kg": _nullable(_NUMBER),
    }
)
VIEW_SCHEMA = _object(
    {
        "id": {"type": "integer"},
        "type": {"type": "string", "enum": list(VIEW_TYPES)},
        "confidence": _NUMBER,
        "reason": _STRING,
        "overall_width_mm": _nullable(_NUMBER),
        "overall_height_mm": _nullable(_NUMBER),
    }
)
REASONING_SCHEMA = _object(
    {
        "projection": _nullable(_PROJECTION),
        "part_class": _nullable({"type": "string", "enum": list(PART_CLASSES)}),
        "part_class_scores": _nullable(
            _object({name: _NUMBER for name in PART_CLASSES})
        ),
        "reconstructable_from_views": _nullable({"type": "boolean"}),
        "views": {"type": "array", "items": VIEW_SCHEMA},
    }
)
CONFIRMATION_SCHEMA = _object(
    {
        "pick": _nullable({"type": "integer"}),
        "confidence": _NUMBER,
        "reason": _STRING,
        "problems": {"type": "array", "items": _STRING},
    }
)
_NUMBERS = {"type": "array", "items": _NUMBER}
UNFOLD_SCHEMA = _object(
    {
        "part_type": {"type": "string", "enum": list(UNFOLD_PART_TYPES)},
        "thickness": _nullable(_NUMBER),
        "inner_dia": _nullable(_NUMBER),
        "length": _nullable(_NUMBER),
        "large_inner_dia": _nullable(_NUMBER),
        "small_inner_dia": _nullable(_NUMBER),
        "cone_height": _nullable(_NUMBER),
        "width": _nullable(_NUMBER),
        "segments": _NUMBERS,
        "bend_angles": _NUMBERS,
        "bend_radii": _NUMBERS,
        "outline": {"type": "array", "items": _NUMBERS},
        "head_type": _nullable(_STRING),
        "straight_flange": _nullable(_NUMBER),
        "holes": {
            "type": "array",
            "items": _object({"diameter": _NUMBER, "count": {"type": "integer"}}),
        },
        "part_name": _nullable(_STRING),
        "material": _nullable(_STRING),
        "quantity": _nullable({"type": "integer"}),
        "confidence": {"type": "string", "enum": list(UNFOLD_CONFIDENCE)},
    }
)
VLM_RESPONSE_SCHEMA = _object(
    {
        "schema_version": {"type": "integer", "enum": [1]},
        "role": {"type": "string", "enum": ["ocr", "reason"]},
        "task": {"type": "string", "enum": list(TASK_BLOCKS)},
        "text_extraction": _nullable(TEXT_SCHEMA),
        "title_block": _nullable(TITLE_SCHEMA),
        "reasoning": _nullable(REASONING_SCHEMA),
        "confirmation": _nullable(CONFIRMATION_SCHEMA),
        "unfold": _nullable(UNFOLD_SCHEMA),
        "notes": _STRING,
    }
)


def response_schema(role: str, task: str) -> dict:
    """Specialize the common shape: exactly one task block contains an object."""
    if role not in {"ocr", "reason"} or task not in TASK_BLOCKS:
        raise ValueError(f"unknown VLM role/task: {role}/{task}")
    schema = deepcopy(VLM_RESPONSE_SCHEMA)
    schema["properties"]["role"]["enum"] = [role]
    schema["properties"]["task"]["enum"] = [task]
    for block in TASK_BLOCKS.values():
        schema["properties"][block] = (
            schema["properties"][block]["anyOf"][0]
            if block == TASK_BLOCKS[task]
            else {"type": "null"}
        )
    return schema


def output_instructions(role: str, task: str) -> str:
    schema = response_schema(role, task)
    return (
        "\n\nOUTPUT CONTRACT (overrides any earlier output-format examples):\n"
        "Return ONE JSON object matching the schema below, without Markdown or prose. "
        f"Set role={json.dumps(role)}, task={json.dumps(task)}, schema_version=1. "
        f"Put the requested task values inside {TASK_BLOCKS[task]}; "
        "set the other task blocks to null. Put explanatory notes in the top-level notes string. "
        "Use null for unknown scalar facts; never invent values or scores. "
        "All numeric values must be finite. Confidence must be between 0 and 1. "
        "Scale is a ratio string, e.g. 1/4. View IDs and candidate picks are positive integers.\n"
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    )


def _validate(value: Any, schema: dict, path: str = "response") -> None:
    """Validate the small JSON Schema subset used by our contract, without deps."""
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                _validate(value, option, path)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: invalid nullable value")
    typ = schema["type"]
    matches = {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in (int, float),
    }
    if not matches[typ]:
        raise ValueError(f"{path}: expected {typ}")
    if typ in {"integer", "number"}:
        try:
            finite = isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError(f"{path}: number must be finite")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unexpected value {value!r}")
    if typ == "object":
        missing = set(schema["required"]) - value.keys()
        extra = value.keys() - schema["properties"].keys()
        if missing or extra:
            raise ValueError(
                f"{path}: missing={sorted(missing)}, extra={sorted(extra)}"
            )
        for key, child in schema["properties"].items():
            _validate(value[key], child, f"{path}.{key}")
    elif typ == "array":
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]")


def normalize_response(
    data: Any, role: str, task: str, *, allow_legacy: bool = True
) -> tuple[dict, bool]:
    """Validate the new envelope or migrate an old bare task JSON response.

    Legacy missing fields are represented by null/empty values, not guessed.
    The caller records this migration so a legacy reply is never mistaken for
    a model that actually followed the new envelope. Server-constrained calls
    set allow_legacy=False: the actual response must satisfy the full contract.
    """
    if allow_legacy and task == "text_extraction" and isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        raise ValueError("VLM response must be a JSON object")
    schema = response_schema(role, task)
    legacy = not any(
        key in data for key in ("schema_version", "role", "task", *TASK_BLOCKS.values())
    )
    if legacy:
        if not allow_legacy:
            raise ValueError(
                "structured response must use the complete task envelope; legacy JSON is not allowed"
            )
        block = TASK_BLOCKS[task]
        fields = schema["properties"][block]["properties"]
        if not fields.keys() & data.keys():
            raise ValueError(f"response contains no fields for task {task}")
        payload = {key: data.get(key) for key in fields}
        if task == "text_extraction":
            if not isinstance(payload["items"], list):
                raise ValueError("text_extraction.items: expected array")
            payload["items"] = [
                {
                    "text": item.get("text"),
                    "bbox": item.get("bbox"),
                    "kind": item.get("kind", "other"),
                }
                if isinstance(item, dict)
                else item
                for item in payload["items"]
            ]
        elif task == "view_labels":
            # Views are essential to this task: a missing list is an error.
            if not isinstance(payload["views"], list):
                raise ValueError("reasoning.views: expected array")
            payload["views"] = [
                {
                    key: item.get(key, "" if key == "reason" else None)
                    for key in VIEW_SCHEMA["properties"]
                }
                if isinstance(item, dict)
                else item
                for item in payload["views"]
            ]
        elif task == "candidate_confirmation":
            payload["reason"] = data.get("reason", "")
            payload["problems"] = data.get("problems", [])
        data = {
            "schema_version": 1,
            "role": role,
            "task": task,
            **{name: None for name in TASK_BLOCKS.values()},
            "notes": data.get("notes", ""),
            block: payload,
        }
    _validate(data, schema)
    block_data = data[TASK_BLOCKS[task]]
    if task == "text_extraction":
        for item in block_data["items"]:
            box = item["bbox"]
            if len(box) != 4 or min(box) < 0 or box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError(
                    "text bbox must contain [x0,y0,x1,y1] with nonnegative coordinates and positive area"
                )
            if not item["text"].strip():
                raise ValueError("text item must not be empty")
    if task == "title_block":
        scale = block_data["scale"]
        if scale is not None:
            ratio = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)\s*[/:]\s*(\d+(?:\.\d+)?)\s*", scale
            )
            if not ratio or not all(
                isfinite(float(v)) and float(v) > 0 for v in ratio.groups()
            ):
                raise ValueError(
                    "title_block.scale must be a positive ratio string or null"
                )
        if block_data["thickness_mm"] is not None and block_data["thickness_mm"] <= 0:
            raise ValueError("title_block.thickness_mm must be positive or null")
        if block_data["weight_kg"] is not None and block_data["weight_kg"] < 0:
            raise ValueError("title_block.weight_kg must be nonnegative or null")
    for view in block_data.get("views", []):
        if view["id"] < 1 or not 0 <= view["confidence"] <= 1:
            raise ValueError("view id must be positive and confidence must be in [0,1]")
        for key in ("overall_width_mm", "overall_height_mm"):
            if view[key] is not None and view[key] <= 0:
                raise ValueError(f"view {key} must be positive or null")
    if task == "unfold_params":
        for key in (
            "thickness",
            "inner_dia",
            "length",
            "large_inner_dia",
            "small_inner_dia",
            "cone_height",
            "width",
            "straight_flange",
        ):
            if block_data[key] is not None and block_data[key] < 0:
                raise ValueError(f"unfold.{key} must be nonnegative or null")
        if any(len(point) != 2 for point in block_data["outline"]):
            raise ValueError("unfold.outline points must be [x, y]")
    if task == "candidate_confirmation":
        if not 0 <= block_data["confidence"] <= 1:
            raise ValueError("confirmation.confidence must be in [0,1]")
        if block_data["pick"] is not None and block_data["pick"] < 1:
            raise ValueError("confirmation.pick must be positive or null")
    return data, legacy


def task_payload(response: dict) -> dict:
    """Project the common response onto the existing adapter task interface."""
    return {**response[TASK_BLOCKS[response["task"]]], "notes": response["notes"]}
