"""Tests for /places editor."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_socket
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.places.repository import PlacesRepository

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> tuple[TestClient, Path]:
    pytest_socket.enable_socket()
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app), db_path


def test_places_get_lists_places(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES ('curated:x', 'My Place', 'home', 0, 0, 50,
                   '2026-01-01', '2026-01-01')""",
    )
    conn.close()
    response = c.get("/places")
    assert response.status_code == 200
    assert "My Place" in response.text
    assert "Add place" in response.text


def test_places_post_add_creates_place(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    response = c.post(
        "/places/add",
        data={"name": "Test Cafe", "type": "restaurant",
              "lat": "37.7749", "lng": "-122.4194", "radius": "75"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 303)
    conn = get_connection(db_path)
    places = PlacesRepository(conn).list_all()
    assert len(places) == 1
    assert places[0].name == "Test Cafe"
    assert places[0].radius_m == 75


def test_places_post_delete_removes_place(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES ('curated:del-me', 'Doomed', 'home', 0, 0, 50, '2026-01-01', '2026-01-01')""",
    )
    conn.close()
    response = c.post("/places/delete", data={"id": "curated:del-me"}, follow_redirects=False)
    assert response.status_code in (200, 303)
    conn = get_connection(db_path)
    assert PlacesRepository(conn).get_by_id("curated:del-me") is None
