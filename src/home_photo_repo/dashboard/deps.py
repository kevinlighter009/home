"""Request-scoped dependencies for dashboard routes.

A fresh sqlite3 connection per request keeps things simple — SQLite is
fast for open/close, and WAL mode (set by `get_connection`) lets the
dashboard read concurrently with the worker writing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from home_photo_repo.db import get_connection
from home_photo_repo.immich_client import ImmichClient


class DashboardDeps:
    """Configuration injected into each route via FastAPI Depends.

    Holds immutable config (paths, URLs); creates per-request connections.
    """

    def __init__(self, *, db_path: Path, immich_base_url: str, immich_api_key: str) -> None:
        self.db_path = db_path
        self.immich_base_url = immich_base_url
        self.immich_api_key = immich_api_key

    def get_db(self) -> Iterator[sqlite3.Connection]:
        conn = get_connection(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_immich(self) -> Iterator[ImmichClient]:
        client = ImmichClient(
            base_url=self.immich_base_url, api_key=self.immich_api_key,
        )
        try:
            yield client
        finally:
            client.close()


__all__ = ["DashboardDeps"]
