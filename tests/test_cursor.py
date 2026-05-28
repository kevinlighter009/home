"""Tests for cursor persistence in worker_state."""

from __future__ import annotations

from datetime import UTC, datetime
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
    assert read_cursor(conn) == EPOCH_CURSOR


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    write_cursor(conn, ts)
    assert read_cursor(conn) == ts


def test_write_cursor_is_monotonic(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    later = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    earlier = datetime(2025, 1, 1, tzinfo=UTC)
    write_cursor(conn, later)
    write_cursor(conn, earlier)  # must not regress
    assert read_cursor(conn) == later
