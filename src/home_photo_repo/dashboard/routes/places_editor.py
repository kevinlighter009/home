"""GET /places and POST /places/{add,delete}."""

from __future__ import annotations

import contextlib
import uuid
from typing import cast

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace

router = APIRouter()

_VALID_TYPES = ("home", "office", "friend_place", "restaurant", "outdoor", "other")


@router.get("/places", response_class=HTMLResponse)
def places_list(request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    gen = deps.get_db()
    conn = next(gen)
    try:
        places = PlacesRepository(conn).list_all()
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)

    templates = request.app.state.templates
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request,
            "places.html",
            {
                "active": "places",
                "places": [
                    {
                        "id": p.id, "name": p.name, "type": p.type,
                        "latitude": p.latitude, "longitude": p.longitude,
                        "radius_m": p.radius_m,
                        "is_curated": p.id.startswith("curated:"),
                    }
                    for p in places
                ],
                "valid_types": _VALID_TYPES,
            },
        ),
    )


@router.post("/places/add")
def places_add(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),  # noqa: A002
    lat: float = Form(...),
    lng: float = Form(...),
    radius: int = Form(50),
    notes: str = Form(""),
) -> RedirectResponse:
    if type not in _VALID_TYPES:
        return RedirectResponse(url="/places?error=invalid_type", status_code=303)
    deps = request.app.state.deps
    gen = deps.get_db()
    conn = next(gen)
    try:
        PlacesRepository(conn).insert(
            CuratedPlace(
                id=f"curated:{uuid.uuid4()}",
                name=name, type=type, latitude=lat, longitude=lng,
                radius_m=radius, google_place_id=None, address=None,
                notes=notes or None,
            )
        )
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)
    return RedirectResponse(url="/places", status_code=303)


@router.post("/places/delete")
def places_delete(
    request: Request,
    id: str = Form(...),  # noqa: A002
) -> RedirectResponse:
    deps = request.app.state.deps
    gen = deps.get_db()
    conn = next(gen)
    try:
        PlacesRepository(conn).delete_by_id(id)
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)
    return RedirectResponse(url="/places", status_code=303)
