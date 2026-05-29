"""Tests for the / map view."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_socket
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
    pytest_socket.enable_socket()
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("curated:home", "Home", "home", 37.7749, -122.4194, 50, now_iso, now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_confidence, stage_a_ran_at,
                dish_name, cuisine, stage_b_ran_at,
                venue_type, place_id, place_match_source, venue_resolved_at,
                review_status)
           VALUES (?, ?, ?, ?, 1, 0.95, ?, ?, ?, ?, ?, ?, ?, ?, 'auto')""",
        ("asset-1", now_iso, 37.7749, -122.4194, now_iso,
         "pizza", "Italian", now_iso, "home", "curated:home", "curated", now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at, dish_name, stage_b_ran_at,
                venue_type, place_id, venue_resolved_at, review_status)
           VALUES (?, ?, ?, ?, 1, ?, 'salad', ?, 'unknown', NULL, ?, 'needs_review')""",
        ("asset-2", now_iso, 37.78, -122.40, now_iso, now_iso, now_iso),
    )
    return db_path, conn


def _client(db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_map_page_renders(seeded: tuple[Path, sqlite3.Connection]) -> None:
    db_path, _ = seeded
    response = _client(db_path).get("/")
    assert response.status_code == 200
    assert "map" in response.text.lower()
    assert 'id="map"' in response.text


def test_map_includes_marker_data_for_food_photos_with_gps(
    seeded: tuple[Path, sqlite3.Connection]
) -> None:
    db_path, _ = seeded
    response = _client(db_path).get("/")
    body = response.text
    assert "asset-1" in body
    assert "asset-2" in body
    assert "pizza" in body or "salad" in body


def test_map_excludes_non_food_photos(tmp_path: Path) -> None:
    pytest_socket.enable_socket()
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at, review_status)
           VALUES (?, ?, 37.7, -122.4, 0, ?, 'auto')""",
        ("non-food", now_iso, now_iso),
    )
    conn.close()
    response = _client(db_path).get("/")
    assert "non-food" not in response.text
