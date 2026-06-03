"""Monthly Google Places API call budget tracker.

The budget is stored in worker_state under key ``google_places_budget``::

    {"month": "2026-06", "used": 45, "limit": 1000}

It auto-resets when the calendar month changes so the limit applies
per-month, not in total.

Usage::

    budget = GoogleBudget(limit=1000)

    if budget.check_and_consume(conn):
        # safe to call Google Places API
        result = google_client.search_nearby(...)
    else:
        # budget exhausted for this month — skip and retry next month
        ...
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime

log = logging.getLogger(__name__)

_STATE_KEY = "google_places_budget"


def _current_month() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m")


def _next_month_start() -> datetime:
    """Return the first instant of next calendar month (UTC)."""
    now = datetime.now(tz=UTC)
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1,
                           hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=now.month + 1, day=1,
                       hour=0, minute=0, second=0, microsecond=0)


class GoogleBudget:
    """Monthly call-count budget for the Google Places API.

    All state is persisted in ``worker_state`` so it survives worker restarts.
    """

    def __init__(self, *, limit: int = 1000) -> None:
        self._limit = limit

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_and_consume(self, conn: sqlite3.Connection) -> bool:
        """Atomically check + decrement the budget.

        Returns ``True`` if a call is allowed and records the consumption.
        Returns ``False`` if the monthly limit has been reached.
        """
        state = self._load(conn)
        if state["used"] >= state["limit"]:
            log.warning(
                "google_places budget exhausted: %d/%d used in %s",
                state["used"], state["limit"], state["month"],
            )
            return False
        state["used"] += 1
        self._save(conn, state)
        return True

    def report(self, conn: sqlite3.Connection) -> str:
        """Human-readable one-liner for logging."""
        state = self._load(conn)
        remaining = max(state["limit"] - state["used"], 0)
        return (
            f"{state['used']}/{state['limit']} used in {state['month']} "
            f"({remaining} remaining)"
        )

    def used_this_month(self, conn: sqlite3.Connection) -> int:
        return self._load(conn)["used"]

    def remaining(self, conn: sqlite3.Connection) -> int:
        state = self._load(conn)
        return max(state["limit"] - state["used"], 0)

    def limit(self) -> int:
        return self._limit

    def next_month_start(self) -> datetime:
        return _next_month_start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self, conn: sqlite3.Connection) -> dict:
        """Load state from DB, resetting if the month has rolled over."""
        row = conn.execute(
            "SELECT value FROM worker_state WHERE key = ?", (_STATE_KEY,)
        ).fetchone()

        current_month = _current_month()

        if row is None:
            state = {"month": current_month, "used": 0, "limit": self._limit}
            self._save(conn, state)
            return state

        state = json.loads(row["value"] if hasattr(row, "keys") else row[0])

        # Month rolled over → reset counter, keep limit.
        if state.get("month") != current_month:
            log.info(
                "google_places budget: new month %s — resetting counter "
                "(previous: %d/%d used in %s)",
                current_month, state.get("used", 0), state.get("limit", self._limit),
                state.get("month", "?"),
            )
            state = {"month": current_month, "used": 0, "limit": self._limit}
            self._save(conn, state)

        # Honour live limit changes (e.g. user updates the config).
        state["limit"] = self._limit
        return state

    def _save(self, conn: sqlite3.Connection, state: dict) -> None:
        conn.execute(
            """
            INSERT INTO worker_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_STATE_KEY, json.dumps(state)),
        )


__all__ = ["GoogleBudget"]
