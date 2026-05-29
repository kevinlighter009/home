"""Vision LLM provider interface.

Both Stage A (Haiku/local-small) and Stage B (Sonnet/local-large) call the
same `classify` method. Providers handle their own SDK / HTTP transport,
prompt encoding, and JSON-schema enforcement; this layer is a thin contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class ProviderError(Exception):
    """Raised when an LLM provider call fails or returns an un-parseable response."""


@dataclass(frozen=True)
class ProviderResult:
    parsed: dict[str, Any]
    raw: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    model: str  # "<provider>:<model>" e.g. "anthropic:claude-haiku-4-5"


@runtime_checkable
class VisionLLMProvider(Protocol):
    """A vision-capable LLM that returns structured JSON output."""

    name: str  # "anthropic" | "mlx"

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult: ...


__all__ = ["ProviderError", "ProviderResult", "VisionLLMProvider"]
