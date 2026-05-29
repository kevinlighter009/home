"""Tests for prompt strings and JSON schemas."""

from __future__ import annotations

import json

from home_photo_repo.llm.prompts import (
    STAGE_A_PROMPT,
    STAGE_A_SCHEMA,
    STAGE_A_VERSION,
    STAGE_B_PROMPT,
    STAGE_B_SCHEMA,
    STAGE_B_VERSION,
)


def test_stage_a_prompt_not_empty() -> None:
    assert STAGE_A_PROMPT.strip()
    assert "food" in STAGE_A_PROMPT.lower()


def test_stage_a_schema_is_valid_json_schema_with_required_fields() -> None:
    assert STAGE_A_SCHEMA["type"] == "object"
    props = STAGE_A_SCHEMA["properties"]
    assert "is_food" in props
    assert props["is_food"]["type"] == "boolean"
    assert "confidence" in props
    assert props["confidence"]["type"] == "number"
    assert set(STAGE_A_SCHEMA["required"]) == {"is_food", "confidence"}
    # Round-trips through json without loss
    assert json.loads(json.dumps(STAGE_A_SCHEMA)) == STAGE_A_SCHEMA


def test_stage_b_prompt_not_empty() -> None:
    assert STAGE_B_PROMPT.strip()
    assert "dish" in STAGE_B_PROMPT.lower()


def test_stage_b_schema_has_dish_and_cuisine() -> None:
    props = STAGE_B_SCHEMA["properties"]
    assert "dish_name" in props
    assert "cuisine" in props
    assert "confidence" in props
    assert set(STAGE_B_SCHEMA["required"]) == {"dish_name", "cuisine", "confidence"}


def test_versions_are_strings() -> None:
    assert isinstance(STAGE_A_VERSION, str)
    assert isinstance(STAGE_B_VERSION, str)
