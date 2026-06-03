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
    user_id: str | None = None,
) -> HTMLResponse:
    deps = request.app.state.deps
    page = max(1, page)
    offset = (page - 1) * _PAGE_SIZE

    # Build WHERE clause dynamically from active filters.
    conditions = ["stage_a_is_food = 1"]
    params: list[object] = []
    if venue_type:
        conditions.append("venue_type = ?")
        params.append(venue_type)
    if user_id:
        conditions.append("uploader_user_id = ?")
        params.append(user_id)
    where = " AND ".join(conditions)

    with deps.db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM photo_analysis WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT immich_asset_id, dish_name, cuisine, taken_at,
                   venue_type, place_id, review_status
              FROM photo_analysis
             WHERE {where}
          ORDER BY taken_at DESC NULLS LAST
             LIMIT ? OFFSET ?
            """,
            [*params, _PAGE_SIZE, offset],
        ).fetchall()
        users = conn.execute(
            "SELECT user_id, username, display_name FROM immich_users ORDER BY display_name"
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
                "user_filter": user_id or "",
                "valid_venue_types": list(VALID_VENUE_TYPES) + ["unknown"],
                "users": [dict(u) for u in users],
            },
        ),
    )
