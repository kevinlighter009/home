"""GET /place/{id} — venue detail page."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/place/{place_id}", response_class=HTMLResponse)
def place_detail(place_id: str, request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    with deps.db_conn() as conn:
        place_row = conn.execute(
            "SELECT * FROM places WHERE id = ?", (place_id,)
        ).fetchone()
        if place_row is None:
            raise HTTPException(status_code=404, detail="place not found")
        photo_rows = conn.execute(
            """
            SELECT immich_asset_id, dish_name, cuisine, taken_at,
                   stage_b_confidence, review_status
              FROM photo_analysis
             WHERE place_id = ?
               AND dish_name IS NOT NULL
          ORDER BY taken_at DESC NULLS LAST
            """,
            (place_id,),
        ).fetchall()

    templates = request.app.state.templates
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request,
            "place.html",
            {
                "active": None,
                "place": dict(place_row),
                "photos": [dict(r) for r in photo_rows],
            },
        ),
    )
