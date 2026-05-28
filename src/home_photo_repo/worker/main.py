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

from home_photo_repo.config import Settings
from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_client import ImmichClient, ImmichClientError
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.worker.cursor import read_cursor, write_cursor
from home_photo_repo.worker.pipeline import ProcessResult, process_asset

log = logging.getLogger(__name__)


class _ImmichLike(Protocol):
    def search_metadata(
        self, *, updated_after: datetime, size: int = ..., order: str = ...
    ) -> list[ImmichAsset]: ...


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
) -> RunSummary:
    """Poll Immich until it returns a non-full batch; process every asset."""
    summary = RunSummary()
    current_time = now or _utcnow()

    run_id = _begin_run(conn, current_time)
    try:
        while True:
            cursor = read_cursor(conn)
            try:
                assets = immich.search_metadata(
                    updated_after=cursor, size=batch_size, order="asc"
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
                    result = process_asset(conn, asset, now=current_time)
                except Exception as e:  # noqa: BLE001 - per-asset isolation
                    summary.errors += 1
                    summary.last_error = f"{asset.id}: {e!r}"
                    log.exception("pipeline failed on asset %s", asset.id)
                    # Do NOT advance the cursor past a failed asset.
                    break
                else:
                    if result is not ProcessResult.DEFERRED_NOT_READY:
                        summary.assets_processed += 1
                    write_cursor(conn, asset.updated_at)
            else:
                # whole batch processed without break
                if len(assets) < batch_size:
                    break
                continue
            break  # broke out of for-loop due to per-asset failure
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
    log.info(
        "worker starting: poll_interval=%ss batch_size=%s db=%s",
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
    )
    try:
        while True:
            summary = run_once(conn, immich, batch_size=settings.backfill_batch_size)
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
        immich.close()
        conn.close()


def main() -> None:  # pragma: no cover - process entrypoint
    settings = Settings()  # type: ignore[call-arg]
    run_forever(settings)


if __name__ == "__main__":  # pragma: no cover
    main()
