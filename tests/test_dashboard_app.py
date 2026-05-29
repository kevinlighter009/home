"""Tests for the dashboard FastAPI app — health + nav."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest_socket import enable_socket

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def app_client(tmp_path: Path) -> TestClient:
    # TestClient uses anyio portal which requires socketpair internally;
    # we still don't make real network calls.
    enable_socket()
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="test-key")
    return TestClient(app)


def test_health_endpoint_returns_ok(app_client: TestClient) -> None:
    response = app_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_returns_404(app_client: TestClient) -> None:
    response = app_client.get("/nope")
    assert response.status_code == 404


def test_static_assets_served(app_client: TestClient) -> None:
    """The /static mount should serve the bundled CSS and JS."""
    response = app_client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
