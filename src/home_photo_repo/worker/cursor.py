"""Persistent ingestion cursor stored in worker_state.

The cursor is a (timestamp, last_asset_id) pair: among assets with the same
`updated_at`, we need a secondary key to know which we've already seen.
Otherwise a bulk import with N identically-stamped assets would re-loop
forever.

Stored serialized as JSON in a single worker_state row keyed `immich_cursor`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

CURSOR_KEY = "immich_cursor"
EPOCH_CURSOR: datetime = datetime(1970, 1, 1, tzinfo=UTC)


def read_cursor(conn: sqlite3.Connection) -> tuple[datetime, str]:
    """Return (timestamp, last_asset_id). Both empty defaults if no cursor yet."""
    row = conn.execute(
        "SELECT value FROM worker_state WHERE key = ?", (CURSOR_KEY,)
    ).fetchone()
    if row is None:
        return (EPOCH_CURSOR, "")
    data = json.loads(row["value"])
    return (datetime.fromisoformat(data["updated_at"]), data["last_id"])


def write_cursor(conn: sqlite3.Connection, ts: datetime, *, last_id: str) -> None:
    """Write the cursor if it strictly advances; otherwise no-op.

    Advances if: ts > current_ts, OR ts == current_ts AND last_id > current_last_id.
    """
    current_ts, current_id = read_cursor(conn)
    if (ts, last_id) <= (current_ts, current_id):
        return
    payload = json.dumps({"updated_at": ts.isoformat(), "last_id": last_id})
    conn.execute(
        """
        INSERT INTO worker_state (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (CURSOR_KEY, payload),
    )


__all__ = ["CURSOR_KEY", "EPOCH_CURSOR", "read_cursor", "write_cursor"]
