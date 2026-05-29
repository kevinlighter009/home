# Plan 4 — Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A localhost-only web dashboard at `http://127.0.0.1:8000` that surfaces what the worker has been doing — a map of food photos pinned by venue, per-place detail pages, a chronological feed, a review queue for low-confidence classifications, a curated-places editor, and a worker-status page.

**Architecture:** FastAPI + Jinja2 server-rendered HTML, with HTMX for in-place form submits (review queue, places editor) and Leaflet for the map. All static assets (Leaflet, HTMX) are vendored — no CDN, no network at runtime. The dashboard runs as a separate process from the worker; both share the same SQLite via WAL mode. Read paths query `photo_analysis` + `places` directly; image bytes are streamed through a `/proxy/thumbnail/{id}` route that fetches from Immich with HTTP caching headers.

**Tech Stack:** Adds `fastapi`, `uvicorn`, `jinja2`, `python-multipart` to runtime deps. Plus `httpx` (already present) for the thumbnail proxy. Tests use `fastapi.testclient.TestClient`.

**Spec reference:** `docs/specs/2026-05-28-home-photo-repo-design.md` — section 7 (dashboard views, image delivery, HTMX rationale), section 5.2 (DB tables consumed).

**Plan 3 follow-ups bundled in:** items #2 (map Google types to canonical buckets) and #3 (add `outdoor` venue type) from `docs/plans/2026-05-28-plan-3-followups.md` — both addressed in Task 1 to ensure the dashboard surfaces accurate types.

**Out of scope (Plan 5):**
- launchd plists for auto-start
- LAN-exposed dashboard / HTTP Basic auth
- Stage B venue-candidate prompting (deferred from Plan 3 follow-up #1)

**Definition of done:**
- `make dev-dashboard` starts uvicorn at 127.0.0.1:8000.
- Visiting `/` shows a Leaflet map with markers for every food photo, clickable to show dish + thumbnail.
- `/place/{id}` lists every dish recorded at that place with thumbnails.
- `/feed` shows recent food photos chronologically with paging.
- `/review` lets the user confirm / re-classify / re-assign venue for low-confidence rows; submission updates the DB.
- `/places` CRUD UI mirrors the CLI.
- `/status` shows the last 20 worker runs + counts.
- All routes work with worker writing concurrently (WAL mode).
- All tests pass with `pytest-socket` blocking real network.
- `ruff` + `mypy` clean.

---

## File map

| Path | Created in task | Responsibility |
|---|---|---|
| `src/home_photo_repo/places/cli.py` (modify) | 1 | Add `"outdoor"` to `_VALID_TYPES` |
| `src/home_photo_repo/places/matcher.py` (modify) | 1 | Add `"outdoor"` to `_CURATED_VENUE_TYPES`; map Google types to canonical bucket when caching |
| `src/home_photo_repo/places/google_places.py` (modify) | 1 | Export `_FOOD_VENUE_TYPES` for the type-mapping table |
| `tests/test_places_matcher.py` (modify) | 1 | New tests: cafe gets type=cafe (if we choose that), outdoor type accepted |
| `pyproject.toml` (modify) | 2 | Add fastapi, uvicorn, jinja2, python-multipart |
| `requirements.txt` (modify) | 2 | Same |
| `src/home_photo_repo/dashboard/__init__.py` | 2 | Package marker |
| `src/home_photo_repo/dashboard/static/leaflet/leaflet.css` | 2 | Vendored — Leaflet 1.9.4 |
| `src/home_photo_repo/dashboard/static/leaflet/leaflet.js` | 2 | Vendored |
| `src/home_photo_repo/dashboard/static/leaflet/images/*` | 2 | Vendored marker icons |
| `src/home_photo_repo/dashboard/static/htmx.min.js` | 2 | Vendored HTMX 2.0.x |
| `src/home_photo_repo/dashboard/static/css/style.css` | 2 | Minimal site CSS |
| `src/home_photo_repo/dashboard/deps.py` | 3 | `get_db()` / `get_immich()` dependency injection |
| `src/home_photo_repo/dashboard/app.py` | 3 | FastAPI factory `create_app(settings)`; mounts static, registers routes |
| `src/home_photo_repo/dashboard/templates/base.html` | 3 | Base layout: header, nav, content slot |
| `src/home_photo_repo/dashboard/main.py` | 3 | Process entrypoint: `python -m home_photo_repo.dashboard.main` |
| `tests/test_dashboard_app.py` | 3 | Health check; 404 handler; nav present |
| `src/home_photo_repo/dashboard/routes/__init__.py` | 4 | Package marker |
| `src/home_photo_repo/dashboard/routes/proxy.py` | 4 | `/proxy/thumbnail/{asset_id}` streams from Immich |
| `tests/test_dashboard_proxy.py` | 4 | respx-mocked Immich; cache headers; 404 passthrough |
| `src/home_photo_repo/dashboard/routes/map_view.py` | 5 | `/` map page |
| `src/home_photo_repo/dashboard/templates/map.html` | 5 | Leaflet container + marker data injection |
| `tests/test_dashboard_map.py` | 5 | Page renders; markers data correct |
| `src/home_photo_repo/dashboard/routes/place.py` | 6 | `/place/{id}` detail page |
| `src/home_photo_repo/dashboard/templates/place.html` | 6 | Place header + dish grid |
| `tests/test_dashboard_place.py` | 6 | 200 for existing place; 404 for unknown |
| `src/home_photo_repo/dashboard/routes/feed.py` | 7 | `/feed?page=N` |
| `src/home_photo_repo/dashboard/templates/feed.html` | 7 | Photo grid with paging |
| `tests/test_dashboard_feed.py` | 7 | Pagination; filtering by venue_type |
| `src/home_photo_repo/dashboard/routes/review.py` | 8 | `/review` GET + `/review/{asset_id}` POST |
| `src/home_photo_repo/dashboard/templates/review.html` | 8 | Review queue list + inline edit form |
| `src/home_photo_repo/dashboard/templates/_review_row.html` | 8 | HTMX partial for one row |
| `tests/test_dashboard_review.py` | 8 | GET lists needs_review rows; POST updates + returns partial |
| `src/home_photo_repo/dashboard/routes/places_editor.py` | 9 | `/places` GET + POST + POST-delete |
| `src/home_photo_repo/dashboard/templates/places.html` | 9 | Places table + add form + per-row delete |
| `tests/test_dashboard_places.py` | 9 | List, add, delete |
| `src/home_photo_repo/dashboard/routes/status.py` | 10 | `/status` page |
| `src/home_photo_repo/dashboard/templates/status.html` | 10 | Worker runs + counts |
| `tests/test_dashboard_status.py` | 10 | Renders counts correctly |
| `Makefile` (modify) | 11 | `make dev-dashboard` target |
| `scripts/smoke_dashboard.py` | 11 | Optional: HTTP GET / + /status to confirm boot |
| `README.md` (modify) | 12 | Plan 4 status, dashboard URLs, screenshots note |
| `docs/SETUP.md` (modify) | 12 | Dashboard verification section |

---

## Conventions

- Repo root: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home`.
- TDD: test → fail → implement → pass → commit, one commit per task (or per sub-task in Task 1).
- `from __future__ import annotations` in every new `.py`.
- All routes are **sync `def`** (FastAPI runs them in a threadpool — matches the sync `sqlite3` module and keeps the worker's mental model).
- DB access via the `_DB` dependency, which opens a read-only or read-write `sqlite3.Connection` per request (cheap; SQLite WAL allows concurrent readers + 1 writer).
- Templates use Jinja2 autoescape (default on for `.html`).
- No JavaScript framework — Leaflet + HTMX + a few inline `<script>` snippets are it.

---

## Task 1: Plan 3 follow-ups — outdoor type + Google type mapping

Two small Plan 3 follow-ups bundled here so the dashboard surfaces accurate venue types.

### Files
- Modify: `src/home_photo_repo/places/cli.py` (add `"outdoor"` to choices)
- Modify: `src/home_photo_repo/places/matcher.py` (add `"outdoor"` + map Google types when caching)
- Modify: `tests/test_places_matcher.py` (new test for Google type mapping)
- Modify: `tests/test_places_cli.py` (new test for outdoor type acceptance)

### Step 1: Modify `src/home_photo_repo/places/cli.py`

Find:
```python
_VALID_TYPES = ("home", "office", "friend_place", "restaurant", "other")
```
Change to:
```python
_VALID_TYPES = ("home", "office", "friend_place", "restaurant", "outdoor", "other")
```

### Step 2: Modify `src/home_photo_repo/places/matcher.py`

Find:
```python
_CURATED_VENUE_TYPES = {"home", "office", "friend_place", "restaurant", "other"}
```
Change to:
```python
_CURATED_VENUE_TYPES = {"home", "office", "friend_place", "restaurant", "outdoor", "other"}
```

Add a Google-type mapping at module level (above `class PlaceMatcher`):

```python
# Google Places returns multiple type strings per place; we pick the first
# that maps into our canonical venue_type bucket.
_GOOGLE_TYPE_TO_VENUE: dict[str, str] = {
    "restaurant": "restaurant",
    "cafe": "restaurant",
    "bakery": "restaurant",
    "bar": "restaurant",
    "meal_delivery": "restaurant",
    "meal_takeaway": "restaurant",
    # Future: when we widen included_types to parks etc., map them to 'outdoor'
}


def _classify_google_types(types: tuple[str, ...]) -> str:
    """Map a Google place's types tuple to our canonical venue_type bucket.

    All current `_FOOD_VENUE_TYPES` map to 'restaurant'; the function exists
    so the matcher's caching path doesn't have to hardcode the mapping and
    so we can extend the table later (e.g., parks → outdoor)."""
    for t in types:
        bucket = _GOOGLE_TYPE_TO_VENUE.get(t)
        if bucket is not None:
            return bucket
    return "restaurant"  # fallback — we only call this on results from the food query
```

In `PlaceMatcher.match()`, find the cached-row construction:

```python
        cached = CuratedPlace(
            id=f"gplaces:{chosen.google_place_id}",
            name=chosen.name,
            type="restaurant",
            latitude=chosen.latitude,
            longitude=chosen.longitude,
            radius_m=self._ambiguous_threshold_m,
            google_place_id=chosen.google_place_id,
            address=chosen.address,
            notes=None,
        )
```

Replace with:
```python
        venue_bucket = _classify_google_types(chosen.types)
        cached = CuratedPlace(
            id=f"gplaces:{chosen.google_place_id}",
            name=chosen.name,
            type=venue_bucket,
            latitude=chosen.latitude,
            longitude=chosen.longitude,
            # Use the tight ambiguity threshold as the cache row's radius —
            # only a very close future photo should re-match this row, otherwise
            # we'd cluster distinct restaurants on the same block.
            radius_m=self._ambiguous_threshold_m,
            google_place_id=chosen.google_place_id,
            address=chosen.address,
            # Preserve raw Google types for debugging / future re-mapping.
            notes=",".join(chosen.types) if chosen.types else None,
        )
```

And update the return statement for the matched venue:
```python
        return MatchResult(
            place_id=cached.id,
            venue_type=venue_bucket,
            distance_m=chosen_dist,
            source="google_places",
            needs_review=ambiguous,
            notes=notes,
        )
```

### Step 3: Add new tests

Append to `tests/test_places_matcher.py`:

```python
def test_match_classifies_cafe_correctly_when_cached_from_google(tmp_path: Path) -> None:
    """A Google place with type='cafe' should still cache as venue_type=
    'restaurant' (our canonical bucket for food venues) — but the raw
    Google types are preserved in notes for future re-mapping."""
    conn = _conn(tmp_path)
    nearby = NearbyPlace(
        google_place_id="gp-cafe",
        name="Bluebird Cafe",
        latitude=37.762,
        longitude=-122.434,
        address=None,
        types=("cafe", "food", "point_of_interest"),
    )
    google = FakeGoogleClient(results=[nearby])
    m = _matcher(conn, google=google)

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.venue_type == "restaurant"  # canonical bucket
    cached = PlacesRepository(conn).get_by_id("gplaces:gp-cafe")
    assert cached is not None
    assert cached.type == "restaurant"
    assert cached.notes is not None
    assert "cafe" in cached.notes  # raw types preserved
```

Append to `tests/test_places_cli.py`:

```python
def test_add_accepts_outdoor_type(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    rc = run(
        ["add", "--type", "outdoor", "--name", "Park",
         "--lat", "37.7694", "--lng", "-122.4862"],
        conn=conn,
    )
    assert rc == 0
    places = PlacesRepository(conn).list_all()
    assert len(places) == 1
    assert places[0].type == "outdoor"
```

### Step 4: Run tests + lint + typecheck + commit

```bash
uv run pytest tests/test_places_matcher.py tests/test_places_cli.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/places/cli.py src/home_photo_repo/places/matcher.py \
        tests/test_places_matcher.py tests/test_places_cli.py
git commit -m "fix: add outdoor venue type; map Google types to canonical buckets

Plan 3 follow-ups #2 and #3. The cache now stores Google types in notes
for debugging / future re-mapping; the venue_type column uses our
canonical bucket. CLI accepts 'outdoor' for parks/picnic spots."
```

Expected: ~137 tests pass; ruff + mypy clean.

---

## Task 2: FastAPI deps + vendor static assets

### Files
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Create: `src/home_photo_repo/dashboard/__init__.py`
- Create: `src/home_photo_repo/dashboard/static/css/style.css`
- Create: `src/home_photo_repo/dashboard/static/leaflet/leaflet.css`
- Create: `src/home_photo_repo/dashboard/static/leaflet/leaflet.js`
- Create: `src/home_photo_repo/dashboard/static/leaflet/images/marker-icon.png`
- Create: `src/home_photo_repo/dashboard/static/leaflet/images/marker-icon-2x.png`
- Create: `src/home_photo_repo/dashboard/static/leaflet/images/marker-shadow.png`
- Create: `src/home_photo_repo/dashboard/static/htmx.min.js`

### Step 1: Update `pyproject.toml` dependencies

Find:
```toml
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "anthropic>=0.40",
]
```
Change to:
```toml
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "anthropic>=0.40",
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
]
```

### Step 2: Update `requirements.txt` (mirror)

Append after the existing entries:
```
fastapi>=0.115
uvicorn>=0.30
jinja2>=3.1
python-multipart>=0.0.9
```

### Step 3: Create `src/home_photo_repo/dashboard/__init__.py`

```python
"""Localhost dashboard for browsing classified photos and managing places."""
```

### Step 4: Download and commit vendored static assets

Run from repo root:

```bash
mkdir -p src/home_photo_repo/dashboard/static/leaflet/images
mkdir -p src/home_photo_repo/dashboard/static/css

