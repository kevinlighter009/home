"""Tests for PlaceMatcher orchestration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace, NearbyPlace

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


class FakeGoogleClient:
    """Returns canned NearbyPlace lists; records each call."""

    def __init__(self, results: list[NearbyPlace]) -> None:
        self.results = results
        self.calls: list[tuple[float, float, float]] = []

    def search_nearby(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> list[NearbyPlace]:
        self.calls.append((latitude, longitude, radius_m))
        return self.results


def _matcher(
    conn: sqlite3.Connection, google: FakeGoogleClient | None = None,
    ambiguous_threshold_m: int = 50, search_radius_m: int = 150,
) -> PlaceMatcher:
    return PlaceMatcher(
        repo=PlacesRepository(conn),
        google=google,
        ambiguous_threshold_m=ambiguous_threshold_m,
        search_radius_m=search_radius_m,
    )


def _seed_curated(conn: sqlite3.Connection, **fields: object) -> CuratedPlace:
    defaults: dict[str, object] = dict(
        id="curated:default",
        name="Default",
        type="home",
        latitude=37.7749,
        longitude=-122.4194,
        radius_m=50,
        google_place_id=None,
        address=None,
        notes=None,
    )
    defaults.update(fields)
    place = CuratedPlace(**defaults)  # type: ignore[arg-type]
    PlacesRepository(conn).insert(place)
    return place


def test_match_returns_curated_place_when_within_radius(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    home = _seed_curated(conn, id="curated:home", name="Home", type="home")
    google = FakeGoogleClient(results=[])
    m = _matcher(conn, google=google)

    result = m.match(latitude=37.7749, longitude=-122.4194)

    assert result.place_id == home.id
    assert result.venue_type == "home"
    assert result.source == "curated"
    assert result.needs_review is False
    assert google.calls == []


def test_match_falls_back_to_google_when_no_curated(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    nearby = NearbyPlace(
        google_place_id="gp-1",
        name="Test Restaurant",
        latitude=37.762,
        longitude=-122.434,
        address="123 Test St",
        types=("restaurant",),
    )
    google = FakeGoogleClient(results=[nearby])
    m = _matcher(conn, google=google, search_radius_m=200)

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.place_id == "gplaces:gp-1"
    assert result.venue_type == "restaurant"
    assert result.source == "google_places"
    assert result.needs_review is False
    assert len(google.calls) == 1
    cached = PlacesRepository(conn).get_by_id("gplaces:gp-1")
    assert cached is not None
    assert cached.name == "Test Restaurant"
    assert cached.google_place_id == "gp-1"


def test_match_cached_google_place_resolves_locally_next_time(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    nearby = NearbyPlace(
        google_place_id="gp-1",
        name="Test Restaurant",
        latitude=37.762,
        longitude=-122.434,
        address=None,
        types=("restaurant",),
    )
    google = FakeGoogleClient(results=[nearby])
    m = _matcher(conn, google=google)

    m.match(latitude=37.762, longitude=-122.434)
    google.calls.clear()
    google.results = []
    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.source == "curated"
    assert result.place_id == "gplaces:gp-1"
    assert google.calls == []


def test_match_flags_ambiguous_when_multiple_curated_within_threshold(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_curated(
        conn, id="curated:a", name="A",
        latitude=37.7749, longitude=-122.4194, radius_m=200,
    )
    _seed_curated(
        conn, id="curated:b", name="B",
        latitude=37.77492, longitude=-122.41944, radius_m=200,
    )
    google = FakeGoogleClient(results=[])
    m = _matcher(conn, google=google, ambiguous_threshold_m=50)

    result = m.match(latitude=37.7749, longitude=-122.4194)

    assert result.needs_review is True
    assert "ambiguous" in (result.notes or "").lower()
    assert result.place_id in ("curated:a", "curated:b")


def test_match_returns_unknown_when_no_curated_and_google_empty(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    google = FakeGoogleClient(results=[])
    m = _matcher(conn, google=google)

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.place_id is None
    assert result.venue_type == "unknown"
    assert result.source == "unknown"
    assert result.needs_review is True


def test_match_returns_unknown_when_google_disabled(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    m = _matcher(conn, google=None)

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.place_id is None
    assert result.venue_type == "unknown"
    assert result.source == "unknown"
    assert result.needs_review is True


def test_match_handles_google_error_gracefully(tmp_path: Path) -> None:
    from home_photo_repo.places.google_places import GooglePlacesError

    conn = _conn(tmp_path)

    class BrokenGoogle:
        def search_nearby(self, *, latitude, longitude, radius_m):
            raise GooglePlacesError("simulated outage")

    m = PlaceMatcher(
        repo=PlacesRepository(conn), google=BrokenGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    result = m.match(latitude=37.762, longitude=-122.434)
    assert result.venue_type == "unknown"
    assert result.needs_review is True
    assert "google" in (result.notes or "").lower()
