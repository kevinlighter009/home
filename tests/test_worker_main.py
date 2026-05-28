"""Tests for the worker main loop's run_once() function.

We test the loop with a fake ImmichClient so no HTTP is involved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.worker.cursor import EPOCH_CURSOR, read_cursor
from home_photo_repo.worker.main import RunSummary, run_once

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


class FakeImmich:
    def __init__(self, batches: list[list[ImmichAsset]]):
        self._batches = list(batches)
        self.calls: list[dict[str, Any]] = []

    def search_metadata(self, *, updated_after, size=100, order="asc"):
        self.calls.append({"updated_after": updated_after, "size": size, "order": order})
        if not self._batches:
            return []
        return self._batches.pop(0)


def _conn(tmp_path: Path):
    c = get_connection(tmp_path / "app.sqlite")
    apply_migrations(c, MIGRATIONS)
    return c


def _asset(aid: str, updated_offset_sec: int) -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id=aid,
        owner_id="owner-x",
        original_file_name=f"{aid}.HEIC",
        updated_at=base + timedelta(seconds=updated_offset_sec),
        taken_at=base,
        latitude=37.0,
        longitude=-122.0,
        file_created_at=base,
    )


def test_run_once_processes_assets_and_advances_cursor(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assets = [_asset("a", 1), _asset("b", 2), _asset("c", 3)]
    fake = FakeImmich(batches=[assets, []])  # second call returns empty → stop
    fixed_now = datetime(2026, 5, 28, 13, 0, 0, tzinfo=UTC)  # later than all updates

    summary = run_once(conn, fake, batch_size=100, now=fixed_now)

    assert isinstance(summary, RunSummary)
    assert summary.assets_seen == 3
    assert summary.assets_processed == 3
    assert summary.errors == 0
    # Cursor advanced to the latest updated_at
    assert read_cursor(conn) == assets[-1].updated_at
    # Initial call used EPOCH_CURSOR
    assert fake.calls[0]["updated_after"] == EPOCH_CURSOR


def test_run_once_catches_up_when_batch_full(tmp_path: Path) -> None:
    """Full batch (== batch_size) triggers an immediate catch-up call.
    A partial batch (< batch_size) means we're caught up; loop exits.
    """
    conn = _conn(tmp_path)
    batch1 = [_asset(f"a{i}", i + 1) for i in range(3)]      # full
    batch2 = [_asset(f"b{i}", 100 + i) for i in range(2)]    # partial → stop
    fake = FakeImmich(batches=[batch1, batch2])
    fixed_now = datetime(2026, 5, 28, 14, 0, 0, tzinfo=UTC)

    summary = run_once(conn, fake, batch_size=3, now=fixed_now)

    assert summary.assets_seen == 5
    assert summary.assets_processed == 5
    assert len(fake.calls) == 2  # batch1 was full → catch-up; batch2 was partial → done


def test_run_once_records_run_in_worker_runs(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    fake = FakeImmich(batches=[[]])
    fixed_now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)

    run_once(conn, fake, batch_size=100, now=fixed_now)

    rows = conn.execute(
        "SELECT assets_seen, assets_processed, errors, finished_at FROM worker_runs"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["finished_at"] is not None


def test_run_once_on_immich_error_records_error_and_does_not_advance(tmp_path: Path) -> None:
    from home_photo_repo.immich_client import ImmichClientError

    class BrokenImmich:
        calls = 0

        def search_metadata(self, *, updated_after, size=100, order="asc"):
            BrokenImmich.calls += 1
            raise ImmichClientError("simulated outage")

    conn = _conn(tmp_path)
    fixed_now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    summary = run_once(conn, BrokenImmich(), batch_size=100, now=fixed_now)

    assert summary.errors == 1
    assert read_cursor(conn) == EPOCH_CURSOR  # unchanged
    row = conn.execute("SELECT errors, notes FROM worker_runs").fetchone()
    assert row["errors"] == 1
    assert "simulated outage" in (row["notes"] or "")
