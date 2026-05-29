"""Per-asset pipeline.

Plan 1 scope: insert a `discovered` row, idempotent on immich_asset_id,
respecting a readiness window that lets Immich's EXIF job finish before
we either record-or-defer GPS-less photos.

Plan 2 extension: after the discovered insert, if providers are given,
run Stage A (is-this-food). If positive above threshold, run Stage B
(dish + cuisine). Results land in photo_analysis. Errors flag the asset
for review and increment error_attempts.
"""

from __future__ import annotations

import enum
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Protocol

from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.providers.base import ProviderError, VisionLLMProvider
from home_photo_repo.llm.rate_limiter import TokenBucket
from home_photo_repo.llm.stage_a import StageAResult, run_stage_a
from home_photo_repo.llm.stage_b import StageBResult, run_stage_b

READINESS_MAX_AGE: timedelta = timedelta(minutes=10)

log = logging.getLogger(__name__)


class ProcessResult(enum.Enum):
    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"
    DEFERRED_NOT_READY = "deferred_not_ready"
    STAGE_A_NOT_FOOD = "stage_a_not_food"
    STAGE_A_AND_B_DONE = "stage_a_and_b_done"
    STAGE_A_ONLY_ERROR = "stage_a_only_error"
    STAGE_B_ERROR = "stage_b_error"


class _ThumbnailFetcher(Protocol):
    def get_thumbnail(self, asset_id: str, *, size: str = ...) -> bytes: ...


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def process_asset(
    conn: sqlite3.Connection,
    asset: ImmichAsset,
    *,
    now: datetime | None = None,
    immich: _ThumbnailFetcher | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = 0.6,
    stage_b_review_threshold: float = 0.7,
) -> ProcessResult:
    """Process one asset.

    Plan 1 path: insert discovered row (if `stage_a_provider is None`).
    Plan 2 path: insert + Stage A + (if food) Stage B.

    Keyword `immich` is required when any provider is set (needed to fetch
    image bytes). All injection points are optional so existing Plan 1
    callers continue to work.
    """
    current_time = now or _utcnow()

    # Idempotency: skip if already present AND already classified.
    existing = conn.execute(
        "SELECT stage_a_ran_at FROM photo_analysis WHERE immich_asset_id = ?",
        (asset.id,),
    ).fetchone()
    if existing is not None:
        # If row exists AND Stage A already ran, treat as fully present.
        if existing["stage_a_ran_at"] is not None:
            return ProcessResult.ALREADY_PRESENT
        # Row exists but Stage A hasn't run yet. If no provider was given
        # (Plan 1 path), there's nothing more to do — treat as present.
        if stage_a_provider is None:
            return ProcessResult.ALREADY_PRESENT
        # Otherwise fall through to LLM section (resume case).
        row_exists = True
    else:
        row_exists = False

    has_gps = asset.latitude is not None and asset.longitude is not None
    age = current_time - asset.updated_at
    if not row_exists and not has_gps and age < READINESS_MAX_AGE:
        return ProcessResult.DEFERRED_NOT_READY

    if not row_exists:
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

    # Plan 1 stop point: if no providers were injected, we're done.
    if stage_a_provider is None:
        return ProcessResult.INSERTED

    if immich is None:
        raise ValueError("process_asset: immich client required when providers given")

    # --- Stage A ---
    try:
        if rate_limiter is not None:
            rate_limiter.acquire()
        thumb_bytes = immich.get_thumbnail(asset.id, size="thumbnail")
        stage_a = run_stage_a(stage_a_provider, image_bytes=thumb_bytes)
    except ProviderError as e:
        log.warning("stage_a failed for asset %s: %s", asset.id, e)
        _record_stage_a_error(conn, asset.id, str(e))
        return ProcessResult.STAGE_A_ONLY_ERROR
    except Exception as e:  # noqa: BLE001
        log.exception("stage_a unexpected failure for asset %s", asset.id)
        _record_stage_a_error(conn, asset.id, f"unexpected: {e!r}")
        return ProcessResult.STAGE_A_ONLY_ERROR
    _record_stage_a_result(conn, asset.id, stage_a, current_time)

    if not stage_a.is_food or stage_a.confidence < stage_a_food_threshold:
        return ProcessResult.STAGE_A_NOT_FOOD

    if stage_b_provider is None:
        # Configured Stage A only.
        return ProcessResult.STAGE_A_NOT_FOOD

    # --- Stage B ---
    try:
        if rate_limiter is not None:
            rate_limiter.acquire()
        preview_bytes = immich.get_thumbnail(asset.id, size="preview")
        stage_b = run_stage_b(stage_b_provider, image_bytes=preview_bytes)
    except ProviderError as e:
        log.warning("stage_b failed for asset %s: %s", asset.id, e)
        _record_stage_b_error(conn, asset.id, str(e))
        return ProcessResult.STAGE_B_ERROR
    except Exception as e:  # noqa: BLE001
        log.exception("stage_b unexpected failure for asset %s", asset.id)
        _record_stage_b_error(conn, asset.id, f"unexpected: {e!r}")
        return ProcessResult.STAGE_B_ERROR

    needs_review = stage_b.confidence < stage_b_review_threshold
    _record_stage_b_result(
        conn, asset.id, stage_b, current_time, needs_review=needs_review
    )
    return ProcessResult.STAGE_A_AND_B_DONE


def _record_stage_a_result(
    conn: sqlite3.Connection,
    asset_id: str,
    result: StageAResult,
    now: datetime,
) -> None:
    conn.execute(
        """
        UPDATE photo_analysis
           SET stage_a_is_food    = ?,
               stage_a_confidence = ?,
               stage_a_model      = ?,
               stage_a_ran_at     = ?,
               last_error         = NULL
         WHERE immich_asset_id = ?
        """,
        (
            1 if result.is_food else 0,
            result.confidence,
            result.model,
            now.isoformat(),
            asset_id,
        ),
    )


def _record_stage_a_error(
    conn: sqlite3.Connection, asset_id: str, message: str
) -> None:
    conn.execute(
        """
        UPDATE photo_analysis
           SET last_error    = ?,
               error_attempts = error_attempts + 1,
               review_status  = 'needs_review'
         WHERE immich_asset_id = ?
        """,
        (f"stage_a: {message}", asset_id),
    )


def _record_stage_b_result(
    conn: sqlite3.Connection,
    asset_id: str,
    result: StageBResult,
    now: datetime,
    *,
    needs_review: bool,
) -> None:
    review_status = "needs_review" if needs_review else "auto"
    conn.execute(
        """
        UPDATE photo_analysis
           SET dish_name          = ?,
               cuisine            = ?,
               stage_b_confidence = ?,
               stage_b_model      = ?,
               stage_b_ran_at     = ?,
               stage_b_raw_json   = ?,
               review_status      = ?,
               last_error         = NULL
         WHERE immich_asset_id = ?
        """,
        (
            result.dish_name,
            result.cuisine,
            result.confidence,
            result.model,
            now.isoformat(),
            result.raw_json,
            review_status,
            asset_id,
        ),
    )


def _record_stage_b_error(
    conn: sqlite3.Connection, asset_id: str, message: str
) -> None:
    conn.execute(
        """
        UPDATE photo_analysis
           SET last_error    = ?,
               error_attempts = error_attempts + 1,
               review_status  = 'needs_review'
         WHERE immich_asset_id = ?
        """,
        (f"stage_b: {message}", asset_id),
    )


__all__ = ["READINESS_MAX_AGE", "ProcessResult", "process_asset"]
