"""Persistent ingestion cursors stored in worker_state.

Timestamp cursor
----------------
A (timestamp, last_asset_id) pair used for incremental polling.
Among assets with the same `updated_at` we need a secondary key to avoid
re-processing.  Stored as JSON under key `immich_cursor[:<user_id>]`.

Backfill page cursor
--------------------
Tracks page-based full-library sweep progress under key
`backfill_page[:<user_id>]`.  Value is the *next* page to fetch (1-based).
None means the sweep is complete; absent key means not yet started (→ page 1).

Both cursors are namespaced by user_id so the worker can process multiple
Immich accounts independently without their cursors colliding.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

CURSOR_KEY = "immich_cursor"
BACKFILL_KEY = "backfill_page"
EPOCH_CURSOR: datetime = datetime(1970, 1, 1, tzinfo=UTC)


def _cursor_key(user_id: str) -> str:
    return f"{CURSOR_KEY}:{user_id}" if user_id else CURSOR_KEY


def _backfill_key(user_id: str) -> str:
    return f"{BACKFILL_KEY}:{user_id}" if user_id else BACKFILL_KEY


def read_cursor(conn: sqlite3.Connection, *, user_id: str = "") -> tuple[datetime, str]:
    """Return (timestamp, last_asset_id). Defaults to epoch / empty if no cursor yet."""
    row = conn.execute(
        "SELECT value FROM worker_state WHERE key = ?", (_cursor_key(user_id),)
    ).fetchone()
    if row is None:
        return (EPOCH_CURSOR, "")
    data = json.loads(row["value"])
    return (datetime.fromisoformat(data["updated_at"]), data["last_id"])


def write_cursor(
    conn: sqlite3.Connection, ts: datetime, *, last_id: str, user_id: str = ""
) -> None:
    """Write the cursor if it strictly advances; otherwise no-op."""
    current_ts, current_id = read_cursor(conn, user_id=user_id)
    if (ts, last_id) <= (current_ts, current_id):
        return
    payload = json.dumps({"updated_at": ts.isoformat(), "last_id": last_id})
    conn.execute(
        """
        INSERT INTO worker_state (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (_cursor_key(user_id), payload),
    )


def read_backfill_page(conn: sqlite3.Connection, *, user_id: str = "") -> int | None:
    """Return the next backfill page to fetch, or None if backfill is complete.

    - Key absent  → backfill not yet started; caller should begin at page 1.
    - Key present, value 1+ → next page to fetch.
    - Key present, value None → backfill complete.
    """
    row = conn.execute(
        "SELECT value FROM worker_state WHERE key = ?", (_backfill_key(user_id),)
    ).fetchone()
    if row is None:
        return 1  # not started — begin at page 1
    data = json.loads(row["value"])
    return data.get("page")  # None means complete


def write_backfill_page(
    conn: sqlite3.Connection, page: int | None, *, user_id: str = ""
) -> None:
    """Persist the backfill page cursor. page=None marks backfill as complete."""
    payload = json.dumps({"page": page})
    conn.execute(
        """
        INSERT INTO worker_state (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (_backfill_key(user_id), payload),
    )


__all__ = [
    "BACKFILL_KEY",
    "CURSOR_KEY",
    "EPOCH_CURSOR",
    "read_backfill_page",
    "read_cursor",
    "write_backfill_page",
    "write_cursor",
]
