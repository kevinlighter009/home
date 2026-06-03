"""GET / — Leaflet map of food photos."""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def map_view(
    request: Request,
    user_id: str | None = None,
) -> HTMLResponse:
    deps = request.app.state.deps

    conditions = [
        "p.stage_a_is_food = 1",
        "p.latitude IS NOT NULL",
        "p.longitude IS NOT NULL",
    ]
    params: list[object] = []
    if user_id:
        conditions.append("p.uploader_user_id = ?")
        params.append(user_id)
    where = " AND ".join(conditions)

    with deps.db_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT p.immich_asset_id, p.latitude, p.longitude,
                   p.dish_name, p.cuisine, p.venue_type,
                   pl.name AS place_name
              FROM photo_analysis p
         LEFT JOIN places pl ON pl.id = p.place_id
             WHERE {where}
          ORDER BY p.taken_at DESC NULLS LAST
             LIMIT 5000
            """,
            params,
        ).fetchall()
        users = conn.execute(
            "SELECT user_id, username, display_name FROM immich_users ORDER BY display_name"
        ).fetchall()

    markers: list[dict[str, Any]] = [
        {
            "id": r["immich_asset_id"],
            "lat": r["latitude"],
            "lng": r["longitude"],
            "dish": r["dish_name"] or "(unclassified)",
            "cuisine": r["cuisine"],
            "venue_type": r["venue_type"],
            "place_name": r["place_name"],
        }
        for r in rows
    ]
    templates = request.app.state.templates
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request,
            "map.html",
            {
                "active": "map",
                "markers_json": json.dumps(markers),
                "count": len(markers),
                "user_filter": user_id or "",
                "users": [dict(u) for u in users],
            },
        ),
    )
