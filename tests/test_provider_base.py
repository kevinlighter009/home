"""Tests for the LLM provider base interface."""

from __future__ import annotations

import pytest

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
    VisionLLMProvider,
)


def test_provider_result_is_a_frozen_dataclass() -> None:
    r = ProviderResult(
        parsed={"is_food": True},
        raw='{"is_food": true}',
        latency_ms=120,
        input_tokens=200,
        output_tokens=10,
        model="anthropic:claude-haiku-4-5",
    )
    with pytest.raises((AttributeError, Exception)):
        r.latency_ms = 999  # type: ignore[misc]


def test_provider_error_is_an_exception() -> None:
    assert issubclass(ProviderError, Exception)


def test_vision_llm_provider_is_a_protocol() -> None:
    """A class that has classify() with the right shape duck-types as a provider."""

    class FakeProvider:
        name = "fake"

        def classify(
            self,
            image_bytes: bytes,
            prompt: str,
            response_schema: dict,
            max_tokens: int = 512,
        ) -> ProviderResult:
            return ProviderResult(
                parsed={"ok": True},
                raw="{}",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                model="fake",
            )

    # Static structural check: this assignment would fail at runtime if Protocol
    # were not runtime_checkable; we use isinstance only because @runtime_checkable.
    p: VisionLLMProvider = FakeProvider()
    assert isinstance(p, VisionLLMProvider)
    assert p.name == "fake"
    result = p.classify(b"", "prompt", {})
    assert result.parsed == {"ok": True}
