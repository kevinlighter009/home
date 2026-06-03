"""Request-scoped dependencies for dashboard routes.

A fresh sqlite3 connection per request keeps things simple — SQLite is
fast for open/close, and WAL mode (set by `get_connection`) lets the
dashboard read concurrently with the worker writing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from home_photo_repo.db import get_connection


class DashboardDeps:
    """Configuration injected into each route via FastAPI Depends.

    `api_key_by_user_id` maps Immich user_id → API key so the thumbnail proxy
    can authenticate with the correct key for each photo owner.
    Falls back to `immich_api_key` for unknown users.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        immich_base_url: str,
        immich_api_key: str,
        api_key_by_user_id: dict[str, str] | None = None,
    ) -> None:
        self.db_path = db_path
        self.immich_base_url = immich_base_url
        self.immich_api_key = immich_api_key
        self.api_key_by_user_id: dict[str, str] = api_key_by_user_id or {}

    def api_key_for_user(self, user_id: str | None) -> str:
        """Return the API key for the given Immich user, falling back to primary."""
        if user_id and user_id in self.api_key_by_user_id:
            return self.api_key_by_user_id[user_id]
        return self.immich_api_key

    @contextmanager
    def db_conn(self) -> Iterator[sqlite3.Connection]:
        """Yield a sqlite3 connection, closing it on exit (success or exception)."""
        conn = get_connection(self.db_path)
        try:
            yield conn
        finally:
            conn.close()


__all__ = ["DashboardDeps"]
