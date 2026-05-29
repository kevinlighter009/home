"""GET /feed — chronological grid of food photos."""

from __future__ import annotations

import contextlib
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

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

    where = ["stage_a_is_food = 1"]
    params: list[object] = []
    if venue_type:
        where.append("venue_type = ?")
        params.append(venue_type)
    where_sql = " AND ".join(where)

    gen = deps.get_db()
    conn = next(gen)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM photo_analysis WHERE {where_sql}",  # noqa: S608
            tuple(params),
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT immich_asset_id, dish_name, cuisine, taken_at,
                   venue_type, place_id, review_status
              FROM photo_analysis
             WHERE {where_sql}
          ORDER BY taken_at DESC NULLS LAST
             LIMIT ? OFFSET ?
            """,  # noqa: S608
            (*params, _PAGE_SIZE, offset),
        ).fetchall()
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)

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
            },
        ),
    )
