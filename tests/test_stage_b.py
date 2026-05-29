"""Tests for stage B (dish + cuisine classifier)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.stage_b import StageBResult, run_stage_b


@dataclass
class FakeProvider:
    name: str = "fake"
    parsed: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        if self.parsed is None:
            self.parsed = {
                "dish_name": "margherita pizza",
                "cuisine": "Italian",
                "confidence": 0.91,
            }

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        self._calls.append({"image_bytes": image_bytes, "prompt": prompt})
        return ProviderResult(
            parsed=self.parsed,
            raw='{"dish_name": "margherita pizza", "cuisine": "Italian", "confidence": 0.91}',
            latency_ms=350,
            input_tokens=1400,
            output_tokens=80,
            model="fake:big",
        )


def test_run_stage_b_returns_typed_result() -> None:
    out = run_stage_b(FakeProvider(), image_bytes=b"img")
    assert isinstance(out, StageBResult)
    assert out.dish_name == "margherita pizza"
    assert out.cuisine == "Italian"
    assert out.confidence == 0.91


def test_run_stage_b_strips_whitespace_from_strings() -> None:
    p = FakeProvider(parsed={
        "dish_name": "  tonkotsu ramen  ", "cuisine": "  Japanese  ", "confidence": 0.8,
    })
    out = run_stage_b(p, image_bytes=b"img")
    assert out.dish_name == "tonkotsu ramen"
    assert out.cuisine == "Japanese"


def test_run_stage_b_raises_on_missing_fields() -> None:
    p = FakeProvider(parsed={"dish_name": "x", "confidence": 0.5})  # no cuisine
    with pytest.raises(ProviderError):
        run_stage_b(p, image_bytes=b"img")


def test_run_stage_b_raises_on_empty_dish_name() -> None:
    p = FakeProvider(parsed={"dish_name": "", "cuisine": "Italian", "confidence": 0.8})
    with pytest.raises(ProviderError):
        run_stage_b(p, image_bytes=b"img")


def test_run_stage_b_clamps_confidence() -> None:
    p = FakeProvider(parsed={"dish_name": "x", "cuisine": "y", "confidence": 2.0})
    out = run_stage_b(p, image_bytes=b"img")
    assert out.confidence == 1.0
