"""Tests for FallbackProvider — composes a primary + fallback VisionLLMProvider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
)
from home_photo_repo.llm.providers.fallback_provider import FallbackProvider


@dataclass
class FakeProvider:
    """Returns a canned ProviderResult, or raises a canned exception."""

    name: str
    canned_result: ProviderResult | None = None
    canned_exception: BaseException | None = None

    def __post_init__(self) -> None:
        self.calls: int = 0

    def classify(
        self, image_bytes: bytes, prompt: str, response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        self.calls += 1
        if self.canned_exception is not None:
            raise self.canned_exception
        assert self.canned_result is not None
        return self.canned_result


def _ok_result(model: str) -> ProviderResult:
    return ProviderResult(
        parsed={"is_food": True, "confidence": 0.9},
        raw='{"is_food": true, "confidence": 0.9}',
        latency_ms=10, input_tokens=1, output_tokens=1, model=model,
    )


def test_fallback_returns_primary_when_primary_succeeds() -> None:
    primary = FakeProvider("primary", canned_result=_ok_result("mlx:m"))
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "mlx:m"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_fallback_used_when_primary_raises_connect_error() -> None:
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx HTTP error: ConnectError()"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "anthropic:c"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_fallback_used_when_primary_raises_5xx_provider_error() -> None:
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx server returned 503: Service Unavailable"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "anthropic:c"
    assert fallback.calls == 1


def test_fallback_used_when_primary_raises_timeout() -> None:
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx HTTP error: TimeoutException()"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "anthropic:c"
    assert fallback.calls == 1


def test_auth_errors_propagate_no_fallback() -> None:
    """401/403 are config errors — failing over wouldn't help. Propagate."""
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx server returned 401: Unauthorized"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    with pytest.raises(ProviderError):
        p.classify(b"img", "prompt", {})
    assert fallback.calls == 0


def test_malformed_response_propagates_no_fallback() -> None:
    """Bad JSON shape is the model's fault — fallback wouldn't help."""
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx model did not emit valid JSON: ..."),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    with pytest.raises(ProviderError):
        p.classify(b"img", "prompt", {})
    assert fallback.calls == 0


def test_name_reflects_chain() -> None:
    primary = FakeProvider("mlx", canned_result=_ok_result("x"))
    fallback = FakeProvider("anthropic", canned_result=_ok_result("y"))
    p = FallbackProvider(primary=primary, fallback=fallback)
    assert p.name == "mlx→anthropic"


def test_fallback_propagates_when_fallback_also_fails() -> None:
    """If fallback ALSO fails, the fallback's exception is raised
    (with the primary's context attached)."""
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx connection refused"),
    )
    fallback = FakeProvider(
        "fallback",
        canned_exception=ProviderError("anthropic 503"),
    )
    p = FallbackProvider(primary=primary, fallback=fallback)
    with pytest.raises(ProviderError) as exc_info:
        p.classify(b"img", "prompt", {})
    # Fallback's error should be in the message
    assert "anthropic" in str(exc_info.value)