# Leaflet 1.9.4
curl -L -o src/home_photo_repo/dashboard/static/leaflet/leaflet.css \
  https://unpkg.com/leaflet@1.9.4/dist/leaflet.css
curl -L -o src/home_photo_repo/dashboard/static/leaflet/leaflet.js \
  https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
curl -L -o src/home_photo_repo/dashboard/static/leaflet/images/marker-icon.png \
  https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png
curl -L -o src/home_photo_repo/dashboard/static/leaflet/images/marker-icon-2x.png \
  https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png
curl -L -o src/home_photo_repo/dashboard/static/leaflet/images/marker-shadow.png \
  https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png

# HTMX 2.0.4
curl -L -o src/home_photo_repo/dashboard/static/htmx.min.js \
  https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js

# Verify sizes (sanity check — Leaflet js is ~150KB, css ~14KB, htmx ~50KB)
ls -la src/home_photo_repo/dashboard/static/leaflet/ \
       src/home_photo_repo/dashboard/static/
```

### Step 5: Create `src/home_photo_repo/dashboard/static/css/style.css`

```css
:root {
  --bg: #f7f7f8;
  --card: #ffffff;
  --border: #e2e2e6;
  --text: #1f2227;
  --muted: #6b7280;
  --accent: #2563eb;
  --warn: #d97706;
  --ok: #16a34a;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg); color: var(--text); font-size: 14px;
}
header {
  background: var(--card); border-bottom: 1px solid var(--border);
  padding: 12px 24px; display: flex; align-items: center; gap: 24px;
}
header h1 { margin: 0; font-size: 16px; font-weight: 600; }
header nav { display: flex; gap: 16px; }
header nav a { color: var(--muted); text-decoration: none; padding: 4px 8px; border-radius: 4px; }
header nav a:hover, header nav a.active { background: var(--bg); color: var(--text); }
main { max-width: 1280px; margin: 0 auto; padding: 24px; }
h2 { margin: 0 0 16px; font-size: 18px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.photo-card { background: var(--card); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.photo-card img { width: 100%; height: 160px; object-fit: cover; display: block; }
.photo-card .meta { padding: 8px 10px; font-size: 12px; }
.photo-card .meta .dish { font-weight: 600; color: var(--text); }
.photo-card .meta .venue { color: var(--muted); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 500; }
.badge.ok { background: #dcfce7; color: var(--ok); }
.badge.warn { background: #fef3c7; color: var(--warn); }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); }
th { font-weight: 600; background: var(--bg); }
form .row { display: flex; gap: 12px; margin-bottom: 12px; }
input, select, button {
  padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px;
  font-size: 14px; font-family: inherit;
}
button { background: var(--accent); color: white; border: none; cursor: pointer; }
button.danger { background: #dc2626; }
button:hover { opacity: 0.92; }
#map { height: calc(100vh - 130px); border-radius: 8px; }
.pagination { display: flex; gap: 8px; margin-top: 16px; }
.pagination a {
  padding: 6px 12px; border: 1px solid var(--border); border-radius: 4px;
  text-decoration: none; color: var(--text);
}
.pagination a.disabled { color: var(--muted); pointer-events: none; }
```

### Step 6: Verify uv installs new deps + tests still pass

```bash
uv sync --all-extras
uv run pytest -v
```

Expected: same test count as before Task 2 (~137); uv adds new packages.

### Step 7: Commit

```bash
git add pyproject.toml requirements.txt \
        src/home_photo_repo/dashboard/__init__.py \
        src/home_photo_repo/dashboard/static
git commit -m "chore: add FastAPI deps + vendor Leaflet 1.9.4 / HTMX 2.0.4 static assets"
```

---

## Task 3: FastAPI app factory + base template + entrypoint

### Files
- Create: `src/home_photo_repo/dashboard/deps.py`
- Create: `src/home_photo_repo/dashboard/app.py`
- Create: `src/home_photo_repo/dashboard/main.py`
- Create: `src/home_photo_repo/dashboard/templates/base.html`
- Create: `tests/test_dashboard_app.py`

### Step 1: Write failing tests — `tests/test_dashboard_app.py`

```python
"""Tests for the dashboard FastAPI app — health + nav."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def app_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="test-key")
    return TestClient(app)


def test_health_endpoint_returns_ok(app_client: TestClient) -> None:
    response = app_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_returns_404(app_client: TestClient) -> None:
    response = app_client.get("/nope")
    assert response.status_code == 404


def test_static_assets_served(app_client: TestClient) -> None:
    """The /static mount should serve the bundled CSS and JS."""
    response = app_client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_dashboard_app.py -v
```

### Step 3: Create `src/home_photo_repo/dashboard/deps.py`

```python
"""Request-scoped dependencies for dashboard routes.

A fresh sqlite3 connection per request keeps things simple — SQLite is
fast for open/close, and WAL mode (set by `get_connection`) lets the
dashboard read concurrently with the worker writing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from home_photo_repo.db import get_connection
from home_photo_repo.immich_client import ImmichClient


class DashboardDeps:
    """Configuration injected into each route via FastAPI Depends.

    Holds immutable config (paths, URLs); creates per-request connections.
    """

    def __init__(self, *, db_path: Path, immich_base_url: str, immich_api_key: str) -> None:
        self.db_path = db_path
        self.immich_base_url = immich_base_url
        self.immich_api_key = immich_api_key

    def get_db(self) -> Iterator[sqlite3.Connection]:
        conn = get_connection(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_immich(self) -> Iterator[ImmichClient]:
        client = ImmichClient(
            base_url=self.immich_base_url, api_key=self.immich_api_key,
        )
        try:
            yield client
        finally:
            client.close()


__all__ = ["DashboardDeps"]
```

### Step 4: Create `src/home_photo_repo/dashboard/app.py`

```python
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

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Routes are registered in subsequent tasks. We'll add:
    # from home_photo_repo.dashboard.routes import (
    #     proxy, map_view, place, feed, review, places_editor, status,
    # )
    # for module in (proxy, map_view, place, feed, review, places_editor, status):
    #     app.include_router(module.router)

    return app


__all__ = ["create_app"]
```

### Step 5: Create `src/home_photo_repo/dashboard/main.py`

```python
"""Process entrypoint: `python -m home_photo_repo.dashboard.main`."""

from __future__ import annotations

import sys

import uvicorn

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.settings_factory import load_settings


def main() -> None:  # pragma: no cover - process entrypoint
    settings = load_settings()
    host, _, port_str = settings.dashboard_bind.partition(":")
    port = int(port_str) if port_str else 8000
    app = create_app(
        db_path=settings.db_path,
        immich_base_url=str(settings.immich_base_url),
        immich_api_key=settings.immich_api_key.get_secret_value(),
    )
    uvicorn.run(app, host=host or "127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
```

### Step 6: Create `src/home_photo_repo/dashboard/templates/base.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{% block title %}home_photo_repo{% endblock %}</title>
  <link rel="stylesheet" href="/static/css/style.css" />
  <link rel="stylesheet" href="/static/leaflet/leaflet.css" />
  <script src="/static/leaflet/leaflet.js" defer></script>
  <script src="/static/htmx.min.js" defer></script>
</head>
<body>
  <header>
    <h1>home_photo_repo</h1>
    <nav>
      <a href="/" class="{% if active == 'map' %}active{% endif %}">Map</a>
      <a href="/feed" class="{% if active == 'feed' %}active{% endif %}">Feed</a>
      <a href="/review" class="{% if active == 'review' %}active{% endif %}">Review</a>
      <a href="/places" class="{% if active == 'places' %}active{% endif %}">Places</a>
      <a href="/status" class="{% if active == 'status' %}active{% endif %}">Status</a>
    </nav>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

### Step 7: Run + commit

```bash
uv run pytest tests/test_dashboard_app.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/dashboard/deps.py src/home_photo_repo/dashboard/app.py \
        src/home_photo_repo/dashboard/main.py \
        src/home_photo_repo/dashboard/templates/base.html \
        tests/test_dashboard_app.py
git commit -m "feat: FastAPI dashboard app factory + base template + /healthz"
```

Expected: 3 dashboard-app tests pass; full suite ~140.

---

## Task 4: Thumbnail proxy

### Files
- Create: `src/home_photo_repo/dashboard/routes/__init__.py`
- Create: `src/home_photo_repo/dashboard/routes/proxy.py`
- Create: `tests/test_dashboard_proxy.py`
- Modify: `src/home_photo_repo/dashboard/app.py` (register proxy router)

### Step 1: Write failing tests — `tests/test_dashboard_proxy.py`

```python
"""Tests for /proxy/thumbnail/{asset_id}."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="test-key")
    return TestClient(app)


@respx.mock
def test_proxy_streams_thumbnail_bytes(client: TestClient) -> None:
    fake_jpeg = b"\xff\xd8\xff fake jpeg bytes"
    respx.get(
        "http://immich.local:2283/api/assets/asset-1/thumbnail"
    ).mock(return_value=httpx.Response(200, content=fake_jpeg, headers={"content-type": "image/jpeg"}))
    response = client.get("/proxy/thumbnail/asset-1")
    assert response.status_code == 200
    assert response.content == fake_jpeg
    # Cache headers help the browser avoid re-fetching the same thumb.
    assert response.headers.get("cache-control") is not None
    assert "max-age" in response.headers["cache-control"]


@respx.mock
def test_proxy_supports_preview_size(client: TestClient) -> None:
    route = respx.get(
        "http://immich.local:2283/api/assets/asset-1/thumbnail"
    ).mock(return_value=httpx.Response(200, content=b"x"))
    client.get("/proxy/thumbnail/asset-1?size=preview")
    assert route.calls.last.request.url.params["size"] == "preview"


@respx.mock
def test_proxy_404_passes_through(client: TestClient) -> None:
    respx.get(
        "http://immich.local:2283/api/assets/asset-missing/thumbnail"
    ).mock(return_value=httpx.Response(404))
    response = client.get("/proxy/thumbnail/asset-missing")
    assert response.status_code == 404
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_dashboard_proxy.py -v
```

### Step 3: Create `src/home_photo_repo/dashboard/routes/__init__.py`

```python
"""Dashboard route modules — one per page or group."""
```

### Step 4: Create `src/home_photo_repo/dashboard/routes/proxy.py`

```python
"""Thumbnail / preview proxy for browser image loads.

Browsers can't authenticate to Immich's API (different origin, no api-key
header support in <img> tags). This proxy is the single point that holds
the Immich API key and streams bytes back to the page.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response

from home_photo_repo.immich_client import (
    ImmichAssetNotReadyError,
    ImmichClient,
    ImmichClientError,
)

router = APIRouter()


@router.get("/proxy/thumbnail/{asset_id}")
def get_thumbnail(
    asset_id: str,
    request: Request,
    size: Literal["thumbnail", "preview"] = "thumbnail",
) -> Response:
    deps = request.app.state.deps
    client = ImmichClient(
        base_url=deps.immich_base_url, api_key=deps.immich_api_key,
    )
    try:
        try:
            data = client.get_thumbnail(asset_id, size=size)
        except ImmichAssetNotReadyError:
            raise HTTPException(status_code=404, detail="thumbnail not ready") from None
        except ImmichClientError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
    finally:
        client.close()
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
```

### Step 5: Register the router in `app.py`

In `create_app`, after the `app.mount("/static", ...)` line, add (before the `healthz` definition):

```python
    from home_photo_repo.dashboard.routes import proxy
    app.include_router(proxy.router)
```

### Step 6: Run + commit

```bash
uv run pytest tests/test_dashboard_proxy.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/dashboard/routes/__init__.py \
        src/home_photo_repo/dashboard/routes/proxy.py \
        src/home_photo_repo/dashboard/app.py \
        tests/test_dashboard_proxy.py
git commit -m "feat: dashboard /proxy/thumbnail/{id} streams from Immich with cache headers"
```

Expected: 3 new tests pass; full suite ~143.

---

## Task 5: Map view (/)

### Files
- Create: `src/home_photo_repo/dashboard/routes/map_view.py`
- Create: `src/home_photo_repo/dashboard/templates/map.html`
- Create: `tests/test_dashboard_map.py`
- Modify: `src/home_photo_repo/dashboard/app.py` (register router)

### Step 1: Write failing tests — `tests/test_dashboard_map.py`

```python
"""Tests for the / map view."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    # Two food rows with venue resolved, one without venue (should be excluded).
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("curated:home", "Home", "home", 37.7749, -122.4194, 50, now_iso, now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_confidence, stage_a_ran_at,
                dish_name, cuisine, stage_b_ran_at,
                venue_type, place_id, place_match_source, venue_resolved_at,
                review_status)
           VALUES (?, ?, ?, ?, 1, 0.95, ?, ?, ?, ?, ?, ?, ?, ?, 'auto')""",
        ("asset-1", now_iso, 37.7749, -122.4194, now_iso,
         "pizza", "Italian", now_iso, "home", "curated:home", "curated", now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at, dish_name, stage_b_ran_at,
                venue_type, place_id, venue_resolved_at, review_status)
           VALUES (?, ?, ?, ?, 1, ?, 'salad', ?, 'unknown', NULL, ?, 'needs_review')""",
        ("asset-2", now_iso, 37.78, -122.40, now_iso, now_iso, now_iso),
    )
    return db_path, conn


def _client(db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_map_page_renders(seeded: tuple[Path, sqlite3.Connection]) -> None:
    db_path, _ = seeded
    response = _client(db_path).get("/")
    assert response.status_code == 200
    assert "map" in response.text.lower()
    assert 'id="map"' in response.text


def test_map_includes_marker_data_for_food_photos_with_gps(
    seeded: tuple[Path, sqlite3.Connection]
) -> None:
    db_path, _ = seeded
    response = _client(db_path).get("/")
    body = response.text
    # The page embeds markers as JSON for Leaflet to consume
    assert "asset-1" in body  # food + has venue → marker
    assert "asset-2" in body  # food + has GPS but unknown venue → marker
    assert "pizza" in body or "salad" in body


def test_map_excludes_non_food_photos(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at, review_status)
           VALUES (?, ?, 37.7, -122.4, 0, ?, 'auto')""",
        ("non-food", now_iso, now_iso),
    )
    conn.close()
    response = _client(db_path).get("/")
    assert "non-food" not in response.text
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_dashboard_map.py -v
```

### Step 3: Create `src/home_photo_repo/dashboard/routes/map_view.py`

```python
"""GET / — Leaflet map of food photos."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from home_photo_repo.dashboard.deps import DashboardDeps

router = APIRouter()


def _deps(request: Request) -> DashboardDeps:
    return request.app.state.deps  # type: ignore[no-any-return]


@router.get("/", response_class=HTMLResponse)
def map_view(request: Request, deps: DashboardDeps = Depends(_deps)) -> HTMLResponse:
    gen = deps.get_db()
    conn = next(gen)
    try:
        rows = conn.execute(
            """
            SELECT p.immich_asset_id, p.latitude, p.longitude,
                   p.dish_name, p.cuisine, p.venue_type,
                   pl.name AS place_name
              FROM photo_analysis p
         LEFT JOIN places pl ON pl.id = p.place_id
             WHERE p.stage_a_is_food = 1
               AND p.latitude IS NOT NULL
               AND p.longitude IS NOT NULL
          ORDER BY p.taken_at DESC NULLS LAST
             LIMIT 5000
            """
        ).fetchall()
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

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
    return templates.TemplateResponse(
        request,
        "map.html",
        {
            "active": "map",
            "markers_json": json.dumps(markers),
            "count": len(markers),
        },
    )
```

### Step 4: Create `src/home_photo_repo/dashboard/templates/map.html`

```html
{% extends "base.html" %}
{% block title %}Map — home_photo_repo{% endblock %}
{% block content %}
<div class="card" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
  <h2 style="margin: 0;">Map ({{ count }} food photos with GPS)</h2>
</div>
<div id="map"></div>
<script>
  document.addEventListener("DOMContentLoaded", () => {
    const markers = {{ markers_json|safe }};
    const map = L.map("map");
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 19,
    }).addTo(map);

    if (markers.length === 0) {
      map.setView([37.7749, -122.4194], 12);
      return;
    }

    const bounds = L.latLngBounds(markers.map(m => [m.lat, m.lng]));
    map.fitBounds(bounds, {padding: [30, 30]});

    markers.forEach(m => {
      const marker = L.marker([m.lat, m.lng]).addTo(map);
      const placeStr = m.place_name ? `at <a href="/place/${encodeURIComponent(m.id)}#">${m.place_name}</a>` : `(${m.venue_type || 'unknown venue'})`;
      const cuisineStr = m.cuisine ? ` (${m.cuisine})` : "";
      marker.bindPopup(`
        <strong>${m.dish}</strong>${cuisineStr}<br>
        ${placeStr}<br>
        <img src="/proxy/thumbnail/${encodeURIComponent(m.id)}" style="width: 160px; margin-top: 6px;" loading="lazy">
      `);
    });
  });
</script>
{% endblock %}
```

### Step 5: Register router in `app.py`

In `create_app`, add to the import list near the proxy import:

```python
    from home_photo_repo.dashboard.routes import map_view, proxy
    for module in (proxy, map_view):
        app.include_router(module.router)
```

(Remove the previous single-line proxy include.)

### Step 6: Run + commit

```bash
uv run pytest tests/test_dashboard_map.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/dashboard/routes/map_view.py \
        src/home_photo_repo/dashboard/templates/map.html \
        src/home_photo_repo/dashboard/app.py \
        tests/test_dashboard_map.py
git commit -m "feat: dashboard / map view with Leaflet + per-marker popups"
```

Expected: 3 map tests + full suite passes.

---

## Task 6: Place detail (/place/{id})

### Files
- Create: `src/home_photo_repo/dashboard/routes/place.py`
- Create: `src/home_photo_repo/dashboard/templates/place.html`
- Create: `tests/test_dashboard_place.py`
- Modify: `app.py` to include router

### Step 1: Write failing tests — `tests/test_dashboard_place.py`

```python
"""Tests for /place/{id}."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("curated:home", "Home", "home", 37.7749, -122.4194, 50, now_iso, now_iso),
    )
    for i, dish in enumerate(["pizza", "ramen", "salad"]):
        conn.execute(
            """INSERT INTO photo_analysis (
                    immich_asset_id, first_seen_at, latitude, longitude,
                    stage_a_is_food, stage_a_ran_at, dish_name, cuisine,
                    stage_b_ran_at, venue_type, place_id, place_match_source,
                    venue_resolved_at, review_status, taken_at)
               VALUES (?, ?, 37.7749, -122.4194, 1, ?, ?, 'Italian', ?,
                       'home', 'curated:home', 'curated', ?, 'auto', ?)""",
            (f"asset-{i}", now_iso, now_iso, dish, now_iso, now_iso, now_iso),
        )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_place_detail_lists_dishes(client: TestClient) -> None:
    response = client.get("/place/curated:home")
    assert response.status_code == 200
    assert "Home" in response.text
    for dish in ("pizza", "ramen", "salad"):
        assert dish in response.text


def test_place_detail_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/place/curated:does-not-exist")
    assert response.status_code == 404
```

### Step 2: Implement `src/home_photo_repo/dashboard/routes/place.py`

```python
"""GET /place/{id} — venue detail page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from home_photo_repo.dashboard.deps import DashboardDeps

router = APIRouter()


def _deps(request: Request) -> DashboardDeps:
    return request.app.state.deps  # type: ignore[no-any-return]


@router.get("/place/{place_id}", response_class=HTMLResponse)
def place_detail(
    place_id: str,
    request: Request,
    deps: DashboardDeps = Depends(_deps),
) -> HTMLResponse:
    gen = deps.get_db()
    conn = next(gen)
    try:
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
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "place.html",
        {
            "active": None,
            "place": dict(place_row),
            "photos": [dict(r) for r in photo_rows],
        },
    )
```

### Step 3: Create `src/home_photo_repo/dashboard/templates/place.html`

```html
{% extends "base.html" %}
{% block title %}{{ place.name }} — home_photo_repo{% endblock %}
{% block content %}
<div class="card">
  <h2 style="margin: 0 0 4px;">{{ place.name }}</h2>
  <div style="color: var(--muted); font-size: 13px;">
    {{ place.type }} ·
    {{ "%.5f" % place.latitude }}, {{ "%.5f" % place.longitude }} ·
    {{ photos|length }} dishes recorded
  </div>
  {% if place.address %}
    <div style="color: var(--muted); font-size: 13px; margin-top: 4px;">{{ place.address }}</div>
  {% endif %}
</div>

<div class="grid">
  {% for p in photos %}
    <div class="photo-card">
      <img src="/proxy/thumbnail/{{ p.immich_asset_id }}?size=thumbnail" alt="{{ p.dish_name }}" loading="lazy" />
      <div class="meta">
        <div class="dish">{{ p.dish_name }}</div>
        <div class="venue">{{ p.cuisine }}{% if p.taken_at %} · {{ p.taken_at[:10] }}{% endif %}</div>
        {% if p.review_status == 'needs_review' %}
          <span class="badge warn">needs review</span>
        {% endif %}
      </div>
    </div>
  {% else %}
    <div class="card" style="grid-column: 1 / -1;">No dishes recorded here yet.</div>
  {% endfor %}
</div>
{% endblock %}
```

### Step 4: Register + commit

In `app.py`:
```python
    from home_photo_repo.dashboard.routes import map_view, place, proxy
    for module in (proxy, map_view, place):
        app.include_router(module.router)
```

```bash
uv run pytest tests/test_dashboard_place.py -v
git add src/home_photo_repo/dashboard/routes/place.py \
        src/home_photo_repo/dashboard/templates/place.html \
        src/home_photo_repo/dashboard/app.py \
        tests/test_dashboard_place.py
git commit -m "feat: dashboard /place/{id} detail page with dish grid"
```

---

## Task 7: Feed view (/feed)

Chronological grid of recent food photos with simple paging.

### Files
- Create: `src/home_photo_repo/dashboard/routes/feed.py`
- Create: `src/home_photo_repo/dashboard/templates/feed.html`
- Create: `tests/test_dashboard_feed.py`
- Modify: `app.py`

### Step 1: Failing tests — `tests/test_dashboard_feed.py`

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    for i in range(30):
        ts = (base - timedelta(hours=i)).isoformat()
        conn.execute(
            """INSERT INTO photo_analysis (
                    immich_asset_id, first_seen_at, taken_at,
                    stage_a_is_food, stage_a_ran_at,
                    dish_name, cuisine, stage_b_ran_at,
                    venue_type, review_status)
               VALUES (?, ?, ?, 1, ?, ?, 'Italian', ?, 'restaurant', 'auto')""",
            (f"asset-{i:02d}", ts, ts, ts, f"dish {i}", ts),
        )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_feed_default_page_shows_first_24(client: TestClient) -> None:
    response = client.get("/feed")
    assert response.status_code == 200
    # First page should contain dish 0 (newest)
    assert "dish 0" in response.text
    # And not dish 25 (which would be on page 2)
    assert "dish 25" not in response.text


def test_feed_page_2_shows_older_photos(client: TestClient) -> None:
    response = client.get("/feed?page=2")
    assert response.status_code == 200
    assert "dish 25" in response.text
    assert "dish 0" not in response.text


def test_feed_filter_by_venue_type(client: TestClient) -> None:
    response = client.get("/feed?venue_type=home")
    assert response.status_code == 200
    # No photos have venue_type=home in this fixture
    assert "dish 0" not in response.text
```

### Step 2: Implement `src/home_photo_repo/dashboard/routes/feed.py`

```python
"""GET /feed — chronological grid of food photos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from home_photo_repo.dashboard.deps import DashboardDeps

router = APIRouter()
_PAGE_SIZE = 24


def _deps(request: Request) -> DashboardDeps:
    return request.app.state.deps  # type: ignore[no-any-return]


@router.get("/feed", response_class=HTMLResponse)
def feed(
    request: Request,
    page: int = 1,
    venue_type: str | None = None,
    deps: DashboardDeps = Depends(_deps),
) -> HTMLResponse:
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
        try:
            next(gen)
        except StopIteration:
            pass

    templates = request.app.state.templates
    return templates.TemplateResponse(
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
    )
```

### Step 3: Create `src/home_photo_repo/dashboard/templates/feed.html`

```html
{% extends "base.html" %}
{% block title %}Feed — home_photo_repo{% endblock %}
{% block content %}
<div class="card" style="display: flex; justify-content: space-between; align-items: center;">
  <h2 style="margin: 0;">Recent food photos ({{ total }})</h2>
  <form method="get" action="/feed" style="margin: 0;">
    <select name="venue_type" onchange="this.form.submit()">
      <option value="" {% if not venue_filter %}selected{% endif %}>All venues</option>
      <option value="home" {% if venue_filter == 'home' %}selected{% endif %}>Home</option>
      <option value="office" {% if venue_filter == 'office' %}selected{% endif %}>Office</option>
      <option value="restaurant" {% if venue_filter == 'restaurant' %}selected{% endif %}>Restaurant</option>
      <option value="friend_place" {% if venue_filter == 'friend_place' %}selected{% endif %}>Friend's place</option>
      <option value="outdoor" {% if venue_filter == 'outdoor' %}selected{% endif %}>Outdoor</option>
      <option value="unknown" {% if venue_filter == 'unknown' %}selected{% endif %}>Unknown</option>
    </select>
  </form>
</div>

<div class="grid">
  {% for p in photos %}
    <div class="photo-card">
      <img src="/proxy/thumbnail/{{ p.immich_asset_id }}" alt="{{ p.dish_name }}" loading="lazy" />
      <div class="meta">
        <div class="dish">{{ p.dish_name or '(unclassified)' }}</div>
        <div class="venue">
          {{ p.cuisine or '' }}
          {% if p.taken_at %} · {{ p.taken_at[:10] }}{% endif %}
        </div>
        {% if p.place_id %}
          <a href="/place/{{ p.place_id }}" style="font-size: 11px;">view venue</a>
        {% endif %}
        {% if p.review_status == 'needs_review' %}
          <span class="badge warn">review</span>
        {% endif %}
      </div>
    </div>
  {% else %}
    <div class="card" style="grid-column: 1 / -1;">No food photos match.</div>
  {% endfor %}
</div>

<div class="pagination">
  <a href="?page={{ page - 1 }}{% if venue_filter %}&venue_type={{ venue_filter }}{% endif %}"
     class="{% if not has_prev %}disabled{% endif %}">← Previous</a>
  <span style="padding: 6px 12px; color: var(--muted);">Page {{ page }}</span>
  <a href="?page={{ page + 1 }}{% if venue_filter %}&venue_type={{ venue_filter }}{% endif %}"
     class="{% if not has_next %}disabled{% endif %}">Next →</a>
</div>
{% endblock %}
```

### Step 4: Register + commit

```python
    from home_photo_repo.dashboard.routes import feed, map_view, place, proxy
    for module in (proxy, map_view, place, feed):
        app.include_router(module.router)
```

```bash
uv run pytest tests/test_dashboard_feed.py -v
git add src/home_photo_repo/dashboard/routes/feed.py \
        src/home_photo_repo/dashboard/templates/feed.html \
        src/home_photo_repo/dashboard/app.py \
        tests/test_dashboard_feed.py
git commit -m "feat: dashboard /feed chronological grid with paging + venue filter"
```

---

## Task 8: Review queue (/review)

GET lists assets needing review; POST `/review/{asset_id}` updates dish/cuisine/place_id/review_status and returns an updated HTMX partial.

### Files
- Create: `src/home_photo_repo/dashboard/routes/review.py`
- Create: `src/home_photo_repo/dashboard/templates/review.html`
- Create: `src/home_photo_repo/dashboard/templates/_review_row.html`
- Create: `tests/test_dashboard_review.py`
- Modify: `app.py`

### Step 1: Failing tests — `tests/test_dashboard_review.py`

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> tuple[TestClient, Path]:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES ('curated:home', 'Home', 'home', 37.7749, -122.4194, 50, ?, ?)""",
        (now_iso, now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at,
                dish_name, cuisine, stage_b_ran_at, stage_b_confidence,
                review_status)
           VALUES ('asset-needs', ?, 37.78, -122.40, 1, ?, 'mystery dish',
                   'Unknown', ?, 0.3, 'needs_review')""",
        (now_iso, now_iso, now_iso),
    )
    conn.execute(
        """INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, latitude, longitude,
                stage_a_is_food, stage_a_ran_at,
                dish_name, cuisine, stage_b_ran_at, stage_b_confidence,
                review_status)
           VALUES ('asset-ok', ?, 37.78, -122.40, 1, ?, 'pizza',
                   'Italian', ?, 0.95, 'auto')""",
        (now_iso, now_iso, now_iso),
    )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app), db_path


def test_review_lists_only_needs_review_rows(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    response = c.get("/review")
    assert response.status_code == 200
    assert "asset-needs" in response.text
    assert "mystery dish" in response.text
    assert "asset-ok" not in response.text


def test_review_post_updates_dish_and_marks_confirmed(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    response = c.post(
        "/review/asset-needs",
        data={"dish_name": "corrected dish", "cuisine": "Italian",
              "place_id": "curated:home", "decision": "confirm"},
    )
    assert response.status_code == 200
    # HTMX partial response — should not contain the whole page chrome
    assert "<html" not in response.text.lower()
    # Verify DB state
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT dish_name, cuisine, place_id, review_status, reviewed_at "
        "FROM photo_analysis WHERE immich_asset_id = ?", ("asset-needs",),
    ).fetchone()
    assert row["dish_name"] == "corrected dish"
    assert row["cuisine"] == "Italian"
    assert row["place_id"] == "curated:home"
    assert row["review_status"] == "confirmed"
    assert row["reviewed_at"] is not None


def test_review_post_with_decision_corrected_marks_status(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    c.post(
        "/review/asset-needs",
        data={"dish_name": "x", "cuisine": "y", "place_id": "",
              "decision": "correct"},
    )
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT review_status FROM photo_analysis WHERE immich_asset_id = ?",
        ("asset-needs",),
    ).fetchone()
    assert row["review_status"] == "corrected"


def test_review_post_unknown_asset_returns_404(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    response = c.post(
        "/review/asset-missing",
        data={"dish_name": "x", "cuisine": "y", "place_id": "", "decision": "confirm"},
    )
    assert response.status_code == 404
```

### Step 2: Implement `src/home_photo_repo/dashboard/routes/review.py`

```python
"""Review queue: GET /review lists pending; POST /review/{id} updates."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from home_photo_repo.dashboard.deps import DashboardDeps

router = APIRouter()


def _deps(request: Request) -> DashboardDeps:
    return request.app.state.deps  # type: ignore[no-any-return]


@router.get("/review", response_class=HTMLResponse)
def review_list(
    request: Request, deps: DashboardDeps = Depends(_deps)
) -> HTMLResponse:
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
        try:
            next(gen)
        except StopIteration:
            pass

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "active": "review",
            "rows": [dict(r) for r in rows],
            "places": [dict(p) for p in places],
        },
    )


@router.post("/review/{asset_id}", response_class=HTMLResponse)
def review_submit(
    asset_id: str,
    request: Request,
    dish_name: str = Form(""),
    cuisine: str = Form(""),
    place_id: str = Form(""),
    decision: str = Form("confirm"),  # 'confirm' or 'correct'
    deps: DashboardDeps = Depends(_deps),
) -> HTMLResponse:
    new_status = "corrected" if decision == "correct" else "confirmed"
    now = datetime.now(tz=UTC).isoformat()

    gen = deps.get_db()
    conn = next(gen)
    try:
        existing = conn.execute(
            "SELECT 1 FROM photo_analysis WHERE immich_asset_id = ?", (asset_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="asset not found")

        # Look up venue_type for the chosen place (if any)
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
                   place_match_source  = CASE WHEN ? <> '' THEN 'manual' ELSE place_match_source END,
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
        try:
            next(gen)
        except StopIteration:
            pass

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_review_row.html",
        {"row": dict(row), "after_submit": True},
    )
```

### Step 3: Create `src/home_photo_repo/dashboard/templates/review.html`

```html
{% extends "base.html" %}
{% block title %}Review — home_photo_repo{% endblock %}
{% block content %}
<div class="card">
  <h2 style="margin: 0;">Review queue ({{ rows|length }})</h2>
  <p style="color: var(--muted); margin: 6px 0 0;">
    Photos with low classifier confidence, ambiguous venue matches, or missing GPS.
    Confirm to accept the current values; correct to override and mark as manually classified.
  </p>
</div>

{% for row in rows %}
  {% include "_review_row.html" %}
{% else %}
  <div class="card">Nothing to review. 🎉</div>
{% endfor %}
{% endblock %}
```

### Step 4: Create `src/home_photo_repo/dashboard/templates/_review_row.html`

```html
<div class="card" id="review-{{ row.immich_asset_id }}" style="display: grid; grid-template-columns: 200px 1fr; gap: 16px;">
  <img src="/proxy/thumbnail/{{ row.immich_asset_id }}?size=preview" alt="" loading="lazy"
       style="width: 100%; border-radius: 6px;" />
  <div>
    {% if after_submit %}
      <div style="color: var(--ok); font-weight: 600; margin-bottom: 8px;">
        ✓ {{ row.review_status }} — {{ row.dish_name or '(no dish)' }}{% if row.place_name %} @ {{ row.place_name }}{% endif %}
      </div>
    {% else %}
      <div style="color: var(--muted); font-size: 12px;">
        {% if row.taken_at %}{{ row.taken_at[:10] }}{% endif %}
        {% if row.stage_b_confidence is not none %}
          · stage_b confidence: {{ "%.2f" % row.stage_b_confidence }}
        {% endif %}
        {% if row.last_error %} · {{ row.last_error }}{% endif %}
        {% if row.review_notes %} · {{ row.review_notes }}{% endif %}
      </div>
      <form hx-post="/review/{{ row.immich_asset_id }}"
            hx-target="#review-{{ row.immich_asset_id }}"
            hx-swap="outerHTML"
            style="margin-top: 12px;">
        <div class="row">
          <input name="dish_name" value="{{ row.dish_name or '' }}" placeholder="dish name" style="flex: 1;" />
          <input name="cuisine" value="{{ row.cuisine or '' }}" placeholder="cuisine" style="flex: 1;" />
        </div>
        <div class="row">
          <select name="place_id" style="flex: 1;">
            <option value="">— pick a place —</option>
            {% for pl in places %}
              <option value="{{ pl.id }}" {% if pl.id == row.place_id %}selected{% endif %}>
                {{ pl.type }}: {{ pl.name }}
              </option>
            {% endfor %}
          </select>
          <button name="decision" value="confirm" type="submit">Confirm</button>
          <button name="decision" value="correct" type="submit">Correct</button>
        </div>
      </form>
    {% endif %}
  </div>
</div>
```

### Step 5: Register + commit

```python
    from home_photo_repo.dashboard.routes import feed, map_view, place, places_editor, proxy, review, status
```
(places_editor + status are stubs at this point but importing here keeps the include list stable. Actually you should just include `review` now; add the others in subsequent tasks.)

Use this for now:
```python
    from home_photo_repo.dashboard.routes import feed, map_view, place, proxy, review
    for module in (proxy, map_view, place, feed, review):
        app.include_router(module.router)
```

```bash
uv run pytest tests/test_dashboard_review.py -v
git add src/home_photo_repo/dashboard/routes/review.py \
        src/home_photo_repo/dashboard/templates/review.html \
        src/home_photo_repo/dashboard/templates/_review_row.html \
        src/home_photo_repo/dashboard/app.py \
        tests/test_dashboard_review.py
git commit -m "feat: dashboard /review queue with HTMX in-place confirm/correct"
```

---

## Task 9: Places editor (/places)

CRUD UI mirroring the CLI. List + add form + per-row delete.

### Files
- Create: `src/home_photo_repo/dashboard/routes/places_editor.py`
- Create: `src/home_photo_repo/dashboard/templates/places.html`
- Create: `tests/test_dashboard_places.py`
- Modify: `app.py`

### Step 1: Failing tests — `tests/test_dashboard_places.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.places.repository import PlacesRepository

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> tuple[TestClient, Path]:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app), db_path


def test_places_get_lists_places(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    # Pre-seed one place
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES ('curated:x', 'My Place', 'home', 0, 0, 50,
                   '2026-01-01', '2026-01-01')""",
    )
    conn.close()
    response = c.get("/places")
    assert response.status_code == 200
    assert "My Place" in response.text
    assert "Add place" in response.text  # form heading


def test_places_post_add_creates_place(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    response = c.post(
        "/places/add",
        data={"name": "Test Cafe", "type": "restaurant",
              "lat": "37.7749", "lng": "-122.4194", "radius": "75"},
    )
    assert response.status_code in (200, 303)  # redirect or full page
    conn = get_connection(db_path)
    places = PlacesRepository(conn).list_all()
    assert len(places) == 1
    assert places[0].name == "Test Cafe"
    assert places[0].radius_m == 75


def test_places_post_delete_removes_place(client: tuple[TestClient, Path]) -> None:
    c, db_path = client
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO places (id, name, type, latitude, longitude, radius_m,
                              created_at, updated_at)
           VALUES ('curated:del-me', 'Doomed', 'home', 0, 0, 50, '2026-01-01', '2026-01-01')""",
    )
    conn.close()
    response = c.post("/places/delete", data={"id": "curated:del-me"})
    assert response.status_code in (200, 303)
    conn = get_connection(db_path)
    assert PlacesRepository(conn).get_by_id("curated:del-me") is None
```

### Step 2: Implement `src/home_photo_repo/dashboard/routes/places_editor.py`

```python
"""GET /places and POST /places/{add,delete}."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from home_photo_repo.dashboard.deps import DashboardDeps
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace

router = APIRouter()

_VALID_TYPES = ("home", "office", "friend_place", "restaurant", "outdoor", "other")


def _deps(request: Request) -> DashboardDeps:
    return request.app.state.deps  # type: ignore[no-any-return]


@router.get("/places", response_class=HTMLResponse)
def places_list(
    request: Request, deps: DashboardDeps = Depends(_deps)
) -> HTMLResponse:
    gen = deps.get_db()
    conn = next(gen)
    try:
        places = PlacesRepository(conn).list_all()
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    templates = request.app.state.templates
    return templates.TemplateResponse(
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
    )


@router.post("/places/add")
def places_add(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),  # noqa: A002 - matches form field
    lat: float = Form(...),
    lng: float = Form(...),
    radius: int = Form(50),
    notes: str = Form(""),
    deps: DashboardDeps = Depends(_deps),
) -> RedirectResponse:
    if type not in _VALID_TYPES:
        # Re-render the page with an error would be nicer but a redirect is fine.
        return RedirectResponse(url="/places?error=invalid_type", status_code=303)
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
        try:
            next(gen)
        except StopIteration:
            pass
    return RedirectResponse(url="/places", status_code=303)


@router.post("/places/delete")
def places_delete(
    id: str = Form(...),  # noqa: A002
    deps: DashboardDeps = Depends(_deps),
) -> RedirectResponse:
    gen = deps.get_db()
    conn = next(gen)
    try:
        PlacesRepository(conn).delete_by_id(id)
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
    return RedirectResponse(url="/places", status_code=303)
```

### Step 3: Create `src/home_photo_repo/dashboard/templates/places.html`

```html
{% extends "base.html" %}
{% block title %}Places — home_photo_repo{% endblock %}
{% block content %}
<div class="card">
  <h2 style="margin: 0 0 12px;">Add place</h2>
  <form method="post" action="/places/add">
    <div class="row">
      <input name="name" placeholder="Name (e.g. Home)" required style="flex: 2;" />
      <select name="type" required>
        {% for t in valid_types %}
          <option value="{{ t }}">{{ t }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="row">
      <input name="lat" type="number" step="any" placeholder="Latitude" required style="flex: 1;" />
      <input name="lng" type="number" step="any" placeholder="Longitude" required style="flex: 1;" />
      <input name="radius" type="number" value="50" min="5" max="500" style="width: 80px;" />
      <button type="submit">Add</button>
    </div>
  </form>
</div>

<div class="card">
  <h2 style="margin: 0 0 12px;">All places ({{ places|length }})</h2>
  <table>
    <thead>
      <tr><th>Type</th><th>Name</th><th>Lat</th><th>Lng</th><th>Radius</th><th>ID</th><th></th></tr>
    </thead>
    <tbody>
      {% for p in places %}
        <tr>
          <td>{{ p.type }}</td>
          <td>{{ p.name }}</td>
          <td>{{ "%.5f" % p.latitude }}</td>
          <td>{{ "%.5f" % p.longitude }}</td>
          <td>{{ p.radius_m }}m</td>
          <td style="font-family: monospace; font-size: 11px; color: var(--muted);">{{ p.id }}</td>
          <td>
            {% if p.is_curated %}
              <form method="post" action="/places/delete" style="display: inline;"
                    onsubmit="return confirm('Delete {{ p.name }}?')">
                <input type="hidden" name="id" value="{{ p.id }}" />
                <button class="danger" type="submit">Delete</button>
              </form>
            {% else %}
              <span style="color: var(--muted); font-size: 11px;">(cached)</span>
            {% endif %}
          </td>
        </tr>
      {% else %}
        <tr><td colspan="7" style="color: var(--muted);">No places yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

### Step 4: Register + commit

```python
    from home_photo_repo.dashboard.routes import (
        feed, map_view, place, places_editor, proxy, review,
    )
    for module in (proxy, map_view, place, feed, review, places_editor):
        app.include_router(module.router)
```

```bash
uv run pytest tests/test_dashboard_places.py -v
git add src/home_photo_repo/dashboard/routes/places_editor.py \
        src/home_photo_repo/dashboard/templates/places.html \
        src/home_photo_repo/dashboard/app.py \
        tests/test_dashboard_places.py
git commit -m "feat: dashboard /places editor — list, add, delete"
```

---

## Task 10: Status view (/status)

Last 20 worker runs + summary counts.

### Files
- Create: `src/home_photo_repo/dashboard/routes/status.py`
- Create: `src/home_photo_repo/dashboard/templates/status.html`
- Create: `tests/test_dashboard_status.py`
- Modify: `app.py`

### Step 1: Failing tests — `tests/test_dashboard_status.py`

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "app.sqlite"
    conn = get_connection(db_path)
    apply_migrations(conn, MIGRATIONS)
    now_iso = datetime.now(tz=UTC).isoformat()
    # Seed three worker_runs
    for i in range(3):
        conn.execute(
            """INSERT INTO worker_runs (started_at, finished_at, assets_seen,
                                       assets_processed, errors)
               VALUES (?, ?, ?, ?, ?)""",
            (now_iso, now_iso, 10 + i, 9 + i, i),
        )
    # And two photo_analysis rows
    for aid, status in (("a1", "auto"), ("a2", "needs_review")):
        conn.execute(
            """INSERT INTO photo_analysis (immich_asset_id, first_seen_at,
                                          stage_a_is_food, stage_a_ran_at,
                                          review_status)
               VALUES (?, ?, 1, ?, ?)""",
            (aid, now_iso, now_iso, status),
        )
    conn.close()
    app = create_app(db_path=db_path, immich_base_url="http://immich.local:2283",
                     immich_api_key="k")
    return TestClient(app)


def test_status_page_renders_counts(client: TestClient) -> None:
    response = client.get("/status")
    assert response.status_code == 200
    body = response.text
    # Counts in header
    assert "2" in body  # total photos analyzed
    assert "1" in body  # needs_review count
    # worker_runs table shows latest entries
    assert "started_at" in body or "Started" in body or "started" in body
```

### Step 2: Implement `src/home_photo_repo/dashboard/routes/status.py`

```python
"""GET /status — worker run history + summary counts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from home_photo_repo.dashboard.deps import DashboardDeps

router = APIRouter()


def _deps(request: Request) -> DashboardDeps:
    return request.app.state.deps  # type: ignore[no-any-return]


@router.get("/status", response_class=HTMLResponse)
def status_page(
    request: Request, deps: DashboardDeps = Depends(_deps)
) -> HTMLResponse:
    gen = deps.get_db()
    conn = next(gen)
    try:
        counts = conn.execute(
            """
            SELECT
              COUNT(*)                                           AS total,
              SUM(CASE WHEN stage_a_ran_at IS NOT NULL THEN 1 ELSE 0 END) AS classified,
              SUM(CASE WHEN stage_a_is_food = 1 THEN 1 ELSE 0 END)        AS food,
              SUM(CASE WHEN dish_name IS NOT NULL THEN 1 ELSE 0 END)      AS with_dish,
              SUM(CASE WHEN venue_resolved_at IS NOT NULL THEN 1 ELSE 0 END) AS with_venue,
              SUM(CASE WHEN review_status = 'needs_review' THEN 1 ELSE 0 END) AS needs_review,
              SUM(CASE WHEN error_attempts > 0 THEN 1 ELSE 0 END)          AS errored
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
        try:
            next(gen)
        except StopIteration:
            pass

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "status.html",
        {
            "active": "status",
            "counts": dict(counts) if counts else {},
            "cursor": cursor_row["value"] if cursor_row else None,
            "runs": [dict(r) for r in runs],
        },
    )
```

### Step 3: Create `src/home_photo_repo/dashboard/templates/status.html`

```html
{% extends "base.html" %}
{% block title %}Status — home_photo_repo{% endblock %}
{% block content %}
<div class="card">
  <h2 style="margin: 0 0 12px;">Pipeline summary</h2>
  <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 16px;">
    <div><div style="color: var(--muted); font-size: 12px;">Total assets</div><div style="font-size: 24px;">{{ counts.total or 0 }}</div></div>
    <div><div style="color: var(--muted); font-size: 12px;">Classified</div><div style="font-size: 24px;">{{ counts.classified or 0 }}</div></div>
    <div><div style="color: var(--muted); font-size: 12px;">Food</div><div style="font-size: 24px;">{{ counts.food or 0 }}</div></div>
    <div><div style="color: var(--muted); font-size: 12px;">With dish</div><div style="font-size: 24px;">{{ counts.with_dish or 0 }}</div></div>
    <div><div style="color: var(--muted); font-size: 12px;">With venue</div><div style="font-size: 24px;">{{ counts.with_venue or 0 }}</div></div>
    <div><div style="color: var(--muted); font-size: 12px;">Needs review</div><div style="font-size: 24px; color: var(--warn);">{{ counts.needs_review or 0 }}</div></div>
    <div><div style="color: var(--muted); font-size: 12px;">Errors</div><div style="font-size: 24px; color: var(--warn);">{{ counts.errored or 0 }}</div></div>
  </div>
  {% if cursor %}
    <div style="margin-top: 16px; color: var(--muted); font-size: 12px;">
      Cursor: <code>{{ cursor }}</code>
    </div>
  {% endif %}
</div>

<div class="card">
  <h2 style="margin: 0 0 12px;">Recent worker runs</h2>
  <table>
    <thead>
      <tr><th>Started</th><th>Finished</th><th>Seen</th><th>Processed</th><th>Errors</th><th>Notes</th></tr>
    </thead>
    <tbody>
      {% for r in runs %}
        <tr>
          <td>{{ r.started_at }}</td>
          <td>{{ r.finished_at or '(running)' }}</td>
          <td>{{ r.assets_seen }}</td>
          <td>{{ r.assets_processed }}</td>
          <td {% if r.errors %}style="color: var(--warn);"{% endif %}>{{ r.errors }}</td>
          <td style="color: var(--muted); font-size: 12px;">{{ r.notes or '' }}</td>
        </tr>
      {% else %}
        <tr><td colspan="6" style="color: var(--muted);">No runs recorded yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

### Step 4: Register + commit

```python
    from home_photo_repo.dashboard.routes import (
        feed, map_view, place, places_editor, proxy, review, status,
    )
    for module in (proxy, map_view, place, feed, review, places_editor, status):
        app.include_router(module.router)
```

```bash
uv run pytest tests/test_dashboard_status.py -v
git add src/home_photo_repo/dashboard/routes/status.py \
        src/home_photo_repo/dashboard/templates/status.html \
        src/home_photo_repo/dashboard/app.py \
        tests/test_dashboard_status.py
git commit -m "feat: dashboard /status with worker_runs + pipeline summary counts"
```

---

## Task 11: Makefile target + smoke script + final sweep

### Files
- Modify: `Makefile`
- Create: `scripts/smoke_dashboard.py`

### Step 1: Append to `Makefile`

Add `dev-dashboard` to `.PHONY` (find the existing line and append):
```
.PHONY: bootstrap ensure-db dev-worker dev-dashboard test lint typecheck format smoke-immich smoke-llm smoke-places smoke-dashboard
```

At the bottom of the Makefile:

```makefile

dev-dashboard: ensure-db
	$(PYTHON) -m home_photo_repo.dashboard.main

smoke-dashboard:
	$(PYTHON) scripts/smoke_dashboard.py
```

### Step 2: Create `scripts/smoke_dashboard.py`

```python
"""Manual smoke test: hit the dashboard /healthz route locally.

Assumes the dashboard is already running (`make dev-dashboard` in another
terminal). Verifies the process is up and responding."""

from __future__ import annotations

import sys

import httpx

from home_photo_repo.settings_factory import load_settings


def main() -> int:
    settings = load_settings()
    host, _, port_str = settings.dashboard_bind.partition(":")
    host = host or "127.0.0.1"
    port = int(port_str) if port_str else 8000
    url = f"http://{host}:{port}/healthz"
    try:
        r = httpx.get(url, timeout=2.0)
    except httpx.HTTPError as e:
        print(f"ERROR: dashboard not reachable at {url}: {e}", file=sys.stderr)
        return 2
    if r.status_code != 200:
        print(f"ERROR: {url} returned {r.status_code}", file=sys.stderr)
        return 2
    print(f"OK: {url} → {r.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Step 3: Final sweep

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

All green. Expected total: ~170 tests.

### Step 4: Commit

```bash
git add Makefile scripts/smoke_dashboard.py
git commit -m "feat: make dev-dashboard / smoke-dashboard targets"
```

---

## Task 12: README + SETUP.md

### Files
- Modify: `README.md`
- Modify: `docs/SETUP.md`

### Step 1: Update `README.md`

**1a.** Replace the intro paragraph. Find the paragraph starting "This is **Plan 3 (Place Matching)**." and replace with:

```markdown
This is **Plan 4 (Dashboard)**. A localhost-only web UI at
`http://127.0.0.1:8000` shows a map of food photos pinned by venue,
per-place dish galleries, a chronological feed, a review queue for
low-confidence classifications, a curated-places editor, and a worker
status page. Plan 5 will add launchd plists so the worker and dashboard
auto-start at login.
```

**1b.** Update the Roadmap section. Find the Plan 4 line and change to:
```markdown
- **Plan 4** ✅ Done — FastAPI + HTMX + Leaflet dashboard at
  `localhost:8000`.
```

**1c.** Add a `## Dashboard` section between "Curated places & Google Places" and "Project layout":

```markdown
## Dashboard

A read-mostly web UI for browsing what the worker has classified.

### Run it

In a separate terminal from the worker:

```bash
make dev-dashboard
```

Open http://127.0.0.1:8000. The dashboard binds to localhost only — to
expose it on the LAN, add HTTP Basic auth first (out of scope here).

### Pages

- **/** — Leaflet map. Pins for every food photo with GPS, popup shows
  dish + thumbnail + venue link.
- **/place/{id}** — Every dish recorded at this venue, with thumbnails.
- **/feed** — Chronological grid of food photos. Filter by venue type;
  paginated.
- **/review** — Photos the worker flagged as low-confidence or ambiguous.
  Inline form to confirm / correct dish + cuisine + venue (HTMX, no page
  reload).
- **/places** — CRUD for curated places (home / office / etc.). Cached
  Google Places rows are listed but read-only.
- **/status** — Last 20 worker runs + pipeline counts (total, classified,
  food, with-venue, needs-review).

### Verify it's running

```bash
make smoke-dashboard      # hits /healthz, prints OK
```
```

**1d.** Update the project layout's `worker/` section by adding a `dashboard/` subtree before it. The full updated tree should look like:

```
src/home_photo_repo/
├── config.py
├── settings_factory.py
├── db.py
├── immich_client.py
├── immich_types.py
├── llm/
│   └── … (unchanged)
├── places/
│   └── … (unchanged)
├── dashboard/                ← Plan 4
│   ├── app.py                # FastAPI factory
│   ├── deps.py               # request-scoped DB / Immich
│   ├── main.py               # uvicorn entrypoint
│   ├── routes/
│   │   ├── proxy.py          # /proxy/thumbnail/{id}
│   │   ├── map_view.py       # /
│   │   ├── place.py          # /place/{id}
│   │   ├── feed.py           # /feed
│   │   ├── review.py         # /review
│   │   ├── places_editor.py  # /places
│   │   └── status.py         # /status
│   ├── templates/            # Jinja2 + HTMX
│   └── static/               # vendored Leaflet + HTMX + CSS
└── worker/
    └── … (unchanged)
```

### Step 2: Update `docs/SETUP.md`

**2a.** Find `## Verification checklist — Plans 1, 2, 3 complete` and rename to:
```markdown
## Verification checklist — Plans 1–4 complete
```

**2b.** Insert before that heading a new section:

```markdown
## (Plan 4 only) Start the dashboard

In a second terminal (leave the worker running in the first):

```bash
cd ~/Documents/code/home
make dev-dashboard
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Open http://127.0.0.1:8000 in a browser:

- The map should show pins for every food photo with GPS.
- /feed lists recent food photos.
- /places lets you add home/office.
- /review queues low-confidence rows.
- /status shows pipeline counts and recent worker runs.

To leave running long-term: open the URL once a day, or wait for Plan 5
(launchd plists) to auto-start it at login.
```

**2c.** Append to the verification checklist:

```markdown
- [ ] `make dev-dashboard` starts uvicorn on 127.0.0.1:8000
- [ ] `make smoke-dashboard` prints `OK: http://127.0.0.1:8000/healthz → {'status': 'ok'}`
- [ ] Map (`/`) shows pins for food photos
- [ ] Review queue (`/review`) lets you confirm a needs_review item
- [ ] Places editor (`/places`) shows curated places + can add/delete
```

### Step 3: Final test + commit

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add README.md docs/SETUP.md
git commit -m "docs: README + SETUP updated for Plan 4 (dashboard)"
```

---

## Plan 4 acceptance checklist

- [ ] `make test` — all tests pass (target: ~170 tests)
- [ ] `make lint` + `make typecheck` clean
- [ ] `make dev-dashboard` starts on 127.0.0.1:8000
- [ ] `make smoke-dashboard` (with dashboard running) prints OK
- [ ] Each of the 6 view URLs returns 200 with expected content
- [ ] `/review` POST updates the DB and returns an HTMX partial
- [ ] `/places` POST add / delete affect the DB
- [ ] Thumbnail proxy serves bytes with cache headers
- [ ] Worker can still write while dashboard reads (WAL mode)

Once green, Plan 4 is complete. Plan 5 (operations) follows.
