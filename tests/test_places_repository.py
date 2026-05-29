"""Tests for PlacesRepository: insert, list, nearby search by radius."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _home() -> CuratedPlace:
    return CuratedPlace(
        id="curated:home-1",
        name="Home",
        type="home",
        latitude=37.7749,
        longitude=-122.4194,
        radius_m=50,
        google_place_id=None,
        address=None,
        notes=None,
    )


def test_insert_and_get_by_id(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    p = _home()
    repo.insert(p)
    found = repo.get_by_id(p.id)
    assert found is not None
    assert found.name == "Home"
    assert found.type == "home"
    assert found.latitude == pytest.approx(37.7749)


def test_get_by_id_returns_none_for_unknown(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    assert repo.get_by_id("curated:nope") is None


def test_list_all_returns_all_places_ordered(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(_home())
    repo.insert(
        CuratedPlace(
            id="curated:office-1",
            name="Office",
            type="office",
            latitude=37.78,
            longitude=-122.40,
            radius_m=75,
            google_place_id=None,
            address=None,
            notes=None,
        )
    )
    all_places = repo.list_all()
    names = sorted(p.name for p in all_places)
    assert names == ["Home", "Office"]


def test_delete_by_id_removes_place(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(_home())
    assert repo.delete_by_id(_home().id) is True
    assert repo.get_by_id(_home().id) is None
    assert repo.delete_by_id(_home().id) is False


def test_nearby_returns_places_within_radius_with_distances(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(_home())
    repo.insert(
        CuratedPlace(
            id="curated:office-far",
            name="Office",
            type="office",
            latitude=37.7858,
            longitude=-122.4194,
            radius_m=75,
            google_place_id=None,
            address=None,
            notes=None,
        )
    )
    matches = repo.nearby(37.7749, -122.4194)
    assert len(matches) == 1
    assert matches[0][0].id == "curated:home-1"
    assert matches[0][1] == pytest.approx(0.0, abs=1.0)


def test_nearby_returns_multiple_when_inside_overlapping_radii(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(
        CuratedPlace(
            id="curated:a", name="A", type="restaurant",
            latitude=37.7749, longitude=-122.4194,
            radius_m=200,
            google_place_id=None, address=None, notes=None,
        )
    )
    repo.insert(
        CuratedPlace(
            id="curated:b", name="B", type="restaurant",
            latitude=37.7752, longitude=-122.4194,
            radius_m=200,
            google_place_id=None, address=None, notes=None,
        )
    )
    matches = repo.nearby(37.7750, -122.4194)
    assert len(matches) == 2
    assert matches[0][1] <= matches[1][1]


def test_nearby_excludes_places_outside_their_radius(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(
        CuratedPlace(
            id="curated:tight", name="Tight", type="home",
            latitude=37.7749, longitude=-122.4194,
            radius_m=10,
            google_place_id=None, address=None, notes=None,
        )
    )
    matches = repo.nearby(37.7758, -122.4194)
    assert matches == []
