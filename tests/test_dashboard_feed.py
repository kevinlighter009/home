"""Tests for /feed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_socket
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    pytest_socket.enable_socket()
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    for i in range(30):
        ts = (base - timedelta(hours=i)).isoformat()
        conn.execute(
            """INSERT INTO photo_analysis (
                    immich_asset_id, first_seen_at, taken_at,
                    stage_a_is_food, stage_a_ran_at,
                    dish_name, cuisine, stage_b_ran_at,
                    venue_type, review_status)
               VALUES (?, ?, ?, 1, ?, ?, 'Italian', ?, 'restaurant', 'auto')""",
            (f"asset-{i:02d}", ts, ts, ts, f"dish {i}", ts),
        )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_feed_default_page_shows_first_24(client: TestClient) -> None:
    response = client.get("/feed")
    assert response.status_code == 200
    assert "dish 0" in response.text
    assert "dish 25" not in response.text


def test_feed_page_2_shows_older_photos(client: TestClient) -> None:
    response = client.get("/feed?page=2")
    assert response.status_code == 200
    assert "dish 25" in response.text
    assert "dish 0" not in response.text


def test_feed_filter_by_venue_type(client: TestClient) -> None:
    response = client.get("/feed?venue_type=home")
    assert response.status_code == 200
    assert "dish 0" not in response.text  # no photos have venue_type=home
