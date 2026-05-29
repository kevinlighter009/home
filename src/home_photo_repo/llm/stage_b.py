"""Stage B: dish + cuisine classifier.

Pure function. Plan 2 returns dish_name + cuisine + confidence. Plan 3 will
extend Stage B (or layer a second LLM call) with venue resolution context.
"""

from __future__ import annotations

from dataclasses import dataclass

from home_photo_repo.llm.prompts import STAGE_B_PROMPT, STAGE_B_SCHEMA
from home_photo_repo.llm.providers.base import (
    ProviderError,
    VisionLLMProvider,
)


@dataclass(frozen=True)
class StageBResult:
    dish_name: str
    cuisine: str
    confidence: float
    model: str
    raw_json: str
    latency_ms: int


def run_stage_b(provider: VisionLLMProvider, *, image_bytes: bytes) -> StageBResult:
    result = provider.classify(
        image_bytes=image_bytes,
        prompt=STAGE_B_PROMPT,
        response_schema=STAGE_B_SCHEMA,
        max_tokens=300,
    )
    parsed = result.parsed
    for field in ("dish_name", "cuisine", "confidence"):
        if field not in parsed:
            raise ProviderError(f"stage_b response missing required field {field!r}: {parsed!r}")
    dish = str(parsed["dish_name"]).strip()
    cuisine = str(parsed["cuisine"]).strip()
    if not dish:
        raise ProviderError("stage_b dish_name is empty")
    if not cuisine:
        raise ProviderError("stage_b cuisine is empty")
    try:
        conf = float(parsed["confidence"])
    except (TypeError, ValueError) as e:
        raise ProviderError(
            f"stage_b confidence not numeric: {parsed['confidence']!r}"
        ) from e
    conf = max(0.0, min(1.0, conf))
    return StageBResult(
        dish_name=dish,
        cuisine=cuisine,
        confidence=conf,
        model=result.model,
        raw_json=result.raw,
        latency_ms=result.latency_ms,
    )


__all__ = ["StageBResult", "run_stage_b"]
