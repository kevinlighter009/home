"""Tests for cursor persistence in worker_state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.worker.cursor import EPOCH_CURSOR, read_cursor, write_cursor

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path):
    c = get_connection(tmp_path / "app.sqlite")
    apply_migrations(c, MIGRATIONS)
    return c


def test_read_cursor_defaults_to_epoch(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assert read_cursor(conn) == (EPOCH_CURSOR, "")


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    write_cursor(conn, ts, last_id="some-id")
    assert read_cursor(conn) == (ts, "some-id")


def test_write_cursor_is_monotonic(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    later = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    earlier = datetime(2025, 1, 1, tzinfo=UTC)
    write_cursor(conn, later, last_id="a")
    write_cursor(conn, earlier, last_id="z")  # must not regress
    assert read_cursor(conn) == (later, "a")


def test_cursor_composite_round_trip(tmp_path: Path) -> None:
    """Cursor stores a (timestamp, last_asset_id) tuple."""
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    write_cursor(conn, ts, last_id="asset-uuid-zzz")
    assert read_cursor(conn) == (ts, "asset-uuid-zzz")


def test_cursor_default_returns_epoch_and_empty_id(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assert read_cursor(conn) == (EPOCH_CURSOR, "")


def test_cursor_monotonic_by_timestamp_then_id(tmp_path: Path) -> None:
    """If timestamps are equal, the larger id wins. If timestamp is earlier, no-op."""
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    write_cursor(conn, ts, last_id="asset-005")
    write_cursor(conn, ts, last_id="asset-003")  # smaller id, no-op
    assert read_cursor(conn) == (ts, "asset-005")
    write_cursor(conn, ts, last_id="asset-009")  # larger id, advances
    assert read_cursor(conn) == (ts, "asset-009")
    earlier = ts - timedelta(seconds=1)
    write_cursor(conn, earlier, last_id="asset-zzz")  # earlier timestamp, no-op
    assert read_cursor(conn) == (ts, "asset-009")
