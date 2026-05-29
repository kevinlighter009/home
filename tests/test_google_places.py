"""Tests for GooglePlacesClient (Places API New)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from home_photo_repo.places.google_places import (
    GooglePlacesClient,
    GooglePlacesError,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client() -> GooglePlacesClient:
    return GooglePlacesClient(api_key="test-key")


@respx.mock
def test_search_nearby_happy_path_returns_typed_places() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json=_load_fixture("google_places_searchnearby.json"))
    )
    results = _client().search_nearby(latitude=37.762, longitude=-122.434, radius_m=150)
    assert len(results) == 2
    p = results[0]
    assert p.google_place_id == "ChIJrTLr-GyuEmsRBfy61i59si0"
    assert p.name == "Mimi's Trattoria"
    assert p.latitude == pytest.approx(37.7619)
    assert p.longitude == pytest.approx(-122.4341)
    assert "restaurant" in p.types


@respx.mock
def test_search_nearby_sends_api_key_and_field_mask_headers() -> None:
    route = respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json={"places": []})
    )
    _client().search_nearby(latitude=0, longitude=0, radius_m=150)
    headers = route.calls.last.request.headers
    assert headers["x-goog-api-key"] == "test-key"
    assert "x-goog-fieldmask" in headers
    fm = headers["x-goog-fieldmask"]
    assert "places.id" in fm
    assert "places.displayName" in fm
    assert "places.location" in fm


@respx.mock
def test_search_nearby_sends_correct_body() -> None:
    route = respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json={"places": []})
    )
    _client().search_nearby(latitude=37.762, longitude=-122.434, radius_m=200)
    body = json.loads(route.calls.last.request.content)
    circle = body["locationRestriction"]["circle"]
    assert circle["center"]["latitude"] == pytest.approx(37.762)
    assert circle["center"]["longitude"] == pytest.approx(-122.434)
    assert circle["radius"] == pytest.approx(200)
    included = set(body["includedTypes"])
    assert "restaurant" in included
    assert "cafe" in included


@respx.mock
def test_search_nearby_no_results_returns_empty_list() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json={})
    )
    assert _client().search_nearby(latitude=0, longitude=0, radius_m=150) == []


@respx.mock
def test_search_nearby_403_raises() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(
            403, json={"error": {"code": 403, "message": "API key invalid"}}
        )
    )
    with pytest.raises(GooglePlacesError):
        _client().search_nearby(latitude=0, longitude=0, radius_m=150)


@respx.mock
def test_search_nearby_malformed_response_raises() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, content=b"not json")
    )
    with pytest.raises(GooglePlacesError):
        _client().search_nearby(latitude=0, longitude=0, radius_m=150)
