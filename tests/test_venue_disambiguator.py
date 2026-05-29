"""Tests for the venue disambiguator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.venue_disambiguator import (
    DisambiguatedVenue,
    disambiguate,
)
from home_photo_repo.places.types import NearbyPlace


def _candidates() -> list[NearbyPlace]:
    return [
        NearbyPlace(
            google_place_id="gp-1", name="Mimi's", latitude=37.0, longitude=-122.0,
            address="123 A St", types=("restaurant",),
        ),
        NearbyPlace(
            google_place_id="gp-2", name="Joe's Diner", latitude=37.0001, longitude=-122.0001,
            address="456 B St", types=("restaurant",),
        ),
    ]


@dataclass
class FakeProvider:
    parsed: dict[str, Any]

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict,
        max_tokens: int = 512,
    ) -> ProviderResult:
        return ProviderResult(
            parsed=self.parsed, raw=str(self.parsed),
            latency_ms=10, input_tokens=10, output_tokens=10, model="fake:disambig",
        )


def test_disambiguate_returns_pick_when_confident() -> None:
    out = disambiguate(
        FakeProvider({"google_place_id": "gp-1", "confidence": 0.92}),
        image_bytes=b"img", candidates=_candidates(),
    )
    assert isinstance(out, DisambiguatedVenue)
    assert out.google_place_id == "gp-1"
    assert out.confidence == 0.92


def test_disambiguate_returns_none_pick_when_model_declines() -> None:
    """The model can return google_place_id=null meaning 'none of these'."""
    out = disambiguate(
        FakeProvider({"google_place_id": None, "confidence": 0.7}),
        image_bytes=b"img", candidates=_candidates(),
    )
    assert out.google_place_id is None


def test_disambiguate_clamps_confidence_to_unit_interval() -> None:
    out = disambiguate(
        FakeProvider({"google_place_id": "gp-1", "confidence": 1.5}),
        image_bytes=b"img", candidates=_candidates(),
    )
    assert out.confidence == 1.0


def test_disambiguate_rejects_unknown_place_id() -> None:
    """If the model returns an id not in the candidates list, raise."""
    with pytest.raises(ProviderError):
        disambiguate(
            FakeProvider({"google_place_id": "gp-bogus", "confidence": 0.9}),
            image_bytes=b"img", candidates=_candidates(),
        )


def test_disambiguate_raises_on_missing_fields() -> None:
    with pytest.raises(ProviderError):
        disambiguate(
            FakeProvider({"confidence": 0.9}),  # missing google_place_id
            image_bytes=b"img", candidates=_candidates(),
        )


def test_disambiguate_with_empty_candidates_returns_no_pick() -> None:
    out = disambiguate(
        FakeProvider({"google_place_id": None, "confidence": 0.0}),
        image_bytes=b"img", candidates=[],
    )
    assert out.google_place_id is None
