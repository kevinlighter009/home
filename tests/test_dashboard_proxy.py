"""Tests for /proxy/thumbnail/{asset_id}."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pytest_socket import enable_socket

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    enable_socket()
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="test-key")
    return TestClient(app)


@respx.mock
def test_proxy_streams_thumbnail_bytes(client: TestClient) -> None:
    fake_jpeg = b"\xff\xd8\xff fake jpeg bytes"
    respx.get(
        "http://immich.local:2283/api/assets/asset-1/thumbnail"
    ).mock(return_value=httpx.Response(
        200, content=fake_jpeg, headers={"content-type": "image/jpeg"},
    ))
    response = client.get("/proxy/thumbnail/asset-1")
    assert response.status_code == 200
    assert response.content == fake_jpeg
    assert response.headers.get("cache-control") is not None
    assert "max-age" in response.headers["cache-control"]


@respx.mock
def test_proxy_supports_preview_size(client: TestClient) -> None:
    route = respx.get(
        "http://immich.local:2283/api/assets/asset-1/thumbnail"
    ).mock(return_value=httpx.Response(200, content=b"x"))
    client.get("/proxy/thumbnail/asset-1?size=preview")
    assert route.calls.last.request.url.params["size"] == "preview"


@respx.mock
def test_proxy_404_passes_through(client: TestClient) -> None:
    respx.get(
        "http://immich.local:2283/api/assets/asset-missing/thumbnail"
    ).mock(return_value=httpx.Response(404))
    response = client.get("/proxy/thumbnail/asset-missing")
    assert response.status_code == 404
