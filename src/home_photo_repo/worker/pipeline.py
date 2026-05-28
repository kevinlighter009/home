"""Per-asset pipeline.

Plan 1 scope: insert a `discovered` row, idempotent on immich_asset_id,
respecting a readiness window that lets Immich's EXIF job finish before
we either record-or-defer GPS-less photos.
"""

from __future__ import annotations

import enum
import sqlite3
from datetime import UTC, datetime, timedelta

from home_photo_repo.immich_types import ImmichAsset

READINESS_MAX_AGE: timedelta = timedelta(minutes=10)


class ProcessResult(enum.Enum):
    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"
    DEFERRED_NOT_READY = "deferred_not_ready"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def process_asset(
    conn: sqlite3.Connection,
    asset: ImmichAsset,
    *,
    now: datetime | None = None,
) -> ProcessResult:
    """Insert (or no-op) one Immich asset into photo_analysis.

    `now` is injectable for tests. In production callers pass nothing.
    """
    current_time = now or _utcnow()

    # Idempotency: skip if already present.
    existing = conn.execute(
        "SELECT 1 FROM photo_analysis WHERE immich_asset_id = ?", (asset.id,)
    ).fetchone()
    if existing is not None:
        return ProcessResult.ALREADY_PRESENT

    # Readiness check: if GPS is missing and the asset is recent,
    # defer — Immich's EXIF job may not have completed yet.
    has_gps = asset.latitude is not None and asset.longitude is not None
    age = current_time - asset.updated_at
    if not has_gps and age < READINESS_MAX_AGE:
        return ProcessResult.DEFERRED_NOT_READY

    review_status = "auto" if has_gps else "needs_review"
    last_error = None if has_gps else "no_gps"

    conn.execute(
        """
        INSERT INTO photo_analysis (
            immich_asset_id, first_seen_at, taken_at, latitude, longitude,
            uploader_user_id, review_status, last_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset.id,
            current_time.isoformat(),
            asset.taken_at.isoformat() if asset.taken_at else None,
            asset.latitude,
            asset.longitude,
            asset.owner_id or None,
            review_status,
            last_error,
        ),
    )
    return ProcessResult.INSERTED


__all__ = ["READINESS_MAX_AGE", "ProcessResult", "process_asset"]
