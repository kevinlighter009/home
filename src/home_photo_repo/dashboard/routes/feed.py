"""GET /feed — chronological grid of food photos."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from home_photo_repo.places.types import VALID_VENUE_TYPES

router = APIRouter()
_PAGE_SIZE = 24


@router.get("/feed", response_class=HTMLResponse)
def feed(
    request: Request,
    page: int = 1,
    venue_type: str | None = None,
) -> HTMLResponse:
    deps = request.app.state.deps
    page = max(1, page)
    offset = (page - 1) * _PAGE_SIZE

    has_filter = bool(venue_type)
    with deps.db_conn() as conn:
        if has_filter:
            total = conn.execute(
                "SELECT COUNT(*) FROM photo_analysis "
                "WHERE stage_a_is_food = 1 AND venue_type = ?",
                (venue_type,),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT immich_asset_id, dish_name, cuisine, taken_at,
                       venue_type, place_id, review_status
                  FROM photo_analysis
                 WHERE stage_a_is_food = 1 AND venue_type = ?
              ORDER BY taken_at DESC NULLS LAST
                 LIMIT ? OFFSET ?
                """,
                (venue_type, _PAGE_SIZE, offset),
            ).fetchall()
        else:
            total = conn.execute(
                "SELECT COUNT(*) FROM photo_analysis WHERE stage_a_is_food = 1"
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT immich_asset_id, dish_name, cuisine, taken_at,
                       venue_type, place_id, review_status
                  FROM photo_analysis
                 WHERE stage_a_is_food = 1
              ORDER BY taken_at DESC NULLS LAST
                 LIMIT ? OFFSET ?
                """,
                (_PAGE_SIZE, offset),
            ).fetchall()

    templates = request.app.state.templates
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request,
            "feed.html",
            {
                "active": "feed",
                "photos": [dict(r) for r in rows],
                "page": page,
                "total": total,
                "has_prev": page > 1,
                "has_next": page * _PAGE_SIZE < total,
                "venue_filter": venue_type or "",
                "valid_venue_types": list(VALID_VENUE_TYPES) + ["unknown"],
            },
        ),
    )
