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
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from home_photo_repo.config import (
    DEFAULT_STAGE_A_FOOD_THRESHOLD,
    DEFAULT_STAGE_B_REVIEW_THRESHOLD,
)
from home_photo_repo.immich_client import ImmichAssetNotReadyError
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.prompts import STAGE_A_VERSION, STAGE_B_VERSION
from home_photo_repo.llm.providers.base import ProviderError, VisionLLMProvider
from home_photo_repo.llm.rate_limiter import TokenBucket
from home_photo_repo.llm.stage_a import StageAResult, run_stage_a
from home_photo_repo.llm.stage_b import StageBResult, run_stage_b
from home_photo_repo.llm.venue_disambiguator import (
    DisambiguatedVenue,
    disambiguate,  # noqa: F401 - exported for users who want to compose manually
)
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.types import MatchResult, NearbyPlace

DisambiguatorFn = Callable[[bytes, list[NearbyPlace]], DisambiguatedVenue]

READINESS_MAX_AGE: timedelta = timedelta(minutes=10)

log = logging.getLogger(__name__)


class ProcessResult(enum.Enum):
    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"
    DEFERRED_NOT_READY = "deferred_not_ready"
    STAGE_A_NOT_FOOD = "stage_a_not_food"
    STAGE_A_DONE_NO_STAGE_B = "stage_a_done_no_stage_b"
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
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
    venue_disambiguator: DisambiguatorFn | None = None,
) -> ProcessResult:
    """Process one asset.

    Plan 1 path: insert discovered row (if `stage_a_provider is None`).
    Plan 2 path: insert + Stage A + (if food) Stage B.

    Keyword `immich` is required when any provider is set (needed to fetch
    image bytes). All injection points are optional so existing Plan 1
    callers continue to work.
    """
    current_time = now or _utcnow()
    preview_bytes: bytes | None = None

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
    except ImmichAssetNotReadyError as e:
        # Transient: Immich's thumbnail job hasn't completed yet. When it
        # does, Immich bumps the asset's updated_at and we'll see it again.
        # Don't record as error; row stays with stage_a_ran_at NULL so the
        # next visit retries Stage A cleanly.
        log.debug("stage_a deferred for asset %s: %s", asset.id, e)
        return ProcessResult.DEFERRED_NOT_READY
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
        # Food per Stage A, but Stage B not configured — distinct from
        # NOT_FOOD so dashboards/queries can tell the two cases apart.
        return ProcessResult.STAGE_A_DONE_NO_STAGE_B

    # --- Stage B ---
    try:
        if rate_limiter is not None:
            rate_limiter.acquire()
        preview_bytes = immich.get_thumbnail(asset.id, size="preview")
        stage_b = run_stage_b(stage_b_provider, image_bytes=preview_bytes)
    except ImmichAssetNotReadyError as e:
        # Transient: preview job hasn't completed yet (thumbnail done but
        # preview pending — Immich runs them as separate sub-jobs).
        log.debug("stage_b deferred for asset %s: %s", asset.id, e)
        return ProcessResult.DEFERRED_NOT_READY
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

    # Venue resolution (Plan 3). Only runs if a matcher was provided AND the
    # photo has GPS. The matcher itself decides curated vs google vs unknown.
    if (
        place_matcher is not None
        and asset.latitude is not None
        and asset.longitude is not None
    ):
        match = place_matcher.match(latitude=asset.latitude, longitude=asset.longitude)
        # If matcher returned ambiguous Google candidates AND we have a
        # disambiguator AND we have preview bytes (already fetched for Stage B),
        # let the LLM pick among the candidates.
        if (
            match.needs_review
            and match.ambiguous_candidates
            and venue_disambiguator is not None
            and preview_bytes is not None
        ):
            try:
                pick: DisambiguatedVenue | None = venue_disambiguator(
                    preview_bytes, list(match.ambiguous_candidates)
                )
            except Exception:  # noqa: BLE001
                log.exception("disambiguator failed for asset %s", asset.id)
                pick = None
            if (
                pick is not None
                and pick.google_place_id is not None
                and pick.confidence >= 0.6
            ):
                match = _refine_match_from_disambiguation(match, pick)
        _record_venue_match(conn, asset.id, match, current_time)

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
           SET stage_a_is_food         = ?,
               stage_a_confidence      = ?,
               stage_a_model           = ?,
               stage_a_ran_at          = ?,
               stage_a_prompt_version  = ?,
               last_error              = NULL
         WHERE immich_asset_id = ?
        """,
        (
            1 if result.is_food else 0,
            result.confidence,
            result.model,
            now.isoformat(),
            STAGE_A_VERSION,
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
           SET dish_name              = ?,
               cuisine                = ?,
               stage_b_confidence     = ?,
               stage_b_model          = ?,
               stage_b_ran_at         = ?,
               stage_b_raw_json       = ?,
               stage_b_prompt_version = ?,
               review_status          = ?,
               last_error             = NULL
         WHERE immich_asset_id = ?
        """,
        (
            result.dish_name,
            result.cuisine,
            result.confidence,
            result.model,
            now.isoformat(),
            result.raw_json,
            STAGE_B_VERSION,
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


def _record_venue_match(
    conn: sqlite3.Connection,
    asset_id: str,
    match: MatchResult,
    now: datetime,
) -> None:
    # NB: when match.needs_review, this overwrites any review_notes previously
    # set by Stage B (low confidence). That's intentional — venue ambiguity is
    # more actionable than Stage B confidence, so we surface it on the
    # dashboard's review row. If Stage B's note matters for a particular
    # asset, the user can correct it manually via the review form.
    # If the match itself is ambiguous, escalate review_status; but don't
    # downgrade an already-confirmed/auto status without reason.
    if match.needs_review:
        conn.execute(
            """
            UPDATE photo_analysis
               SET venue_type             = ?,
                   place_id               = ?,
                   place_match_source     = ?,
                   place_match_distance_m = ?,
                   venue_resolved_at      = ?,
                   review_status          = 'needs_review',
                   review_notes           = ?
             WHERE immich_asset_id = ?
            """,
            (
                match.venue_type,
                match.place_id,
                match.source,
                match.distance_m,
                now.isoformat(),
                match.notes,
                asset_id,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE photo_analysis
               SET venue_type             = ?,
                   place_id               = ?,
                   place_match_source     = ?,
                   place_match_distance_m = ?,
                   venue_resolved_at      = ?,
                   review_notes           = ?
             WHERE immich_asset_id = ?
            """,
            (
                match.venue_type,
                match.place_id,
                match.source,
                match.distance_m,
                now.isoformat(),
                match.notes,
                asset_id,
            ),
        )


def _refine_match_from_disambiguation(
    original: MatchResult,
    pick: DisambiguatedVenue,
) -> MatchResult:
    """Replace the matcher's nearest-by-haversine pick with the LLM's
    candidate of choice. The picked place_id must be one of the candidates."""
    matching = next(
        (
            c for c in original.ambiguous_candidates
            if c.google_place_id == pick.google_place_id
        ),
        None,
    )
    if matching is None:
        # Disambiguator returned an unknown id — keep original.
        return original
    return MatchResult(
        place_id=f"gplaces:{matching.google_place_id}",
        venue_type="restaurant",
        distance_m=original.distance_m,
        source="llm_disambiguated",
        needs_review=False,
        notes=(
            f"disambiguated from {len(original.ambiguous_candidates)} candidates "
            f"(conf={pick.confidence:.2f})"
        ),
        ambiguous_candidates=original.ambiguous_candidates,
    )


__all__ = ["READINESS_MAX_AGE", "ProcessResult", "process_asset"]
