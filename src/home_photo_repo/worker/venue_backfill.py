"""Venue resolution backfill for historical food photos.

Processes food photos whose venue was previously unresolved — either because
no Google Places key was configured at the time, or because Google found
nothing and the monthly retry window has now elapsed.

Resolution order per photo:
  1. Local cache check (instant, no API call).
  2. Concurrent Google Places lookup (HTTP, 5 workers in parallel).
  3. Ranking + DB caching on the main thread (SQLite writes are serialised).

The monthly budget (``GoogleBudget``) is consumed atomically before each
Google call; when exhausted the photo is marked ``venue_retry_after=<next
month>`` and skipped.

Typical run for 2,937 legacy photos (~150 distinct venues):
  - ~150 real Google API calls (~$5 of the welcome credit)
  - ~2,787 local cache hits (sub-millisecond each)
  - Total wall-clock time with 5 concurrent workers: 1–3 minutes
"""

from __future__ import annotations

import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.types import MatchResult, NearbyPlace
from home_photo_repo.worker.google_budget import GoogleBudget

log = logging.getLogger(__name__)

_BATCH_SIZE = 50   # photos per backfill cycle
_MAX_WORKERS = 5   # concurrent Google HTTP calls


# ---------------------------------------------------------------------------
# Result summary
# ---------------------------------------------------------------------------

@dataclass
class VenueBackfillSummary:
    resolved: int = 0        # matched to a place (curated or Google)
    cache_hits: int = 0      # resolved from local cache (no API call)
    google_calls: int = 0    # real Google API calls made
    budget_skipped: int = 0  # skipped due to exhausted monthly budget
    google_miss: int = 0     # Google returned no candidates
    errors: int = 0
    still_pending: bool = True


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _pending_count(conn: sqlite3.Connection, user_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM photo_analysis
        WHERE uploader_user_id   = ?
          AND stage_a_is_food    = 1
          AND latitude           IS NOT NULL
          AND (place_match_source = 'unknown' OR venue_resolved_at IS NULL)
          AND (venue_retry_after IS NULL OR venue_retry_after <= datetime('now'))
        """,
        (user_id,),
    ).fetchone()
    return row[0] if row else 0


def has_pending(conn: sqlite3.Connection, user_id: str) -> bool:
    return _pending_count(conn, user_id) > 0


def _fetch_batch(
    conn: sqlite3.Connection, user_id: str, batch_size: int
) -> list[dict[str, Any]]:
    """Fetch up to batch_size food photos needing venue resolution, newest first."""
    rows = conn.execute(
        """
        SELECT immich_asset_id, latitude, longitude
        FROM photo_analysis
        WHERE uploader_user_id   = ?
          AND stage_a_is_food    = 1
          AND latitude           IS NOT NULL
          AND (place_match_source = 'unknown' OR venue_resolved_at IS NULL)
          AND (venue_retry_after IS NULL OR venue_retry_after <= datetime('now'))
        ORDER BY taken_at DESC
        LIMIT ?
        """,
        (user_id, batch_size),
    ).fetchall()
    return [
        {"id": r[0], "lat": r[1], "lng": r[2]}
        for r in rows
    ]


def _write_result(
    conn: sqlite3.Connection,
    asset_id: str,
    match: MatchResult,
    now: datetime,
    budget: GoogleBudget,
) -> None:
    retry_after: str | None = (
        budget.next_month_start().isoformat() if match.retry_next_month else None
    )
    if match.needs_review:
        conn.execute(
            """
            UPDATE photo_analysis
               SET venue_type             = ?,
                   place_id               = ?,
                   place_match_source     = ?,
                   place_match_distance_m = ?,
                   venue_resolved_at      = ?,
                   venue_retry_after      = ?,
                   review_status          = 'needs_review',
                   review_notes           = ?
             WHERE immich_asset_id = ?
            """,
            (match.venue_type, match.place_id, match.source, match.distance_m,
             now.isoformat(), retry_after, match.notes, asset_id),
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
                   venue_retry_after      = ?,
                   review_notes           = ?
             WHERE immich_asset_id = ?
            """,
            (match.venue_type, match.place_id, match.source, match.distance_m,
             now.isoformat(), retry_after, match.notes, asset_id),
        )


# ---------------------------------------------------------------------------
# Concurrent resolution
# ---------------------------------------------------------------------------

def _google_fetch(
    google_client: Any,
    lat: float,
    lng: float,
    radius_m: int,
) -> list[NearbyPlace]:
    """Pure HTTP call — no DB access.  Safe to run in a thread pool."""
    return google_client.search_nearby(latitude=lat, longitude=lng, radius_m=radius_m)


