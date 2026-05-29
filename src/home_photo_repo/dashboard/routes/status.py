"""GET /status — worker run history + summary counts."""

from __future__ import annotations

import contextlib
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/status", response_class=HTMLResponse)
def status_page(request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    gen = deps.get_db()
    conn = next(gen)
    try:
        counts = conn.execute(
            """
            SELECT
              COUNT(*)                                                       AS total,
              SUM(CASE WHEN stage_a_ran_at IS NOT NULL THEN 1 ELSE 0 END)    AS classified,
              SUM(CASE WHEN stage_a_is_food = 1 THEN 1 ELSE 0 END)           AS food,
              SUM(CASE WHEN dish_name IS NOT NULL THEN 1 ELSE 0 END)         AS with_dish,
              SUM(CASE WHEN venue_resolved_at IS NOT NULL THEN 1 ELSE 0 END) AS with_venue,
              SUM(CASE WHEN review_status = 'needs_review' THEN 1 ELSE 0 END) AS needs_review,
              SUM(CASE WHEN error_attempts > 0 THEN 1 ELSE 0 END)             AS errored
              FROM photo_analysis
            """
        ).fetchone()
        cursor_row = conn.execute(
            "SELECT value FROM worker_state WHERE key = 'immich_cursor'"
        ).fetchone()
        runs = conn.execute(
            """
            SELECT started_at, finished_at, assets_seen, assets_processed,
                   errors, notes
              FROM worker_runs
          ORDER BY id DESC
             LIMIT 20
            """
        ).fetchall()
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)

    templates = request.app.state.templates
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request,
            "status.html",
            {
                "active": "status",
                "counts": dict(counts) if counts else {},
                "cursor": cursor_row["value"] if cursor_row else None,
                "runs": [dict(r) for r in runs],
            },
        ),
    )
