"""Tests for /place/{id}."""

from __future__ import annotations

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
def client(tmp_path: Path) -> TestClient:
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
    for i, dish in enumerate(["pizza", "ramen", "salad"]):
        conn.execute(
            """INSERT INTO photo_analysis (
                    immich_asset_id, first_seen_at, latitude, longitude,
                    stage_a_is_food, stage_a_ran_at, dish_name, cuisine,
                    stage_b_ran_at, venue_type, place_id, place_match_source,
                    venue_resolved_at, review_status, taken_at)
               VALUES (?, ?, 37.7749, -122.4194, 1, ?, ?, 'Italian', ?,
                       'home', 'curated:home', 'curated', ?, 'auto', ?)""",
            (f"asset-{i}", now_iso, now_iso, dish, now_iso, now_iso, now_iso),
        )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_place_detail_lists_dishes(client: TestClient) -> None:
    response = client.get("/place/curated:home")
    assert response.status_code == 200
    assert "Home" in response.text
    for dish in ("pizza", "ramen", "salad"):
        assert dish in response.text


def test_place_detail_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/place/curated:does-not-exist")
    assert response.status_code == 404
