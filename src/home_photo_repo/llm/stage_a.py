"""Stage A: is-this-food classifier.

Pure function — takes a provider and bytes, returns a typed result. Pipeline
integration (DB writes, error handling) lives in the worker pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from home_photo_repo.llm.prompts import STAGE_A_PROMPT, STAGE_A_SCHEMA
from home_photo_repo.llm.providers.base import (
    ProviderError,
    VisionLLMProvider,
)


@dataclass(frozen=True)
class StageAResult:
    is_food: bool
    confidence: float  # clamped to [0.0, 1.0]
    model: str
    raw_json: str
    latency_ms: int


def run_stage_a(provider: VisionLLMProvider, *, image_bytes: bytes) -> StageAResult:
    result = provider.classify(
        image_bytes=image_bytes,
        prompt=STAGE_A_PROMPT,
        response_schema=STAGE_A_SCHEMA,
        max_tokens=128,
    )
    parsed = result.parsed
    if "is_food" not in parsed or "confidence" not in parsed:
        raise ProviderError(f"stage_a response missing required fields: {parsed!r}")
    if not isinstance(parsed["is_food"], bool):
        raise ProviderError(f"stage_a is_food is not bool: {parsed['is_food']!r}")
    try:
        conf = float(parsed["confidence"])
    except (TypeError, ValueError) as e:
        raise ProviderError(
            f"stage_a confidence not numeric: {parsed['confidence']!r}"
        ) from e
    conf = max(0.0, min(1.0, conf))
    return StageAResult(
        is_food=parsed["is_food"],
        confidence=conf,
        model=result.model,
        raw_json=result.raw,
        latency_ms=result.latency_ms,
    )


__all__ = ["StageAResult", "run_stage_a"]
