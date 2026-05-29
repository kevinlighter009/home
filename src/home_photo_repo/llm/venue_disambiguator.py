"""Venue disambiguator: pick among ambiguous Google Places candidates by LLM.

Used when the matcher's Google Nearby Search returns multiple candidates
within the ambiguity threshold of each other. We hand the image and the
candidate list to a vision LLM; it picks one (or declines with None).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from home_photo_repo.llm.providers.base import (
    ProviderError,
    VisionLLMProvider,
)
from home_photo_repo.places.types import NearbyPlace

DISAMBIGUATE_PROMPT_VERSION: str = "disambiguator/v1"

_BASE_PROMPT = (
    "You are looking at a photograph taken near several possible venues. "
    "Based on visible context — signage, decor, plating style, menu items, "
    "wall art, language on labels — pick which of the candidates is most "
    "likely where this photo was taken. If you can't tell, return "
    "google_place_id=null.\n\n"
    "Candidates:\n"
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "google_place_id": {
            "type": ["string", "null"],
            "description": "The id of the picked candidate, or null if uncertain.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
    "required": ["google_place_id", "confidence"],
}


@dataclass(frozen=True)
class DisambiguatedVenue:
    google_place_id: str | None  # None = "none of these"
    confidence: float            # clamped to [0.0, 1.0]
    model: str
    raw_json: str


def _format_candidate(idx: int, p: NearbyPlace) -> str:
    type_str = ", ".join(p.types[:3]) if p.types else "(no types)"
    addr = f"\n   {p.address}" if p.address else ""
    return (
        f"{idx + 1}. id={p.google_place_id}  name={p.name}  types={type_str}"
        f"{addr}"
    )


def _build_prompt(candidates: list[NearbyPlace]) -> str:
    body = _BASE_PROMPT
    for i, c in enumerate(candidates):
        body += _format_candidate(i, c) + "\n"
    body += (
        "\nReturn the picked candidate's google_place_id (or null), and a "
        "confidence between 0.0 and 1.0."
    )
    return body


def disambiguate(
    provider: VisionLLMProvider,
    *,
    image_bytes: bytes,
    candidates: list[NearbyPlace],
) -> DisambiguatedVenue:
    result = provider.classify(
        image_bytes=image_bytes,
        prompt=_build_prompt(candidates),
        response_schema=_RESPONSE_SCHEMA,
        max_tokens=200,
    )
    parsed = result.parsed
    if "google_place_id" not in parsed or "confidence" not in parsed:
        raise ProviderError(
            f"disambiguator response missing required fields: {parsed!r}"
        )
    picked = parsed["google_place_id"]
    if picked is not None and not isinstance(picked, str):
        raise ProviderError(
            f"disambiguator google_place_id must be string or null: {picked!r}"
        )
    if picked is not None:
        valid_ids = {c.google_place_id for c in candidates}
        if picked not in valid_ids:
            raise ProviderError(
                f"disambiguator returned unknown google_place_id {picked!r}; "
                f"candidates were {sorted(valid_ids)}"
            )
    try:
        conf = float(parsed["confidence"])
    except (TypeError, ValueError) as e:
        raise ProviderError(
            f"disambiguator confidence not numeric: {parsed['confidence']!r}"
        ) from e
    conf = max(0.0, min(1.0, conf))
    return DisambiguatedVenue(
        google_place_id=picked,
        confidence=conf,
        model=result.model,
        raw_json=result.raw,
    )


__all__ = [
    "DISAMBIGUATE_PROMPT_VERSION",
    "DisambiguatedVenue",
    "disambiguate",
]
