"""Tests for the Plan-1 pipeline: insert discovered rows idempotently."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.worker.pipeline import (
    READINESS_MAX_AGE,
    ProcessResult,
    process_asset,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset(
    *,
    aid: str = "asset-1",
    lat: float | None = 37.7749,
    lon: float | None = -122.4194,
    updated_at: datetime | None = None,
) -> ImmichAsset:
    now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id=aid,
        owner_id="owner-x",
        original_file_name="IMG.HEIC",
        updated_at=updated_at or now,
        taken_at=now - timedelta(hours=1),
        latitude=lat,
        longitude=lon,
        file_created_at=now,
    )


def test_process_asset_inserts_discovered_row(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    a = _asset()
    now = a.updated_at

    result = process_asset(conn, a, now=now)

    assert result is ProcessResult.INSERTED
    row = conn.execute(
        "SELECT immich_asset_id, latitude, longitude, uploader_user_id, review_status "
        "FROM photo_analysis WHERE immich_asset_id = ?",
        (a.id,),
    ).fetchone()
    assert row is not None
    assert row["latitude"] == pytest.approx(37.7749)
    assert row["longitude"] == pytest.approx(-122.4194)
    assert row["uploader_user_id"] == "owner-x"
    assert row["review_status"] == "auto"


def test_process_asset_is_idempotent(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    a = _asset()
    now = a.updated_at

    assert process_asset(conn, a, now=now) is ProcessResult.INSERTED
    assert process_asset(conn, a, now=now) is ProcessResult.ALREADY_PRESENT

    count = conn.execute(
        "SELECT COUNT(*) FROM photo_analysis WHERE immich_asset_id = ?", (a.id,)
    ).fetchone()[0]
    assert count == 1


def test_process_asset_skips_young_gpsless_asset(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    young_updated = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    now = young_updated + (READINESS_MAX_AGE / 2)  # within readiness window
    a = _asset(lat=None, lon=None, updated_at=young_updated)

    result = process_asset(conn, a, now=now)

    assert result is ProcessResult.DEFERRED_NOT_READY
    count = conn.execute("SELECT COUNT(*) FROM photo_analysis").fetchone()[0]
    assert count == 0


def test_process_asset_records_old_gpsless_for_review(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    old_updated = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    now = old_updated + READINESS_MAX_AGE + timedelta(seconds=1)
    a = _asset(lat=None, lon=None, updated_at=old_updated)

    result = process_asset(conn, a, now=now)

    assert result is ProcessResult.INSERTED
    row = conn.execute(
        "SELECT review_status, last_error FROM photo_analysis WHERE immich_asset_id = ?",
        (a.id,),
    ).fetchone()
    assert row["review_status"] == "needs_review"
    assert row["last_error"] == "no_gps"