def run_venue_backfill_batch(
    conn: sqlite3.Connection,
    place_matcher: PlaceMatcher,
    budget: GoogleBudget,
    *,
    user_id: str,
    batch_size: int = _BATCH_SIZE,
    max_workers: int = _MAX_WORKERS,
) -> VenueBackfillSummary:
    """Process one batch of pending venue photos for a single user.

    Returns a :class:`VenueBackfillSummary` describing what happened.
    ``still_pending`` is True if more photos remain after this batch.
    """
    summary = VenueBackfillSummary()
    now = datetime.now(tz=UTC)
    batch = _fetch_batch(conn, user_id, batch_size)

    if not batch:
        summary.still_pending = False
        return summary

    google_client = place_matcher._google  # noqa: SLF001 — intentional internal access

    # ── Phase 1: local cache check (fast, sequential, no API) ──────────────
    cache_hits: list[tuple[dict, MatchResult]] = []
    google_needed: list[dict] = []

    for photo in batch:
        local = place_matcher.local_lookup(photo["lat"], photo["lng"])
        if local is not None:
            cache_hits.append((photo, local))
        else:
            google_needed.append(photo)

    # Write cache-hit results immediately.
    for photo, match in cache_hits:
        _write_result(conn, photo["id"], match, now, budget)
        summary.cache_hits += 1
        summary.resolved += 1

    # ── Phase 2: concurrent Google calls for cache misses ──────────────────
    if google_needed and google_client is not None:
        # Deduplicate by rounded GPS (4 decimal places ≈ 11 m grid).
        # ONE Google API call per unique coordinate; result applied to ALL
        # photos at that location — this is the key efficiency fix that
        # prevents burning N budget units for N photos at the same restaurant.
        coord_to_photos: dict[tuple[float, float], list[dict]] = {}
        for photo in google_needed:
            key = (round(photo["lat"], 4), round(photo["lng"], 4))
            coord_to_photos.setdefault(key, []).append(photo)

        unique_coords = list(coord_to_photos.items())  # [(coord_key, [photos…]), …]
        retry_after_str = budget.next_month_start().isoformat()
        future_to_coord: dict = {}
        exhausted_from_idx: int | None = None

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for i, (coord_key, _photos) in enumerate(unique_coords):
                if not budget.check_and_consume(conn):
                    exhausted_from_idx = i
                    break
                lat, lng = coord_key
                future = pool.submit(
                    _google_fetch, google_client, lat, lng,
                    place_matcher.search_radius_m,
                )
                future_to_coord[future] = (coord_key, coord_to_photos[coord_key])

        # Defer any coordinates that didn't get a budget slot.
        if exhausted_from_idx is not None:
            deferred = [
                p
                for _, photos in unique_coords[exhausted_from_idx:]
                for p in photos
            ]
            for photo in deferred:
                conn.execute(
                    "UPDATE photo_analysis SET venue_retry_after = ? "
                    "WHERE immich_asset_id = ?",
                    (retry_after_str, photo["id"]),
                )
            summary.budget_skipped += len(deferred)
            log.warning(
                "google_places budget exhausted — %d photos deferred to next month",
                len(deferred),
            )

        # ── Phase 3: rank + cache + write ALL photos per coordinate ────────
        for future, (coord_key, photos) in future_to_coord.items():
            lat, lng = coord_key
            try:
                candidates = future.result()
                summary.google_calls += 1
            except Exception as exc:  # noqa: BLE001
                log.error("google lookup failed for coord %s: %s", coord_key, exc)
                summary.errors += len(photos)
                continue

            match = place_matcher.match_from_candidates(
                latitude=lat,
                longitude=lng,
                candidates=candidates,
            )
            # Apply the single match result to every photo at this coordinate.
            for photo in photos:
                _write_result(conn, photo["id"], match, now, budget)
                if match.source == "google_places":
                    summary.resolved += 1
                else:
                    summary.google_miss += 1

    elif google_client is None:
        # No Google key — mark all as retry next month.
        retry_after = budget.next_month_start().isoformat()
        for photo in google_needed:
            conn.execute(
                "UPDATE photo_analysis SET venue_retry_after = ? "
                "WHERE immich_asset_id = ?",
                (retry_after, photo["id"]),
            )
        summary.budget_skipped += len(google_needed)

    summary.still_pending = has_pending(conn, user_id)
    return summary


__all__ = ["GoogleBudget", "VenueBackfillSummary", "has_pending",
           "run_venue_backfill_batch"]
