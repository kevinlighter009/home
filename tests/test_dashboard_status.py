"""Tests for /status."""

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
    for i in range(3):
        conn.execute(
            """INSERT INTO worker_runs (started_at, finished_at, assets_seen,
                                       assets_processed, errors)
               VALUES (?, ?, ?, ?, ?)""",
            (now_iso, now_iso, 10 + i, 9 + i, i),
        )
    for aid, status in (("a1", "auto"), ("a2", "needs_review")):
        conn.execute(
            """INSERT INTO photo_analysis (immich_asset_id, first_seen_at,
                                          stage_a_is_food, stage_a_ran_at,
                                          review_status)
               VALUES (?, ?, 1, ?, ?)""",
            (aid, now_iso, now_iso, status),
        )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_status_page_renders_counts(client: TestClient) -> None:
    response = client.get("/status")
    assert response.status_code == 200
    body = response.text
    assert "Pipeline summary" in body or "summary" in body.lower()
    # 2 total assets, 1 needs_review
    assert "2" in body
    assert "1" in body
