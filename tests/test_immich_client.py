"""Tests for the Immich REST client.

All HTTP is mocked with respx; the test runner has sockets disabled.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from home_photo_repo.immich_client import ImmichClient, ImmichClientError

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client() -> ImmichClient:
    return ImmichClient(base_url="http://immich.local:2283", api_key="test-key")


@respx.mock
def test_search_metadata_happy_path() -> None:
    route = respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=_load_fixture("immich_search_metadata.json"))
    )
    client = _client()
    assets = client.search_metadata(
        updated_after=datetime(2026, 5, 27, tzinfo=UTC), size=100
    )
    assert route.called
    # The request body should include the cursor and pagination.
    body = json.loads(route.calls.last.request.content)
    assert body["updatedAfter"] == "2026-05-27T00:00:00+00:00"
    assert body["size"] == 100
    assert body["order"] == "asc"
    assert body["withExif"] is True
    # Result shape: a list of assets with parsed GPS where present.
    assert len(assets) == 2
    assert assets[0].id == "asset-uuid-1"
    assert assets[0].latitude == pytest.approx(37.7749)
    assert assets[0].longitude == pytest.approx(-122.4194)
    assert assets[0].owner_id == "user-uuid-a"
    assert assets[1].latitude is None
    assert assets[1].longitude is None


@respx.mock
def test_search_metadata_sends_api_key_header() -> None:
    route = respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json={"assets": {"items": []}})
    )
    _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=UTC))
    assert route.calls.last.request.headers["x-api-key"] == "test-key"


@respx.mock
def test_search_metadata_401_raises() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(401, json={"message": "unauthorized"})
    )
    with pytest.raises(ImmichClientError):
        _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=UTC))


@respx.mock
def test_search_metadata_5xx_raises() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(ImmichClientError):
        _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=UTC))


@respx.mock
def test_search_metadata_handles_empty_items() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json={"assets": {"items": []}})
    )
    assets = _client().search_metadata(
        updated_after=datetime(2026, 5, 27, tzinfo=UTC)
    )
    assert assets == []


@respx.mock
def test_search_metadata_parses_taken_at_as_utc() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=_load_fixture("immich_search_metadata.json"))
    )
    assets = _client().search_metadata(
        updated_after=datetime(2026, 5, 27, tzinfo=UTC)
    )
    # dateTimeOriginal "2026-05-27T11:42:09.000-07:00" → 2026-05-27T18:42:09+00:00
    assert assets[0].taken_at == datetime(2026, 5, 27, 18, 42, 9, tzinfo=UTC)
    # updatedAt "2026-05-27T18:42:15.000Z"
    assert assets[0].updated_at == datetime(2026, 5, 27, 18, 42, 15, tzinfo=UTC)


@respx.mock
def test_search_metadata_raises_on_missing_required_fields() -> None:
    """An asset missing the required 'id' or 'updatedAt' should raise."""
    bad_body = {
        "assets": {
            "items": [
                {
                    "ownerId": "owner-x",
                    "originalFileName": "no_id.jpg",
                    "updatedAt": "2026-05-28T12:00:00Z",
                    "exifInfo": {},
                }
            ]
        }
    }
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=bad_body)
    )
    with pytest.raises(ImmichClientError):
        _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=UTC))


@respx.mock
def test_search_metadata_raises_on_missing_updated_at() -> None:
    bad_body = {
        "assets": {
            "items": [
                {
                    "id": "asset-x",
                    "ownerId": "owner-x",
                    "originalFileName": "no_updated.jpg",
                    "exifInfo": {},
                }
            ]
        }
    }
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=bad_body)
    )
    with pytest.raises(ImmichClientError):
        _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=UTC))


@respx.mock
def test_search_metadata_filters_already_seen_with_last_id() -> None:
    """When last_id is set, items at or before that (timestamp, id) are dropped."""
    fixture = _load_fixture("immich_search_metadata.json")
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    # asset-uuid-1 updated_at: 2026-05-27T18:42:15.000Z
    cursor_ts = datetime(2026, 5, 27, 18, 42, 15, tzinfo=UTC)
    assets = _client().search_metadata(
        updated_after=cursor_ts, last_id="asset-uuid-1", size=100
    )
    # Only asset-uuid-2 should remain.
    assert len(assets) == 1
    assert assets[0].id == "asset-uuid-2"


def test_client_context_manager_closes() -> None:
    """Using the client as a context manager calls close on exit."""
    closed = {"called": False}

    class FakeHttpx:
        def close(self) -> None:
            closed["called"] = True

    c = ImmichClient(base_url="http://x", api_key="k", client=FakeHttpx())  # type: ignore[arg-type]
    with c:
        pass
    assert closed["called"] is True
