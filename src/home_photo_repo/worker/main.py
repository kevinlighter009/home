"""Worker main loop.

`run_once` does one poll-and-catch-up cycle: it fetches assets newer than the
cursor and processes each through the pipeline, advancing the cursor per-asset.
It loops internally as long as Immich returns full batches (catch-up).

`run_forever` schedules `run_once` on a timer with sleep-between-polls.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from home_photo_repo.config import (
    DEFAULT_STAGE_A_FOOD_THRESHOLD,
    DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    Settings,
)
from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_client import ImmichClient, ImmichClientError
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.factory import build_provider
from home_photo_repo.llm.providers.base import VisionLLMProvider
from home_photo_repo.llm.rate_limiter import TokenBucket
from home_photo_repo.places.google_places import GooglePlacesClient
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.settings_factory import load_settings
from home_photo_repo.worker.cursor import read_cursor, write_cursor
from home_photo_repo.worker.pipeline import ProcessResult, process_asset

log = logging.getLogger(__name__)


class _ImmichLike(Protocol):
    def search_metadata(
        self,
        *,
        updated_after: datetime,
        last_id: str = ...,
        size: int = ...,
        order: str = ...,
    ) -> list[ImmichAsset]: ...

    def get_thumbnail(self, asset_id: str, *, size: str = ...) -> bytes: ...


@dataclass
class RunSummary:
    assets_seen: int = 0
    assets_processed: int = 0
    errors: int = 0
    last_error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def run_once(
    conn: sqlite3.Connection,
    immich: _ImmichLike,
    *,
    batch_size: int,
    now: datetime | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
) -> RunSummary:
    """Poll Immich until it returns a non-full batch; process every asset."""
    summary = RunSummary()
    current_time = now or _utcnow()

    run_id = _begin_run(conn, current_time)
    try:
        while True:
            cursor_ts, cursor_last_id = read_cursor(conn)
            try:
                assets = immich.search_metadata(
                    updated_after=cursor_ts,
                    last_id=cursor_last_id,
                    size=batch_size,
                    order="asc",
                )
            except ImmichClientError as e:
                summary.errors += 1
                summary.last_error = str(e)
                log.error("immich poll failed: %s", e)
                break

            if not assets:
                break

            for asset in assets:
                summary.assets_seen += 1
                try:
                    result = process_asset(
                        conn,
                        asset,
                        now=current_time,
                        immich=immich,
                        stage_a_provider=stage_a_provider,
                        stage_b_provider=stage_b_provider,
                        rate_limiter=rate_limiter,
                        stage_a_food_threshold=stage_a_food_threshold,
                        stage_b_review_threshold=stage_b_review_threshold,
                        place_matcher=place_matcher,
                    )
                except Exception as e:  # noqa: BLE001 - per-asset isolation
                    summary.errors += 1
                    summary.last_error = f"{asset.id}: {e!r}"
                    log.exception("pipeline failed on asset %s", asset.id)
                    # Advance cursor past the failed asset so the rest of
                    # the batch still gets processed. The asset's row (if
                    # inserted) carries last_error / review_status='needs_review'
                    # from the pipeline's error helpers, so the user can
                    # re-process it from the dashboard.
                    write_cursor(conn, asset.updated_at, last_id=asset.id)
                    continue
                if result is not ProcessResult.DEFERRED_NOT_READY:
                    summary.assets_processed += 1
                write_cursor(conn, asset.updated_at, last_id=asset.id)
            # The for-loop now always completes naturally. Continue the
            # outer while based on batch fullness.
            if len(assets) < batch_size:
                break
    finally:
        _finish_run(conn, run_id, summary)
    return summary


def _begin_run(conn: sqlite3.Connection, now: datetime) -> int:
    cur = conn.execute(
        "INSERT INTO worker_runs (started_at) VALUES (?)", (now.isoformat(),)
    )
    assert cur.lastrowid is not None
    return int(cur.lastrowid)


def _finish_run(conn: sqlite3.Connection, run_id: int, summary: RunSummary) -> None:
    conn.execute(
        """
        UPDATE worker_runs
           SET finished_at      = datetime('now'),
               assets_seen      = ?,
               assets_processed = ?,
               errors           = ?,
               notes            = ?
         WHERE id = ?
        """,
        (
            summary.assets_seen,
            summary.assets_processed,
            summary.errors,
            summary.last_error,
            run_id,
        ),
    )


def run_forever(settings: Settings) -> None:  # pragma: no cover - integration entrypoint
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    repo_root = Path(__file__).resolve().parents[3]
    conn = get_connection(settings.db_path)
    apply_migrations(conn, repo_root / "migrations")
    immich = ImmichClient(
        base_url=str(settings.immich_base_url),
        api_key=settings.immich_api_key.get_secret_value(),
    )
    stage_a_provider = build_provider("stage_a", settings)
    stage_b_provider = build_provider("stage_b", settings)
    rate_limiter = TokenBucket(
        rate_per_minute=settings.anthropic_rate_limit_per_minute,
        capacity=max(1, settings.anthropic_rate_limit_per_minute // 4),
    )

    # Place matcher: build Google client only if a real key is configured.
    google_key = settings.google_places_api_key.get_secret_value()
    google_client = (
        GooglePlacesClient(api_key=google_key)
        if google_key and google_key != "replace_me"
        else None
    )
    place_matcher = PlaceMatcher(
        repo=PlacesRepository(conn),
        google=google_client,
        ambiguous_threshold_m=settings.place_match_ambiguous_threshold_m,
        search_radius_m=settings.google_places_search_radius_m,
    )

    log.info(
        "worker starting: poll_interval=%ss batch_size=%s db=%s "
        "stage_a=%s stage_b=%s google_places=%s",
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
        stage_a_provider.name,
        stage_b_provider.name,
        "enabled" if google_client else "disabled (curated places only)",
    )
    try:
        while True:
            summary = run_once(
                conn, immich,
                batch_size=settings.backfill_batch_size,
                stage_a_provider=stage_a_provider,
                stage_b_provider=stage_b_provider,
                rate_limiter=rate_limiter,
                stage_a_food_threshold=settings.stage_a_food_threshold,
                stage_b_review_threshold=settings.stage_b_confidence_review_threshold,
                place_matcher=place_matcher,
            )
            log.info(
                "run complete: seen=%d processed=%d errors=%d",
                summary.assets_seen,
                summary.assets_processed,
                summary.errors,
            )
            time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        log.info("worker shutting down (KeyboardInterrupt)")
    finally:
        if google_client is not None:
            google_client.close()
        immich.close()
        conn.close()


def main() -> None:  # pragma: no cover - process entrypoint
    settings = load_settings()
    run_forever(settings)


if __name__ == "__main__":  # pragma: no cover
    main()
