"""Tests for stage A (is-this-food classifier)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.stage_a import StageAResult, run_stage_a


@dataclass
class FakeProvider:
    """Returns a pre-canned ProviderResult; records each call."""

    name: str = "fake"
    parsed: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        if self.parsed is None:
            self.parsed = {"is_food": True, "confidence": 0.85}

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        self._calls.append(
            {"image_bytes": image_bytes, "prompt": prompt, "response_schema": response_schema}
        )
        return ProviderResult(
            parsed=self.parsed,
            raw='{"is_food": true, "confidence": 0.85}',
            latency_ms=100,
            input_tokens=200,
            output_tokens=10,
            model="fake:tiny",
        )


def test_run_stage_a_returns_typed_result() -> None:
    p = FakeProvider()
    out = run_stage_a(p, image_bytes=b"img")
    assert isinstance(out, StageAResult)
    assert out.is_food is True
    assert out.confidence == 0.85
    assert out.model == "fake:tiny"
    assert out.raw_json == '{"is_food": true, "confidence": 0.85}'


def test_run_stage_a_sends_correct_prompt_and_schema() -> None:
    p = FakeProvider()
    run_stage_a(p, image_bytes=b"img")
    call = p._calls[0]
    assert call["image_bytes"] == b"img"
    assert "food" in call["prompt"].lower()
    assert call["response_schema"]["required"] == ["is_food", "confidence"]


def test_run_stage_a_raises_on_missing_fields() -> None:
    p = FakeProvider(parsed={"is_food": True})  # missing confidence
    with pytest.raises(ProviderError):
        run_stage_a(p, image_bytes=b"img")


def test_run_stage_a_raises_on_wrong_type() -> None:
    p = FakeProvider(parsed={"is_food": "yes", "confidence": 0.9})  # is_food not bool
    with pytest.raises(ProviderError):
        run_stage_a(p, image_bytes=b"img")


def test_run_stage_a_clamps_confidence_to_unit_interval() -> None:
    p = FakeProvider(parsed={"is_food": True, "confidence": 1.5})
    out = run_stage_a(p, image_bytes=b"img")
    assert out.confidence == 1.0
    p2 = FakeProvider(parsed={"is_food": False, "confidence": -0.1})
    out2 = run_stage_a(p2, image_bytes=b"img")
    assert out2.confidence == 0.0
