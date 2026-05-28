"""Persistent ingestion cursor stored in worker_state."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

CURSOR_KEY = "immich_cursor"
EPOCH_CURSOR: datetime = datetime(1970, 1, 1, tzinfo=UTC)


def read_cursor(conn: sqlite3.Connection) -> datetime:
    row = conn.execute(
        "SELECT value FROM worker_state WHERE key = ?", (CURSOR_KEY,)
    ).fetchone()
    if row is None:
        return EPOCH_CURSOR
    return datetime.fromisoformat(row["value"])


def write_cursor(conn: sqlite3.Connection, ts: datetime) -> None:
    """Write `ts` if it is strictly greater than the current cursor; otherwise no-op."""
    current = read_cursor(conn)
    if ts <= current:
        return
    conn.execute(
        """
        INSERT INTO worker_state (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (CURSOR_KEY, ts.isoformat()),
    )


__all__ = ["CURSOR_KEY", "EPOCH_CURSOR", "read_cursor", "write_cursor"]
