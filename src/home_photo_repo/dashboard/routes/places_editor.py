"""GET /places and POST /places/{add,delete}."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import VALID_VENUE_TYPES as _VALID_TYPES
from home_photo_repo.places.types import CuratedPlace

router = APIRouter()


@router.get("/places", response_class=HTMLResponse)
def places_list(request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    with deps.db_conn() as conn:
        places = PlacesRepository(conn).list_all()

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
    with deps.db_conn() as conn:
        PlacesRepository(conn).insert(
            CuratedPlace(
                id=f"curated:{uuid.uuid4()}",
                name=name, type=type, latitude=lat, longitude=lng,
                radius_m=radius, google_place_id=None, address=None,
                notes=notes or None,
            )
        )
    return RedirectResponse(url="/places", status_code=303)


@router.post("/places/delete")
def places_delete(
    request: Request,
    id: str = Form(...),  # noqa: A002
) -> RedirectResponse:
    deps = request.app.state.deps
    with deps.db_conn() as conn:
        PlacesRepository(conn).delete_by_id(id)
    return RedirectResponse(url="/places", status_code=303)
