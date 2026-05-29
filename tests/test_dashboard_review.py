"""Tests for /review."""

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
def client(tmp_path: Path) -> tuple[TestClient, Path]:
    pytest_socket.enable_socket()
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES ('curated:home', 'Home', 'home', 37.7749, -122.4194, 50, ?, ?)""",
        (now_iso, now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at,
                dish_name, cuisine, stage_b_ran_at, stage_b_confidence,
                review_status)
           VALUES ('asset-needs', ?, 37.78, -122.40, 1, ?, 'mystery dish',
                   'Unknown', ?, 0.3, 'needs_review')""",
        (now_iso, now_iso, now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at,
                dish_name, cuisine, stage_b_ran_at, stage_b_confidence,
                review_status)
           VALUES ('asset-ok', ?, 37.78, -122.40, 1, ?, 'pizza',
                   'Italian', ?, 0.95, 'auto')""",
        (now_iso, now_iso, now_iso),
    )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app), db_path


def test_review_lists_only_needs_review_rows(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    response = c.get("/review")
    assert response.status_code == 200
    assert "asset-needs" in response.text
    assert "mystery dish" in response.text
    assert "asset-ok" not in response.text


def test_review_post_updates_dish_and_marks_confirmed(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    response = c.post(
        "/review/asset-needs",
        data={"dish_name": "corrected dish", "cuisine": "Italian",
              "place_id": "curated:home", "decision": "confirm"},
    )
    assert response.status_code == 200
    assert "<html" not in response.text.lower()  # HTMX partial — no full page
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT dish_name, cuisine, place_id, review_status, reviewed_at "
        "FROM photo_analysis WHERE immich_asset_id = ?", ("asset-needs",),
    ).fetchone()
    assert row["dish_name"] == "corrected dish"
    assert row["cuisine"] == "Italian"
    assert row["place_id"] == "curated:home"
    assert row["review_status"] == "confirmed"
    assert row["reviewed_at"] is not None


def test_review_post_with_decision_corrected_marks_status(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    c.post(
        "/review/asset-needs",
        data={"dish_name": "x", "cuisine": "y", "place_id": "",
              "decision": "correct"},
    )
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT review_status FROM photo_analysis WHERE immich_asset_id = ?",
        ("asset-needs",),
    ).fetchone()
    assert row["review_status"] == "corrected"


def test_review_post_rejects_invalid_decision(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    response = c.post(
        "/review/asset-needs",
        data={"dish_name": "x", "cuisine": "y", "place_id": "", "decision": "frobnicate"},
    )
    assert response.status_code == 400


def test_review_post_unknown_asset_returns_404(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    response = c.post(
        "/review/asset-missing",
        data={"dish_name": "x", "cuisine": "y", "place_id": "", "decision": "confirm"},
    )
    assert response.status_code == 404
