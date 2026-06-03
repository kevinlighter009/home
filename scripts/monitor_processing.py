"""Live processing-progress monitor.

Shows, per Immich user:
  • Total assets in Immich (live from API)
  • Assets processed through Stage A so far (from SQLite)
  • Completion percentage
  • Food detections and errors
  • Estimated time to finish (derived from recent throughput)
  • Backfill page / incremental state

Refreshes every REFRESH_SECONDS until you press Ctrl-C.

Run with:
    make monitor
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import time

from home_photo_repo.config import Settings
from home_photo_repo.immich_client import ImmichClient, ImmichClientError

REFRESH_SECONDS = 30


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_progress(conn: sqlite3.Connection, user_id: str) -> dict[str, int]:
    """Counts for one user from photo_analysis (Stage-A-complete rows only)."""
    row = conn.execute(
        """
        SELECT
            COUNT(*)                                               AS processed,
            SUM(CASE WHEN stage_a_is_food = 1  THEN 1 ELSE 0 END) AS food,
            SUM(CASE WHEN last_error IS NOT NULL THEN 1 ELSE 0 END) AS errors
        FROM photo_analysis
        WHERE uploader_user_id = ?
          AND stage_a_ran_at   IS NOT NULL
        """,
        (user_id,),
    ).fetchone()
    return {
        "processed": row["processed"] or 0,
        "food":      row["food"]      or 0,
        "errors":    row["errors"]    or 0,
    }


def _backfill_states(conn: sqlite3.Connection) -> dict[str, str]:
    """Return {user_id: human-readable-state} for every tracked user."""
    rows = conn.execute(
        "SELECT key, value FROM worker_state WHERE key LIKE 'backfill_page:%'"
    ).fetchall()
    states: dict[str, str] = {}
    for r in rows:
        uid  = r["key"].replace("backfill_page:", "")
        page = json.loads(r["value"]).get("page")
        states[uid] = "complete" if page is None else f"backfill p.{page}"
    return states


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pct(done: int, total: int) -> str:
    if total == 0:
        return "  n/a"
    return f"{min(done / total * 100, 100.0):5.1f}%"


def _eta(done: int, total: int, rate_per_min: float) -> str:
    """Human-readable ETA; — when not applicable."""
    remaining = total - done
    if remaining <= 0:
        return "—"
    if rate_per_min <= 0:
        return "…"
    minutes = remaining / rate_per_min
    if minutes < 90:
        return f"~{minutes:.0f} min"
    return f"~{minutes / 60:.1f} hr"


# ---------------------------------------------------------------------------
# Main render loop
# ---------------------------------------------------------------------------

def _render(
    settings: Settings,
    conn: sqlite3.Connection,
    prev_counts: dict[str, int],
    elapsed_s: float,
) -> dict[str, int]:
    """Print one full-screen refresh frame; return updated counts."""
    os.system("clear")

    w = 80
    print("═" * w)
    print("  📸  Photo Processing Progress")
    print(f"  {time.strftime('%a %b %d  %H:%M:%S %Z %Y')}")
    print("═" * w)

    fmt = "  {:<17} {:>8} {:>9} {:>7}  {:>7} {:>7}  {:>10}  {}"
    print(fmt.format("User", "Immich", "Processed", "%", "Food", "Errors", "ETA", "State"))
    print("─" * w)

    backfill = _backfill_states(conn)
    new_counts: dict[str, int] = {}

    for key in settings.all_api_keys_list:
        try:
            with ImmichClient(
                base_url=str(settings.immich_base_url), api_key=key
            ) as client:
                me    = client.get_me()
                stats = client.get_asset_statistics()
        except ImmichClientError as exc:
            print(f"  [API error: {exc}]")
            continue

        uid   = me["id"]
        name  = (me.get("name") or me.get("email") or uid[:8])[:17]
        total = stats["total"]

        db_stats = _sqlite_progress(conn, uid)
        done     = db_stats["processed"]
        new_counts[uid] = done

        # Throughput rate (photos/min) based on delta since last refresh
        prev  = prev_counts.get(uid, done)
        delta = max(done - prev, 0)
        rate  = (delta / elapsed_s * 60) if elapsed_s > 0 else 0.0

        state   = backfill.get(uid, "incremental")
        # Only show ETA while actively backfilling
        eta_str = _eta(done, total, rate) if state not in ("complete", "incremental") else "—"

        print(fmt.format(
            name,
            f"{total:,}",
            f"{done:,}",
            _pct(done, total),
            f"{db_stats['food']:,}",
            f"{db_stats['errors']:,}",
            eta_str,
            state,
        ))

    print("─" * w)
    print(f"  Refreshing every {REFRESH_SECONDS}s  —  Ctrl-C to quit")
    return new_counts


def main() -> int:
    settings = Settings()
    db_path  = str(settings.db_path)

    if not os.path.exists(db_path):
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        print("Run 'make bootstrap' or 'make ensure-db' first.", file=sys.stderr)
        return 1

    conn = _open_db(db_path)

    def _stop(sig: int, frame: object) -> None:
        print("\nStopped.")
        conn.close()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    prev_counts: dict[str, int] = {}
    last_tick = time.monotonic()

    while True:
        now     = time.monotonic()
        elapsed = now - last_tick
        prev_counts = _render(settings, conn, prev_counts, elapsed)
        last_tick   = time.monotonic()
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
