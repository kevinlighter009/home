"""FastAPI application factory for the dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from home_photo_repo.dashboard.deps import DashboardDeps

_DASHBOARD_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _DASHBOARD_DIR / "static"
_TEMPLATES_DIR = _DASHBOARD_DIR / "templates"


def create_app(
    *,
    db_path: Path,
    immich_base_url: str,
    immich_api_key: str,
) -> FastAPI:
    app = FastAPI(title="home_photo_repo", docs_url=None, redoc_url=None)
    app.state.deps = DashboardDeps(
        db_path=db_path,
        immich_base_url=immich_base_url,
        immich_api_key=immich_api_key,
    )
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    from home_photo_repo.dashboard.routes import (
        feed,
        map_view,
        place,
        places_editor,
        proxy,
        review,
        status,
    )
    for module in (proxy, map_view, place, feed, review, places_editor, status):
        app.include_router(module.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Routes are registered in subsequent tasks via app.include_router(...)

    return app


__all__ = ["create_app"]
