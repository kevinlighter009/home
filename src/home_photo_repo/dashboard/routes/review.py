"""Review queue: GET /review lists pending; POST /review/{id} updates."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/review", response_class=HTMLResponse)
def review_list(request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    gen = deps.get_db()
    conn = next(gen)
    try:
        rows = conn.execute(
            """
            SELECT p.immich_asset_id, p.dish_name, p.cuisine, p.taken_at,
                   p.venue_type, p.place_id, p.last_error,
                   p.stage_b_confidence, p.review_notes,
                   pl.name AS place_name
              FROM photo_analysis p
         LEFT JOIN places pl ON pl.id = p.place_id
             WHERE p.review_status = 'needs_review'
          ORDER BY p.first_seen_at DESC
             LIMIT 200
            """
        ).fetchall()
        places = conn.execute(
            "SELECT id, name, type FROM places ORDER BY type, name"
        ).fetchall()
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)

    templates = request.app.state.templates
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request,
            "review.html",
            {
                "active": "review",
                "rows": [dict(r) for r in rows],
                "places": [dict(p) for p in places],
            },
        ),
    )


@router.post("/review/{asset_id}", response_class=HTMLResponse)
def review_submit(
    asset_id: str,
    request: Request,
    dish_name: str = Form(""),
    cuisine: str = Form(""),
    place_id: str = Form(""),
    decision: str = Form("confirm"),
) -> HTMLResponse:
    new_status = "corrected" if decision == "correct" else "confirmed"
    now = datetime.now(tz=UTC).isoformat()

    deps = request.app.state.deps
    gen = deps.get_db()
    conn = next(gen)
    try:
        existing = conn.execute(
            "SELECT 1 FROM photo_analysis WHERE immich_asset_id = ?", (asset_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="asset not found")

        venue_type: str | None = None
        if place_id:
            row = conn.execute(
                "SELECT type FROM places WHERE id = ?", (place_id,)
            ).fetchone()
            if row is not None:
                venue_type = row["type"]

        conn.execute(
            """
            UPDATE photo_analysis
               SET dish_name           = ?,
                   cuisine             = ?,
                   place_id            = ?,
                   place_match_source  = CASE WHEN ? <> ''
                                              THEN 'manual'
                                              ELSE place_match_source END,
                   venue_type          = COALESCE(?, venue_type),
                   review_status       = ?,
                   reviewed_at         = ?
             WHERE immich_asset_id = ?
            """,
            (
                dish_name or None,
                cuisine or None,
                place_id or None,
                place_id,
                venue_type,
                new_status,
                now,
                asset_id,
            ),
        )
        row = conn.execute(
            """
            SELECT p.immich_asset_id, p.dish_name, p.cuisine, p.review_status,
                   pl.name AS place_name
              FROM photo_analysis p
         LEFT JOIN places pl ON pl.id = p.place_id
             WHERE p.immich_asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)

    templates = request.app.state.templates
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request,
            "_review_row.html",
            {"row": dict(row), "after_submit": True},
        ),
    )
