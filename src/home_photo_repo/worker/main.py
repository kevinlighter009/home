"""Worker main loop.

`run_once` does one poll-and-catch-up cycle: it fetches assets newer than the
cursor and processes each through the pipeline, advancing the cursor per-asset.
It loops internally as long as Immich returns full batches (catch-up).

`run_backfill_once` does one page of a full-library page sweep, used when the
updatedAfter cursor cannot reach historical assets (e.g. a bulk import where
all assets share the same updatedAt timestamp).

`run_forever` supports multiple Immich users.  Each API key configured in
settings gets its own ImmichClient, and each user's cursors are namespaced
independently so processing never crosses account boundaries.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
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
from home_photo_repo.llm.venue_disambiguator import (
    DisambiguatedVenue,
    disambiguate,
)
from home_photo_repo.places.google_places import GooglePlacesClient
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import NearbyPlace
from home_photo_repo.settings_factory import load_settings
from home_photo_repo.worker.cursor import (
    read_backfill_page,
    read_cursor,
    write_backfill_page,
    write_cursor,
)
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

    def search_all_assets(
        self,
        *,
        page: int = ...,
        size: int = ...,
        order: str = ...,
    ) -> tuple[list[ImmichAsset], int | None]: ...

    def get_thumbnail(self, asset_id: str, *, size: str = ...) -> bytes: ...

    def get_me(self) -> dict[str, str]: ...

    def get_asset_statistics(self) -> dict[str, int]: ...


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
    user_id: str = "",
    now: datetime | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
    venue_disambiguator: Callable[
        [bytes, list[NearbyPlace]], DisambiguatedVenue
    ] | None = None,
) -> RunSummary:
    """Poll Immich until it returns a non-full batch; process every asset."""
    summary = RunSummary()
    current_time = now or _utcnow()

    run_id = _begin_run(conn, current_time)
    try:
        while True:
            cursor_ts, cursor_last_id = read_cursor(conn, user_id=user_id)
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
                        venue_disambiguator=venue_disambiguator,
                    )
                except Exception as e:  # noqa: BLE001
                    summary.errors += 1
                    summary.last_error = f"{asset.id}: {e!r}"
                    log.exception("pipeline failed on asset %s", asset.id)
                    write_cursor(conn, asset.updated_at, last_id=asset.id, user_id=user_id)
                    continue
                if result is not ProcessResult.DEFERRED_NOT_READY:
                    summary.assets_processed += 1
                write_cursor(conn, asset.updated_at, last_id=asset.id, user_id=user_id)
            if len(assets) < batch_size:
                break
    finally:
        _finish_run(conn, run_id, summary)
    return summary


def run_backfill_once(
    conn: sqlite3.Connection,
    immich: _ImmichLike,
    *,
    batch_size: int,
    user_id: str = "",
    now: datetime | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
    venue_disambiguator: Callable[
        [bytes, list[NearbyPlace]], DisambiguatedVenue
    ] | None = None,
) -> tuple[RunSummary, bool]:
    """Fetch and process one page of the full-library backfill sweep.

    Unlike run_once (which uses an updatedAfter timestamp cursor), this method
    iterates through ALL Immich assets page by page. Already-classified assets
    are skipped instantly by the pipeline's idempotency check (ALREADY_PRESENT).

    Returns (summary, backfill_still_running). When backfill_still_running is
    False the sweep is complete and run_once should take over for incremental
    polling.
    """
    current_page = read_backfill_page(conn, user_id=user_id)
    if current_page is None:
        return RunSummary(), False  # already complete

    current_time = now or _utcnow()
    summary = RunSummary()
    run_id = _begin_run(conn, current_time)
    try:
        assets, next_page = immich.search_all_assets(page=current_page, size=batch_size)
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
                    venue_disambiguator=venue_disambiguator,
                )
                if result is not ProcessResult.DEFERRED_NOT_READY:
                    summary.assets_processed += 1
            except Exception as e:  # noqa: BLE001
                summary.errors += 1
                summary.last_error = f"{asset.id}: {e!r}"
                log.exception("backfill pipeline failed on asset %s", asset.id)
        write_backfill_page(conn, next_page, user_id=user_id)  # None → complete
    finally:
        _finish_run(conn, run_id, summary)

    still_running = next_page is not None
    return summary, still_running


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


def _reconcile(
    conn: sqlite3.Connection,
    client: _ImmichLike,
    *,
    user_id: str,
    username: str,
    gap_threshold: int = 50,
) -> bool:
    """Compare Immich asset total with photo_analysis count.

    If Immich has significantly more assets than we have processed, this means
    photos were missed — most likely a bulk import where all assets share the
    same ``updated_at`` timestamp, causing the incremental cursor to skip them.

    When a gap larger than ``gap_threshold`` is detected the backfill page is
    reset to 1 so the worker re-sweeps the full library on the next iteration.
    Already-classified assets are skipped instantly by the pipeline's
    idempotency check (ALREADY_PRESENT), so the re-sweep only does real work
    for the assets that were missed.

    Returns True if a backfill was triggered, False otherwise.
    """
    try:
        stats = client.get_asset_statistics()
        immich_total = stats["total"]
    except Exception as e:  # noqa: BLE001
        log.warning("[%s] reconcile: could not fetch Immich asset count: %s", username, e)
        return False

    row = conn.execute(
        "SELECT COUNT(*) FROM photo_analysis WHERE uploader_user_id = ? AND stage_a_ran_at IS NOT NULL",
        (user_id,),
    ).fetchone()
    processed = row[0] if row else 0

    gap = immich_total - processed
    log.debug(
        "[%s] reconcile: immich=%d processed=%d gap=%d threshold=%d",
        username, immich_total, processed, gap, gap_threshold,
    )

    if gap > gap_threshold:
        log.warning(
            "[%s] reconcile: gap of %d detected (immich=%d, processed=%d) "
            "— resetting backfill to sweep missed assets",
            username, gap, immich_total, processed,
        )
        write_backfill_page(conn, 1, user_id=user_id)
        return True

    return False


def _upsert_user(conn: sqlite3.Connection, user_info: dict[str, str]) -> None:
    """Insert or update a row in immich_users from /api/users/me response."""
    conn.execute(
        """
        INSERT INTO immich_users (user_id, username, display_name, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE
           SET username     = excluded.username,
               display_name = excluded.display_name,
               updated_at   = excluded.updated_at
        """,
        (user_info["id"], user_info.get("email", ""), user_info.get("name", "")),
    )


def run_forever(settings: Settings) -> None:  # pragma: no cover - integration entrypoint
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    repo_root = Path(__file__).resolve().parents[3]
    conn = get_connection(settings.db_path)
    apply_migrations(conn, repo_root / "migrations")

    # Build one ImmichClient per configured API key; resolve user info at startup.
    all_keys = settings.all_api_keys_list
    clients: list[tuple[str, str, ImmichClient]] = []  # (user_id, username, client)
    for api_key in all_keys:
        client = ImmichClient(
            base_url=str(settings.immich_base_url),
            api_key=api_key,
        )
        try:
            user_info = client.get_me()
        except ImmichClientError as e:
            log.error("failed to resolve user for API key (skipping): %s", e)
            client.close()
            continue
        _upsert_user(conn, user_info)
        clients.append((user_info["id"], user_info.get("name", user_info["id"]), client))
        log.info("registered user: %s (%s)", user_info.get("name"), user_info["id"])

    if not clients:
        log.error("no valid Immich API keys — exiting")
        return

    stage_a_provider = build_provider("stage_a", settings)
    stage_b_provider = build_provider("stage_b", settings)
    rate_limiter = TokenBucket(
        rate_per_minute=settings.anthropic_rate_limit_per_minute,
        capacity=max(1, settings.anthropic_rate_limit_per_minute // 4),
    )

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

    def _disambiguator_fn(
        image_bytes: bytes, candidates: list[NearbyPlace]
    ) -> DisambiguatedVenue:
        return disambiguate(
            stage_b_provider, image_bytes=image_bytes, candidates=candidates,
        )

    # Probe MLX once at startup.
    if "mlx" in (settings.llm_stage_a_provider, settings.llm_stage_b_provider):
        try:
            import httpx as _httpx
            r = _httpx.get(f"{settings.mlx_base_url}/models", timeout=2.0)
            if r.status_code == 200:
                log.info("MLX server reachable at %s", settings.mlx_base_url)
            else:
                log.warning(
                    "MLX server at %s returned %s — fallback will be used per-call",
                    settings.mlx_base_url, r.status_code,
                )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "MLX server at %s unreachable (%s) — fallback will be used per-call",
                settings.mlx_base_url, e,
            )

    # How many incremental polls between reconciliation checks.
    # At poll_interval_seconds=30 this is every ~10 minutes.
    _RECONCILE_EVERY = 20

    user_labels = ", ".join(f"{name}({uid[:8]})" for uid, name, _ in clients)
    log.info(
        "worker starting: users=[%s] poll_interval=%ss batch_size=%s db=%s "
        "stage_a=%s stage_b=%s google_places=%s reconcile_every=%d_polls",
        user_labels,
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
        stage_a_provider.name,
        stage_b_provider.name,
        "enabled" if google_client else "disabled (curated places only)",
        _RECONCILE_EVERY,
    )

    _pipeline_kwargs: dict = dict(
        batch_size=settings.backfill_batch_size,
        stage_a_provider=stage_a_provider,
        stage_b_provider=stage_b_provider,
        rate_limiter=rate_limiter,
        stage_a_food_threshold=settings.stage_a_food_threshold,
        stage_b_review_threshold=settings.stage_b_confidence_review_threshold,
        place_matcher=place_matcher,
        venue_disambiguator=_disambiguator_fn,
    )

    # Per-user counter: how many incremental polls since last reconciliation.
    incremental_poll_counts: dict[str, int] = {uid: 0 for uid, _, _ in clients}

    try:
        while True:
            any_backfilling = False
            for user_id, username, client in clients:
                backfill_page = read_backfill_page(conn, user_id=user_id)
                if backfill_page is not None:
                    any_backfilling = True
                    # Reset counter — reconciliation isn't needed while backfilling.
                    incremental_poll_counts[user_id] = 0
                    summary, still_running = run_backfill_once(
                        conn, client, user_id=user_id, **_pipeline_kwargs
                    )
                    log.info(
                        "[%s] backfill page %d: seen=%d processed=%d errors=%d%s",
                        username,
                        backfill_page,
                        summary.assets_seen,
                        summary.assets_processed,
                        summary.errors,
                        "" if still_running else " → complete, switching to incremental",
                    )
                    # Tiny yield when page was entirely already-processed (avoids spin).
                    if summary.assets_processed == 0 and summary.errors == 0:
                        time.sleep(0.1)
                else:
                    summary = run_once(
                        conn, client, user_id=user_id, **_pipeline_kwargs
                    )
                    log.info(
                        "[%s] run complete: seen=%d processed=%d errors=%d",
                        username,
                        summary.assets_seen,
                        summary.assets_processed,
                        summary.errors,
                    )

                    # Periodic reconciliation: detect assets missed by the cursor
                    # (e.g. bulk imports where all photos share the same updated_at).
                    incremental_poll_counts[user_id] = (
                        incremental_poll_counts.get(user_id, 0) + 1
                    )
                    if incremental_poll_counts[user_id] >= _RECONCILE_EVERY:
                        incremental_poll_counts[user_id] = 0
                        triggered = _reconcile(
                            conn, client,
                            user_id=user_id,
                            username=username,
                        )
                        if triggered:
                            # Re-read so the next iteration starts backfilling.
                            any_backfilling = True

            # Sleep between polls only when all users are in incremental mode.
            if not any_backfilling:
                time.sleep(settings.poll_interval_seconds)

    except KeyboardInterrupt:
        log.info("worker shutting down (KeyboardInterrupt)")
    finally:
        if google_client is not None:
            google_client.close()
        for _, _, client in clients:
            client.close()
        conn.close()


def main() -> None:  # pragma: no cover - process entrypoint
    settings = load_settings()
    run_forever(settings)


if __name__ == "__main__":  # pragma: no cover
    main()
