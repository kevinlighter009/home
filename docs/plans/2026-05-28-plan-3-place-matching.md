# Plan 3 — Place Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After Stage B classifies a food photo, resolve the photo's GPS to a specific venue — first checking curated personal places (home/office/friend_place/restaurant), then falling back to the Google Places API for unknown locations. Results land in `photo_analysis.venue_type` / `place_id`.

**Architecture:** A `PlacesRepository` over the existing `places` table provides nearest-within-radius lookup using haversine distance. A `GooglePlacesClient` wraps the New Places API's `:searchNearby` endpoint. A `PlaceMatcher` orchestrates: try local first (cheap, instant, no API call); if no hit, query Google Places (one API call per novel location, the result is cached as a new `places` row so subsequent photos at the same venue resolve locally). Ambiguous matches (multiple candidates within 50m of each other) flag the asset for review. A CLI tool lets the user add home/office/friend_place rows. The pipeline runs venue resolution as the final step after Stage B.

**Tech Stack:** Plain `httpx` for Google Places (no new dep). Stdlib `math` for haversine. CLI via `argparse`. No new infrastructure.

**Spec reference:** `docs/specs/2026-05-28-home-photo-repo-design.md` — sections 4.3 (place matching), 5.2 (`places` table, `venue_type`/`place_id`/`place_match_source`/`place_match_distance_m` columns), 10 (thresholds: `PLACE_MATCH_AMBIGUOUS_THRESHOLD_M=50`, `CURATED_PLACE_DEFAULT_RADIUS_M=50`, `GOOGLE_PLACES_SEARCH_RADIUS_M=150`).

**Plan 2 follow-ups bundled in:** items #4 (persist prompt versions in schema) and #9 (`venue_resolved_at` column) from `docs/plans/2026-05-28-plan-2-followups.md` — both addressed by migration `002`.

**Out of scope:**
- Dashboard for browsing places / reviewing matches (Plan 4)
- LLM disambiguation of ambiguous Google Places candidates (deferred — flag for review in Plan 3, add LLM tiebreaker later if needed)
- launchd / operations (Plan 5)

**Definition of done:**
- `make smoke-places` performs one real Google Places lookup near a known GPS and prints the candidate(s).
- `python -m home_photo_repo.places.cli add-home --lat X --lng Y --name "home"` adds a curated home place.
- Food photos taken at curated places get `venue_type` set correctly (e.g., `home`) without any Google API call.
- Food photos taken at unknown restaurant GPS coordinates get matched via Google Places and cached as `gplaces:*` rows.
- Food photos with no GPS, or in locations with no curated/Google match, end up with `venue_type='unknown'` and `review_status='needs_review'`.
- All tests pass with `pytest-socket` blocking real network; `ruff` and `mypy` clean.

---

## File map

| Path | Created in task | Responsibility |
|---|---|---|
| `migrations/002_prompt_versions_and_venue_timestamps.sql` | 1 | Add 3 columns: `stage_a_prompt_version`, `stage_b_prompt_version`, `venue_resolved_at` |
| `src/home_photo_repo/worker/pipeline.py` (modify) | 1 | Persist `STAGE_A_VERSION` / `STAGE_B_VERSION` when writing stage results |
| `tests/test_migration_002.py` | 1 | New migration creates the 3 columns |
| `src/home_photo_repo/places/__init__.py` | 2 | Package marker |
| `src/home_photo_repo/places/haversine.py` | 2 | `haversine_m(lat1, lng1, lat2, lng2) -> float` |
| `tests/test_haversine.py` | 2 | Known-distance checks against published values |
| `src/home_photo_repo/places/types.py` | 3 | `CuratedPlace`, `NearbyPlace`, `MatchResult` dataclasses |
| `src/home_photo_repo/places/repository.py` | 3 | `PlacesRepository`: list, insert, nearby search via haversine |
| `tests/test_places_repository.py` | 3 | CRUD; nearby returns sorted by distance; filters by max_distance |
| `src/home_photo_repo/places/cli.py` | 4 | `python -m home_photo_repo.places.cli {add\|list\|remove}` |
| `tests/test_places_cli.py` | 4 | Each subcommand against a tmp DB |
| `src/home_photo_repo/places/google_places.py` | 5 | `GooglePlacesClient.search_nearby(lat, lng, radius_m) -> list[NearbyPlace]` |
| `tests/test_google_places.py` | 5 | Happy path, no results, 403, malformed JSON; all respx-mocked |
| `tests/fixtures/google_places_searchnearby.json` | 5 | Recorded sample response |
| `src/home_photo_repo/places/matcher.py` | 6 | `PlaceMatcher.match(lat, lng) -> MatchResult` — orchestrates curated → google → unknown |
| `tests/test_places_matcher.py` | 6 | Each of the 5 outcome branches |
| `src/home_photo_repo/worker/pipeline.py` (modify) | 7 | Add venue resolution step after Stage B |
| `tests/test_pipeline_venue.py` | 7 | Pipeline writes `venue_type` / `place_id` correctly per match outcome |
| `src/home_photo_repo/worker/main.py` (modify) | 8 | Build `GooglePlacesClient` + `PlaceMatcher` from Settings; pass through to pipeline |
| `tests/test_worker_main.py` (modify) | 8 | FakeImmich is sufficient; the existing tests stay green |
| `scripts/smoke_places.py` | 9 | One-shot Google Places call for verification |
| `Makefile` (modify) | 9 | Add `smoke-places` target |
| `README.md` (modify) | 10 | Plan 3 status, curated places workflow, Google Places setup |

---

## Conventions

- Repo root: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home`.
- TDD: tests first, fail, implement, pass, commit. Per-task commit.
- `from __future__ import annotations` at the top of every new `.py` file.
- Place id convention: `curated:<uuid4>` for user-added; `gplaces:<google_place_id>` for cached Google results.
- All datetimes use `UTC` (Python 3.12 `datetime.UTC` constant).

---

## Task 1: Plan 2 follow-ups — migration 002 + prompt-version persistence

Bundle items #4 (persist prompt versions) and #9 (`venue_resolved_at`) from `docs/plans/2026-05-28-plan-2-followups.md` into one migration + pipeline update.

**Files:**
- Create: `migrations/002_prompt_versions_and_venue_timestamps.sql`
- Create: `tests/test_migration_002.py`
- Modify: `src/home_photo_repo/worker/pipeline.py` — write versions in `_record_stage_a_result` / `_record_stage_b_result`

### Step 1: Write the failing test — `tests/test_migration_002.py`

```python
"""Verify migrations/002 adds prompt-version columns and venue_resolved_at."""

from __future__ import annotations

from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _column_names(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_migration_002_adds_prompt_version_columns(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    cols = _column_names(conn, "photo_analysis")
    assert "stage_a_prompt_version" in cols
    assert "stage_b_prompt_version" in cols
    assert "venue_resolved_at" in cols


def test_migration_002_columns_are_nullable(tmp_path: Path) -> None:
    """The new columns must be nullable so existing rows aren't broken."""
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    # Insert a minimal row without the new columns; should succeed.
    conn.execute(
        "INSERT INTO photo_analysis (immich_asset_id, first_seen_at) VALUES (?, ?)",
        ("test-asset", "2026-05-28T12:00:00+00:00"),
    )
    row = conn.execute(
        "SELECT stage_a_prompt_version, stage_b_prompt_version, venue_resolved_at "
        "FROM photo_analysis WHERE immich_asset_id = ?",
        ("test-asset",),
    ).fetchone()
    assert row["stage_a_prompt_version"] is None
    assert row["stage_b_prompt_version"] is None
    assert row["venue_resolved_at"] is None
```

### Step 2: Run test, verify it fails

```bash
uv run pytest tests/test_migration_002.py -v
```
Expected: failures — the columns don't exist yet.

### Step 3: Create `migrations/002_prompt_versions_and_venue_timestamps.sql`

```sql
-- 002_prompt_versions_and_venue_timestamps.sql
-- Plan 2 follow-up #4: persist which prompt version produced each Stage A/B
-- result, so future prompt changes don't silently mix incompatible outputs.
-- Plan 2 follow-up #9: record when venue resolution was attempted, so the
-- worker can re-attempt venue matching after curated places change.

ALTER TABLE photo_analysis ADD COLUMN stage_a_prompt_version TEXT;
ALTER TABLE photo_analysis ADD COLUMN stage_b_prompt_version TEXT;
ALTER TABLE photo_analysis ADD COLUMN venue_resolved_at DATETIME;
```

### Step 4: Run tests, verify they pass

```bash
uv run pytest tests/test_migration_002.py -v
```
Expected: 2 passed.

### Step 5: Persist prompt versions in pipeline writes

In `src/home_photo_repo/worker/pipeline.py`, update the imports section to include the versions:

Find:
```python
from home_photo_repo.llm.stage_a import StageAResult, run_stage_a
from home_photo_repo.llm.stage_b import StageBResult, run_stage_b
```

Change to:
```python
from home_photo_repo.llm.prompts import STAGE_A_VERSION, STAGE_B_VERSION
from home_photo_repo.llm.stage_a import StageAResult, run_stage_a
from home_photo_repo.llm.stage_b import StageBResult, run_stage_b
```

Find `_record_stage_a_result` and update its SQL to include `stage_a_prompt_version`:

```python
def _record_stage_a_result(
    conn: sqlite3.Connection,
    asset_id: str,
    result: StageAResult,
    now: datetime,
) -> None:
    conn.execute(
        """
        UPDATE photo_analysis
           SET stage_a_is_food         = ?,
               stage_a_confidence      = ?,
               stage_a_model           = ?,
               stage_a_ran_at          = ?,
               stage_a_prompt_version  = ?,
               last_error              = NULL
         WHERE immich_asset_id = ?
        """,
        (
            1 if result.is_food else 0,
            result.confidence,
            result.model,
            now.isoformat(),
            STAGE_A_VERSION,
            asset_id,
        ),
    )
```

Find `_record_stage_b_result` and similarly include `stage_b_prompt_version`:

```python
def _record_stage_b_result(
    conn: sqlite3.Connection,
    asset_id: str,
    result: StageBResult,
    now: datetime,
    *,
    needs_review: bool,
) -> None:
    review_status = "needs_review" if needs_review else "auto"
    conn.execute(
        """
        UPDATE photo_analysis
           SET dish_name              = ?,
               cuisine                = ?,
               stage_b_confidence     = ?,
               stage_b_model          = ?,
               stage_b_ran_at         = ?,
               stage_b_raw_json       = ?,
               stage_b_prompt_version = ?,
               review_status          = ?,
               last_error             = NULL
         WHERE immich_asset_id = ?
        """,
        (
            result.dish_name,
            result.cuisine,
            result.confidence,
            result.model,
            now.isoformat(),
            result.raw_json,
            STAGE_B_VERSION,
            review_status,
            asset_id,
        ),
    )
```

### Step 6: Run full suite, verify nothing regressed

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
Expected: 98 tests pass (96 prior + 2 new migration_002); mypy + ruff clean.

The existing `test_pipeline_llm.py` tests don't assert on `stage_a_prompt_version` or `stage_b_prompt_version`, so they continue to pass — those columns just get populated additionally.

### Step 7: Commit

```bash
git add migrations/002_prompt_versions_and_venue_timestamps.sql tests/test_migration_002.py src/home_photo_repo/worker/pipeline.py
git commit -m "feat: persist Stage A/B prompt versions + add venue_resolved_at column

Plan 2 follow-ups #4 and #9. Adds three nullable columns to
photo_analysis and updates the pipeline to write the prompt version
constants when recording Stage A/B results. The new venue_resolved_at
column lights up in Plan 3 Task 7."
```

---

## Task 2: Haversine distance helper

Pure stdlib math. Used by the places repository and matcher.

**Files:**
- Create: `src/home_photo_repo/places/__init__.py`
- Create: `src/home_photo_repo/places/haversine.py`
- Create: `tests/test_haversine.py`

### Step 1: Write failing tests — `tests/test_haversine.py`

```python
"""Tests for the great-circle distance helper.

Reference distances:
- SFO (37.6213, -122.3790) to LAX (33.9416, -118.4085): ~543 km
- 0,0 to 0,1 (one degree longitude at equator): ~111.32 km
- Same point: 0
- One block in San Francisco (~80 m): roughly 0.0009 degrees lat
"""

from __future__ import annotations

import pytest

from home_photo_repo.places.haversine import haversine_m


def test_same_point_returns_zero() -> None:
    assert haversine_m(37.7749, -122.4194, 37.7749, -122.4194) == pytest.approx(0.0)


def test_sfo_to_lax_about_543km() -> None:
    d = haversine_m(37.6213, -122.3790, 33.9416, -118.4085)
    # Published distance: 543 km; allow 1% tolerance.
    assert d == pytest.approx(543_000, rel=0.01)


def test_one_degree_longitude_at_equator_about_111km() -> None:
    d = haversine_m(0.0, 0.0, 0.0, 1.0)
    assert d == pytest.approx(111_320, rel=0.001)


def test_one_degree_latitude_about_111km() -> None:
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_320, rel=0.001)


def test_short_distance_san_francisco() -> None:
    # 0.0009 degrees latitude ≈ 100m
    d = haversine_m(37.7749, -122.4194, 37.7758, -122.4194)
    assert d == pytest.approx(100, rel=0.05)


def test_symmetric() -> None:
    a = haversine_m(37.7749, -122.4194, 40.7128, -74.0060)
    b = haversine_m(40.7128, -74.0060, 37.7749, -122.4194)
    assert a == pytest.approx(b)
```

### Step 2: Run tests, verify they fail

```bash
uv run pytest tests/test_haversine.py -v
```
Expected: ModuleNotFoundError.

### Step 3: Implement `src/home_photo_repo/places/__init__.py`

```python
"""Place / venue resolution package — repository, matcher, Google Places client."""
```

### Step 4: Implement `src/home_photo_repo/places/haversine.py`

```python
"""Great-circle distance helper using the haversine formula.

Returns meters between two (lat, lng) points on Earth's surface. Accurate
enough for our use case (matching photos to venues within ~150m); for
sub-meter accuracy you'd want Vincenty or geodesic instead.
"""

from __future__ import annotations

import math

_EARTH_RADIUS_M: float = 6_371_000.0  # mean Earth radius in meters


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in meters between two lat/lng points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _EARTH_RADIUS_M * c


__all__ = ["haversine_m"]
```

### Step 5: Run tests, verify they pass

```bash
uv run pytest tests/test_haversine.py -v
```
Expected: 6 tests pass.

### Step 6: Commit

```bash
git add src/home_photo_repo/places/__init__.py src/home_photo_repo/places/haversine.py tests/test_haversine.py
git commit -m "feat: haversine_m distance helper for great-circle meters between lat/lng"
```

---

## Task 3: Places types + repository

The `places` table already exists (created by `001_initial.sql`). This task adds Python access layers.

**Files:**
- Create: `src/home_photo_repo/places/types.py`
- Create: `src/home_photo_repo/places/repository.py`
- Create: `tests/test_places_repository.py`

### Step 1: Write failing tests — `tests/test_places_repository.py`

```python
"""Tests for PlacesRepository: insert, list, nearby search by radius."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _home() -> CuratedPlace:
    return CuratedPlace(
        id="curated:home-1",
        name="Home",
        type="home",
        latitude=37.7749,
        longitude=-122.4194,
        radius_m=50,
        google_place_id=None,
        address=None,
        notes=None,
    )


def test_insert_and_get_by_id(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    p = _home()
    repo.insert(p)
    found = repo.get_by_id(p.id)
    assert found is not None
    assert found.name == "Home"
    assert found.type == "home"
    assert found.latitude == pytest.approx(37.7749)


def test_get_by_id_returns_none_for_unknown(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    assert repo.get_by_id("curated:nope") is None


def test_list_all_returns_all_places_ordered(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(_home())
    repo.insert(
        CuratedPlace(
            id="curated:office-1",
            name="Office",
            type="office",
            latitude=37.78,
            longitude=-122.40,
            radius_m=75,
            google_place_id=None,
            address=None,
            notes=None,
        )
    )
    all_places = repo.list_all()
    names = sorted(p.name for p in all_places)
    assert names == ["Home", "Office"]


def test_delete_by_id_removes_place(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(_home())
    assert repo.delete_by_id(_home().id) is True
    assert repo.get_by_id(_home().id) is None
    assert repo.delete_by_id(_home().id) is False  # already gone


def test_nearby_returns_places_within_radius_with_distances(tmp_path: Path) -> None:
    """nearby(lat, lng, max_m) returns (place, distance_m) tuples,
    sorted by distance ascending, only places within their own radius_m."""
    repo = PlacesRepository(_conn(tmp_path))
    # Home at 37.7749, -122.4194 with radius 50m
    repo.insert(_home())
    # Office 1km away, radius 75m — should NOT match if we're at home
    repo.insert(
        CuratedPlace(
            id="curated:office-far",
            name="Office",
            type="office",
            latitude=37.7858,  # ~1.2 km north
            longitude=-122.4194,
            radius_m=75,
            google_place_id=None,
            address=None,
            notes=None,
        )
    )
    # A photo taken right at home should match home only
    matches = repo.nearby(37.7749, -122.4194)
    assert len(matches) == 1
    assert matches[0][0].id == "curated:home-1"
    assert matches[0][1] == pytest.approx(0.0, abs=1.0)


def test_nearby_returns_multiple_when_inside_overlapping_radii(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    repo.insert(
        CuratedPlace(
            id="curated:a", name="A", type="restaurant",
            latitude=37.7749, longitude=-122.4194,
            radius_m=200,  # generous
            google_place_id=None, address=None, notes=None,
        )
    )
    repo.insert(
        CuratedPlace(
            id="curated:b", name="B", type="restaurant",
            latitude=37.7752, longitude=-122.4194,  # ~33m north of A
            radius_m=200,
            google_place_id=None, address=None, notes=None,
        )
    )
    # Probe point between them
    matches = repo.nearby(37.7750, -122.4194)
    assert len(matches) == 2
    # Sorted by distance ascending
    assert matches[0][1] <= matches[1][1]


def test_nearby_excludes_places_outside_their_radius(tmp_path: Path) -> None:
    repo = PlacesRepository(_conn(tmp_path))
    # A tight radius (10m) — probe 100m away should NOT match
    repo.insert(
        CuratedPlace(
            id="curated:tight", name="Tight", type="home",
            latitude=37.7749, longitude=-122.4194,
            radius_m=10,
            google_place_id=None, address=None, notes=None,
        )
    )
    matches = repo.nearby(37.7758, -122.4194)  # ~100m away
    assert matches == []
```

### Step 2: Run tests, verify they fail

```bash
uv run pytest tests/test_places_repository.py -v
```
Expected: ModuleNotFoundError.

### Step 3: Implement `src/home_photo_repo/places/types.py`

```python
"""Typed value objects for place data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedPlace:
    """A row from the places table — user-curated or cached from Google Places."""

    id: str  # 'curated:<uuid>' or 'gplaces:<google_place_id>'
    name: str
    type: str  # 'home' | 'office' | 'friend_place' | 'restaurant' | 'other'
    latitude: float
    longitude: float
    radius_m: int
    google_place_id: str | None
    address: str | None
    notes: str | None


@dataclass(frozen=True)
class NearbyPlace:
    """A candidate place returned by the Google Places client (not yet cached)."""

    google_place_id: str
    name: str
    latitude: float
    longitude: float
    address: str | None
    types: tuple[str, ...]  # e.g. ('restaurant', 'food', 'point_of_interest')


@dataclass(frozen=True)
class MatchResult:
    """The outcome of `PlaceMatcher.match()`."""

    place_id: str | None
    venue_type: str  # 'restaurant' | 'home' | 'office' | 'friend_place' | 'outdoor' | 'unknown'
    distance_m: float | None  # distance from photo to matched place's center
    source: str  # 'curated' | 'google_places' | 'unknown'
    needs_review: bool  # ambiguous or unresolved
    notes: str | None = None  # e.g. "ambiguous: 3 candidates within 50m"


__all__ = ["CuratedPlace", "MatchResult", "NearbyPlace"]
```

### Step 4: Implement `src/home_photo_repo/places/repository.py`

```python
"""SQL access layer over the `places` table.

`PlacesRepository` is the only place that knows the table schema. Higher-
level code (matcher, CLI) speaks `CuratedPlace` objects.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from home_photo_repo.places.haversine import haversine_m
from home_photo_repo.places.types import CuratedPlace


class PlacesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, place: CuratedPlace) -> None:
        now = datetime.now(tz=UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO places (
                id, name, type, latitude, longitude, radius_m,
                google_place_id, address, created_at, updated_at, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                place.id,
                place.name,
                place.type,
                place.latitude,
                place.longitude,
                place.radius_m,
                place.google_place_id,
                place.address,
                now,
                now,
                place.notes,
            ),
        )

    def get_by_id(self, place_id: str) -> CuratedPlace | None:
        row = self._conn.execute(
            """
            SELECT id, name, type, latitude, longitude, radius_m,
                   google_place_id, address, notes
              FROM places WHERE id = ?
            """,
            (place_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_place(row)

    def list_all(self) -> list[CuratedPlace]:
        rows = self._conn.execute(
            """
            SELECT id, name, type, latitude, longitude, radius_m,
                   google_place_id, address, notes
              FROM places
          ORDER BY name
            """
        ).fetchall()
        return [_row_to_place(r) for r in rows]

    def delete_by_id(self, place_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM places WHERE id = ?", (place_id,))
        return cur.rowcount > 0

    def nearby(
        self, latitude: float, longitude: float
    ) -> list[tuple[CuratedPlace, float]]:
        """Return places whose `radius_m` covers the given lat/lng.

        Each result is a (place, distance_m) tuple, sorted by distance asc.
        Implementation: load all places (small table; typically <100 rows for
        a personal use case), compute distance, filter by each row's own
        radius_m. SQL-based distance approximation isn't worth the
        complexity at this scale.
        """
        all_places = self.list_all()
        candidates: list[tuple[CuratedPlace, float]] = []
        for place in all_places:
            d = haversine_m(latitude, longitude, place.latitude, place.longitude)
            if d <= place.radius_m:
                candidates.append((place, d))
        candidates.sort(key=lambda pair: pair[1])
        return candidates


def _row_to_place(row: sqlite3.Row) -> CuratedPlace:
    return CuratedPlace(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        radius_m=row["radius_m"],
        google_place_id=row["google_place_id"],
        address=row["address"],
        notes=row["notes"],
    )


__all__ = ["PlacesRepository"]
```

### Step 5: Run tests, verify they pass

```bash
uv run pytest tests/test_places_repository.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 7 tests pass; mypy + ruff clean.

### Step 6: Commit

```bash
git add src/home_photo_repo/places/types.py src/home_photo_repo/places/repository.py tests/test_places_repository.py
git commit -m "feat: PlacesRepository with insert/list/delete/nearby (haversine filter)"
```

---

## Task 4: Curated places CLI

`python -m home_photo_repo.places.cli ...` lets the user add their home/office/friends without hand-editing SQL. Three subcommands: `add`, `list`, `remove`.

**Files:**
- Create: `src/home_photo_repo/places/cli.py`
- Create: `tests/test_places_cli.py`

### Step 1: Write failing tests — `tests/test_places_cli.py`

```python
"""Tests for the places CLI. We import main() and pass argv directly."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.places.cli import run
from home_photo_repo.places.repository import PlacesRepository

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def test_add_creates_curated_place(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    conn = _conn(tmp_path)
    rc = run(
        ["add", "--type", "home", "--name", "My House",
         "--lat", "37.7749", "--lng", "-122.4194", "--radius", "60"],
        conn=conn,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "added" in out.lower() or "ok" in out.lower()
    places = PlacesRepository(conn).list_all()
    assert len(places) == 1
    p = places[0]
    assert p.name == "My House"
    assert p.type == "home"
    assert p.radius_m == 60
    assert p.id.startswith("curated:")


def test_add_uses_default_radius(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    run(
        ["add", "--type", "office", "--name", "Work",
         "--lat", "37.78", "--lng", "-122.40"],
        conn=conn,
    )
    places = PlacesRepository(conn).list_all()
    assert places[0].radius_m == 50  # default


def test_add_rejects_invalid_type(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    with pytest.raises(SystemExit):
        run(
            ["add", "--type", "spaceship", "--name", "X",
             "--lat", "0", "--lng", "0"],
            conn=conn,
        )


def test_list_prints_places_in_table(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    conn = _conn(tmp_path)
    run(
        ["add", "--type", "home", "--name", "Home",
         "--lat", "37.7749", "--lng", "-122.4194"],
        conn=conn,
    )
    run(
        ["add", "--type", "office", "--name", "Office",
         "--lat", "37.78", "--lng", "-122.40"],
        conn=conn,
    )
    capsys.readouterr()  # clear add output
    rc = run(["list"], conn=conn)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Home" in out
    assert "Office" in out
    assert "37.7749" in out or "37.7749000" in out


def test_remove_deletes_place(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    conn = _conn(tmp_path)
    run(
        ["add", "--type", "home", "--name", "Tmp",
         "--lat", "0", "--lng", "0"],
        conn=conn,
    )
    place_id = PlacesRepository(conn).list_all()[0].id
    capsys.readouterr()
    rc = run(["remove", "--id", place_id], conn=conn)
    assert rc == 0
    assert PlacesRepository(conn).list_all() == []


def test_remove_unknown_id_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    conn = _conn(tmp_path)
    rc = run(["remove", "--id", "curated:does-not-exist"], conn=conn)
    assert rc != 0
```

### Step 2: Run tests, verify they fail

```bash
uv run pytest tests/test_places_cli.py -v
```

### Step 3: Implement `src/home_photo_repo/places/cli.py`

```python
"""Curated places CLI.

Usage:
    python -m home_photo_repo.places.cli add --type home --name "Home" \
        --lat 37.7749 --lng -122.4194 [--radius 50] [--notes "..."]
    python -m home_photo_repo.places.cli list
    python -m home_photo_repo.places.cli remove --id curated:<uuid>
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import uuid
from collections.abc import Sequence

from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace

_VALID_TYPES = ("home", "office", "friend_place", "restaurant", "other")
_DEFAULT_RADIUS_M = 50


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="home_photo_repo.places.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Add a curated place")
    add.add_argument("--type", required=True, choices=_VALID_TYPES)
    add.add_argument("--name", required=True)
    add.add_argument("--lat", required=True, type=float)
    add.add_argument("--lng", required=True, type=float)
    add.add_argument("--radius", type=int, default=_DEFAULT_RADIUS_M,
                     help=f"Match radius in meters (default {_DEFAULT_RADIUS_M})")
    add.add_argument("--address", default=None)
    add.add_argument("--notes", default=None)

    sub.add_parser("list", help="List all curated places")

    rm = sub.add_parser("remove", help="Remove a place by id")
    rm.add_argument("--id", required=True)

    return parser


def run(argv: Sequence[str], *, conn: sqlite3.Connection) -> int:
    args = _build_parser().parse_args(argv)
    repo = PlacesRepository(conn)
    if args.command == "add":
        return _cmd_add(args, repo)
    if args.command == "list":
        return _cmd_list(repo)
    if args.command == "remove":
        return _cmd_remove(args, repo)
    return 2


def _cmd_add(args: argparse.Namespace, repo: PlacesRepository) -> int:
    place = CuratedPlace(
        id=f"curated:{uuid.uuid4()}",
        name=args.name,
        type=args.type,
        latitude=args.lat,
        longitude=args.lng,
        radius_m=args.radius,
        google_place_id=None,
        address=args.address,
        notes=args.notes,
    )
    repo.insert(place)
    print(f"added {place.id} ({place.type}: {place.name})")
    return 0


def _cmd_list(repo: PlacesRepository) -> int:
    places = repo.list_all()
    if not places:
        print("(no places)")
        return 0
    print(f"{'TYPE':<14} {'NAME':<24} {'LAT':<11} {'LNG':<12} {'RADIUS':<8} ID")
    for p in places:
        print(
            f"{p.type:<14} {p.name:<24} {p.latitude:<11.6f} {p.longitude:<12.6f} "
            f"{p.radius_m:<8} {p.id}"
        )
    return 0


def _cmd_remove(args: argparse.Namespace, repo: PlacesRepository) -> int:
    if repo.delete_by_id(args.id):
        print(f"removed {args.id}")
        return 0
    print(f"no place with id {args.id!r}", file=sys.stderr)
    return 1


def main() -> None:  # pragma: no cover - process entrypoint
    from home_photo_repo.db import apply_migrations, get_connection
    from home_photo_repo.settings_factory import load_settings

    settings = load_settings()
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    conn = get_connection(settings.db_path)
    apply_migrations(conn, repo_root / "migrations")
    rc = run(sys.argv[1:], conn=conn)
    sys.exit(rc)


if __name__ == "__main__":  # pragma: no cover
    main()
```

### Step 4: Run tests, verify they pass

```bash
uv run pytest tests/test_places_cli.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 6 tests pass; mypy + ruff clean.

### Step 5: Commit

```bash
git add src/home_photo_repo/places/cli.py tests/test_places_cli.py
git commit -m "feat: places CLI — add/list/remove subcommands"
```

---

## Task 5: Google Places client

Wraps Google's "Places API (New)" — the recommended API as of late 2024. Uses POST `https://places.googleapis.com/v1/places:searchNearby`. Field mask reduces response size (and avoids paying for fields we don't use).

**Files:**
- Create: `tests/fixtures/google_places_searchnearby.json`
- Create: `src/home_photo_repo/places/google_places.py`
- Create: `tests/test_google_places.py`

### Step 1: Create the fixture — `tests/fixtures/google_places_searchnearby.json`

```json
{
  "places": [
    {
      "id": "ChIJrTLr-GyuEmsRBfy61i59si0",
      "displayName": {
        "text": "Mimi's Trattoria",
        "languageCode": "en"
      },
      "formattedAddress": "123 Castro St, San Francisco, CA 94114, USA",
      "types": ["restaurant", "italian_restaurant", "food", "point_of_interest", "establishment"],
      "location": {
        "latitude": 37.7619,
        "longitude": -122.4341
      }
    },
    {
      "id": "ChIJxxxxxxxxxxxxxxxxxxxxxx",
      "displayName": {
        "text": "Joe's Diner",
        "languageCode": "en"
      },
      "formattedAddress": "456 Castro St, San Francisco, CA 94114, USA",
      "types": ["restaurant", "diner", "food", "point_of_interest"],
      "location": {
        "latitude": 37.7620,
        "longitude": -122.4342
      }
    }
  ]
}
```

### Step 2: Write failing tests — `tests/test_google_places.py`

```python
"""Tests for GooglePlacesClient (Places API New)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from home_photo_repo.places.google_places import (
    GooglePlacesClient,
    GooglePlacesError,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client() -> GooglePlacesClient:
    return GooglePlacesClient(api_key="test-key")


@respx.mock
def test_search_nearby_happy_path_returns_typed_places() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json=_load_fixture("google_places_searchnearby.json"))
    )
    results = _client().search_nearby(latitude=37.762, longitude=-122.434, radius_m=150)
    assert len(results) == 2
    p = results[0]
    assert p.google_place_id == "ChIJrTLr-GyuEmsRBfy61i59si0"
    assert p.name == "Mimi's Trattoria"
    assert p.latitude == pytest.approx(37.7619)
    assert p.longitude == pytest.approx(-122.4341)
    assert "restaurant" in p.types


@respx.mock
def test_search_nearby_sends_api_key_and_field_mask_headers() -> None:
    route = respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json={"places": []})
    )
    _client().search_nearby(latitude=0, longitude=0, radius_m=150)
    headers = route.calls.last.request.headers
    assert headers["x-goog-api-key"] == "test-key"
    assert "x-goog-fieldmask" in headers
    # FieldMask must request the fields we depend on
    fm = headers["x-goog-fieldmask"]
    assert "places.id" in fm
    assert "places.displayName" in fm
    assert "places.location" in fm


@respx.mock
def test_search_nearby_sends_correct_body() -> None:
    route = respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json={"places": []})
    )
    _client().search_nearby(latitude=37.762, longitude=-122.434, radius_m=200)
    body = json.loads(route.calls.last.request.content)
    circle = body["locationRestriction"]["circle"]
    assert circle["center"]["latitude"] == pytest.approx(37.762)
    assert circle["center"]["longitude"] == pytest.approx(-122.434)
    assert circle["radius"] == pytest.approx(200)
    # Includes restaurant-like types
    included = set(body["includedTypes"])
    assert "restaurant" in included
    assert "cafe" in included


@respx.mock
def test_search_nearby_no_results_returns_empty_list() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, json={})
    )
    assert _client().search_nearby(latitude=0, longitude=0, radius_m=150) == []


@respx.mock
def test_search_nearby_403_raises() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(
            403, json={"error": {"code": 403, "message": "API key invalid"}}
        )
    )
    with pytest.raises(GooglePlacesError):
        _client().search_nearby(latitude=0, longitude=0, radius_m=150)


@respx.mock
def test_search_nearby_malformed_response_raises() -> None:
    respx.post("https://places.googleapis.com/v1/places:searchNearby").mock(
        return_value=httpx.Response(200, content=b"not json")
    )
    with pytest.raises(GooglePlacesError):
        _client().search_nearby(latitude=0, longitude=0, radius_m=150)
```

### Step 3: Run tests, verify they fail

```bash
uv run pytest tests/test_google_places.py -v
```

### Step 4: Implement `src/home_photo_repo/places/google_places.py`

```python
"""Google Places API (New) — Nearby Search.

Endpoint: POST https://places.googleapis.com/v1/places:searchNearby
Auth: X-Goog-Api-Key header.
Field mask: required header X-Goog-FieldMask listing which fields the response
            should include (also controls billing — smaller mask = cheaper).
"""

from __future__ import annotations

from typing import Any

import httpx

from home_photo_repo.places.types import NearbyPlace

_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"

# Types from Google Places that we treat as food venues.
_FOOD_VENUE_TYPES: tuple[str, ...] = (
    "restaurant",
    "cafe",
    "bakery",
    "bar",
    "meal_delivery",
    "meal_takeaway",
)

# We request only the fields we parse — keeps response small and billing low.
_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.types,"
    "places.location"
)


class GooglePlacesError(RuntimeError):
    """Raised on HTTP error or malformed response from Google Places."""


class GooglePlacesClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GooglePlacesClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def search_nearby(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> list[NearbyPlace]:
        body: dict[str, Any] = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_m,
                }
            },
            "includedTypes": list(_FOOD_VENUE_TYPES),
            "maxResultCount": 10,
            "rankPreference": "DISTANCE",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        try:
            response = self._client.post(_ENDPOINT, headers=headers, json=body)
        except httpx.HTTPError as e:
            raise GooglePlacesError(f"Google Places HTTP error: {e!r}") from e
        if response.status_code >= 400:
            raise GooglePlacesError(
                f"Google Places returned {response.status_code}: "
                f"{response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as e:
            raise GooglePlacesError(f"non-JSON response: {e!r}") from e
        if not isinstance(data, dict):
            raise GooglePlacesError("non-object JSON response")

        places_raw = data.get("places", []) or []
        return [_parse_place(p) for p in places_raw]


def _parse_place(item: dict[str, Any]) -> NearbyPlace:
    try:
        google_id = item["id"]
        display = item["displayName"]
        name = display["text"] if isinstance(display, dict) else str(display)
        location = item["location"]
        lat = float(location["latitude"])
        lng = float(location["longitude"])
    except (KeyError, TypeError, ValueError) as e:
        raise GooglePlacesError(f"malformed Google Places item: {e!r}") from e
    types = tuple(item.get("types", []) or [])
    address = item.get("formattedAddress")
    return NearbyPlace(
        google_place_id=google_id,
        name=name,
        latitude=lat,
        longitude=lng,
        address=address,
        types=types,
    )


__all__ = ["GooglePlacesClient", "GooglePlacesError"]
```

### Step 5: Run tests, verify they pass

```bash
uv run pytest tests/test_google_places.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 6 tests pass; mypy + ruff clean.

### Step 6: Commit

```bash
git add src/home_photo_repo/places/google_places.py tests/test_google_places.py tests/fixtures/google_places_searchnearby.json
git commit -m "feat: GooglePlacesClient using Places API (New) :searchNearby"
```

---

## Task 6: Place matcher orchestration

The matcher implements the spec's resolution order. Importantly, it caches Google Places results into the `places` table so subsequent photos at the same venue resolve locally.

**Files:**
- Create: `src/home_photo_repo/places/matcher.py`
- Create: `tests/test_places_matcher.py`

### Step 1: Write failing tests — `tests/test_places_matcher.py`

```python
"""Tests for PlaceMatcher orchestration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace, NearbyPlace

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


class FakeGoogleClient:
    """Returns canned NearbyPlace lists; records each call."""

    def __init__(self, results: list[NearbyPlace]) -> None:
        self.results = results
        self.calls: list[tuple[float, float, float]] = []

    def search_nearby(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> list[NearbyPlace]:
        self.calls.append((latitude, longitude, radius_m))
        return self.results


def _matcher(
    conn: sqlite3.Connection, google: FakeGoogleClient | None = None,
    ambiguous_threshold_m: int = 50, search_radius_m: int = 150,
) -> PlaceMatcher:
    return PlaceMatcher(
        repo=PlacesRepository(conn),
        google=google,
        ambiguous_threshold_m=ambiguous_threshold_m,
        search_radius_m=search_radius_m,
    )


def _seed_curated(conn: sqlite3.Connection, **fields: object) -> CuratedPlace:
    defaults = dict(
        id="curated:default",
        name="Default",
        type="home",
        latitude=37.7749,
        longitude=-122.4194,
        radius_m=50,
        google_place_id=None,
        address=None,
        notes=None,
    )
    defaults.update(fields)
    place = CuratedPlace(**defaults)  # type: ignore[arg-type]
    PlacesRepository(conn).insert(place)
    return place


def test_match_returns_curated_place_when_within_radius(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    home = _seed_curated(conn, id="curated:home", name="Home", type="home")
    google = FakeGoogleClient(results=[])  # should not be called
    m = _matcher(conn, google=google)

    result = m.match(latitude=37.7749, longitude=-122.4194)

    assert result.place_id == home.id
    assert result.venue_type == "home"
    assert result.source == "curated"
    assert result.needs_review is False
    assert google.calls == []


def test_match_falls_back_to_google_when_no_curated(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    nearby = NearbyPlace(
        google_place_id="gp-1",
        name="Test Restaurant",
        latitude=37.762,
        longitude=-122.434,
        address="123 Test St",
        types=("restaurant",),
    )
    google = FakeGoogleClient(results=[nearby])
    m = _matcher(conn, google=google, search_radius_m=200)

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.place_id == "gplaces:gp-1"
    assert result.venue_type == "restaurant"
    assert result.source == "google_places"
    assert result.needs_review is False
    assert len(google.calls) == 1
    # The Google result must be cached into places for future lookups
    cached = PlacesRepository(conn).get_by_id("gplaces:gp-1")
    assert cached is not None
    assert cached.name == "Test Restaurant"
    assert cached.google_place_id == "gp-1"


def test_match_cached_google_place_resolves_locally_next_time(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    nearby = NearbyPlace(
        google_place_id="gp-1",
        name="Test Restaurant",
        latitude=37.762,
        longitude=-122.434,
        address=None,
        types=("restaurant",),
    )
    google = FakeGoogleClient(results=[nearby])
    m = _matcher(conn, google=google)

    # First call hits Google
    m.match(latitude=37.762, longitude=-122.434)
    # Second call at the same location should NOT hit Google
    google.calls.clear()
    google.results = []  # would return nothing if asked
    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.source == "curated"  # served from the cached row
    assert result.place_id == "gplaces:gp-1"
    assert google.calls == []


def test_match_flags_ambiguous_when_multiple_curated_within_threshold(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_curated(conn, id="curated:a", name="A", latitude=37.7749, longitude=-122.4194, radius_m=200)
    _seed_curated(conn, id="curated:b", name="B", latitude=37.77492, longitude=-122.41944, radius_m=200)
    google = FakeGoogleClient(results=[])
    m = _matcher(conn, google=google, ambiguous_threshold_m=50)

    result = m.match(latitude=37.7749, longitude=-122.4194)

    assert result.needs_review is True
    assert "ambiguous" in (result.notes or "").lower()
    # We still pick the closest as place_id so the dashboard shows something
    assert result.place_id in ("curated:a", "curated:b")


def test_match_returns_unknown_when_no_curated_and_google_empty(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    google = FakeGoogleClient(results=[])
    m = _matcher(conn, google=google)

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.place_id is None
    assert result.venue_type == "unknown"
    assert result.source == "unknown"
    assert result.needs_review is True


def test_match_returns_unknown_when_google_disabled(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    m = _matcher(conn, google=None)  # no Google client provided

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.place_id is None
    assert result.venue_type == "unknown"
    assert result.source == "unknown"
    assert result.needs_review is True


def test_match_handles_google_error_gracefully(tmp_path: Path) -> None:
    """If Google Places fails (network, quota, 5xx), the matcher returns
    unknown + needs_review rather than crashing the pipeline."""
    from home_photo_repo.places.google_places import GooglePlacesError

    conn = _conn(tmp_path)

    class BrokenGoogle:
        def search_nearby(self, *, latitude, longitude, radius_m):
            raise GooglePlacesError("simulated outage")

    m = PlaceMatcher(
        repo=PlacesRepository(conn), google=BrokenGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    result = m.match(latitude=37.762, longitude=-122.434)
    assert result.venue_type == "unknown"
    assert result.needs_review is True
    assert "google" in (result.notes or "").lower()
```

### Step 2: Run tests, verify they fail

```bash
uv run pytest tests/test_places_matcher.py -v
```

### Step 3: Implement `src/home_photo_repo/places/matcher.py`

```python
"""Place resolution orchestration.

Resolution order (per spec §4.3):
  1. Local lookup in the `places` table (covers both user-curated and
     previously-cached Google Places rows).
  2. Google Places Nearby Search (only if step 1 missed and a client is
     configured). Result is cached as a new `places` row keyed
     `gplaces:<id>` so subsequent matches at the same location resolve
     locally.
  3. Else: unknown + needs_review.
"""

from __future__ import annotations

from typing import Protocol

from home_photo_repo.places.haversine import haversine_m
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace, MatchResult, NearbyPlace


class _GoogleLike(Protocol):
    def search_nearby(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> list[NearbyPlace]: ...


_CURATED_VENUE_TYPES = {"home", "office", "friend_place", "restaurant", "other"}


class PlaceMatcher:
    def __init__(
        self,
        *,
        repo: PlacesRepository,
        google: _GoogleLike | None,
        ambiguous_threshold_m: int,
        search_radius_m: int,
    ) -> None:
        self._repo = repo
        self._google = google
        self._ambiguous_threshold_m = ambiguous_threshold_m
        self._search_radius_m = search_radius_m

    def match(self, *, latitude: float, longitude: float) -> MatchResult:
        # Step 1: local
        local = self._repo.nearby(latitude, longitude)
        if local:
            return self._resolve_local(local)

        # Step 2: Google fallback
        if self._google is None:
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                notes="no google_places client configured",
            )
        try:
            candidates = self._google.search_nearby(
                latitude=latitude, longitude=longitude,
                radius_m=self._search_radius_m,
            )
        except Exception as e:  # noqa: BLE001 - any failure → unknown
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                notes=f"google places error: {e!r}",
            )
        if not candidates:
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                notes="no google places candidates",
            )

        # Sort by distance from photo
        ranked = sorted(
            candidates,
            key=lambda c: haversine_m(latitude, longitude, c.latitude, c.longitude),
        )
        chosen = ranked[0]
        chosen_dist = haversine_m(latitude, longitude, chosen.latitude, chosen.longitude)

        # Cache as a places row so next time we resolve locally.
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
        try:
            self._repo.insert(cached)
        except Exception:  # noqa: BLE001 — cache write failure must not fail the match
            pass

        # Ambiguous if a runner-up is within the ambiguity threshold of the winner.
        ambiguous = False
        if len(ranked) > 1:
            second = ranked[1]
            sep = haversine_m(
                chosen.latitude, chosen.longitude,
                second.latitude, second.longitude,
            )
            if sep <= self._ambiguous_threshold_m:
                ambiguous = True
        notes = (
            f"ambiguous: {len(ranked)} google candidates within "
            f"{self._ambiguous_threshold_m}m"
            if ambiguous
            else None
        )
        return MatchResult(
            place_id=cached.id,
            venue_type="restaurant",
            distance_m=chosen_dist,
            source="google_places",
            needs_review=ambiguous,
            notes=notes,
        )

    def _resolve_local(
        self, candidates: list[tuple[CuratedPlace, float]]
    ) -> MatchResult:
        """Resolve a local-table hit. May still be ambiguous (multiple curated
        places within threshold of each other)."""
        winner_place, winner_dist = candidates[0]
        venue_type = (
            winner_place.type if winner_place.type in _CURATED_VENUE_TYPES else "other"
        )
        ambiguous = False
        if len(candidates) > 1:
            second_place, _ = candidates[1]
            sep = haversine_m(
                winner_place.latitude, winner_place.longitude,
                second_place.latitude, second_place.longitude,
            )
            if sep <= self._ambiguous_threshold_m:
                ambiguous = True
        notes = (
            f"ambiguous: {len(candidates)} curated places within "
            f"{self._ambiguous_threshold_m}m"
            if ambiguous
            else None
        )
        return MatchResult(
            place_id=winner_place.id,
            venue_type=venue_type,
            distance_m=winner_dist,
            source="curated",
            needs_review=ambiguous,
            notes=notes,
        )


__all__ = ["PlaceMatcher"]
```

### Step 4: Run tests, verify they pass

```bash
uv run pytest tests/test_places_matcher.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 7 tests pass; mypy + ruff clean.

### Step 5: Commit

```bash
git add src/home_photo_repo/places/matcher.py tests/test_places_matcher.py
git commit -m "feat: PlaceMatcher orchestrates curated → google → unknown resolution"
```

---

## Task 7: Pipeline integration

Run the matcher as the final step after a successful Stage B. Only food photos with GPS are matched; everything else stays at `venue_type=NULL` or gets the unknown treatment.

**Files:**
- Modify: `src/home_photo_repo/worker/pipeline.py`
- Create: `tests/test_pipeline_venue.py`

### Step 1: Update `src/home_photo_repo/worker/pipeline.py`

Add to imports:

```python
from home_photo_repo.places.matcher import PlaceMatcher
```

Update the `process_asset` signature to accept the matcher as an optional kwarg:

Find:
```python
def process_asset(
    conn: sqlite3.Connection,
    asset: ImmichAsset,
    *,
    now: datetime | None = None,
    immich: _ThumbnailFetcher | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = 0.6,
    stage_b_review_threshold: float = 0.7,
) -> ProcessResult:
```

Add `place_matcher: PlaceMatcher | None = None,` as the last parameter:

```python
def process_asset(
    conn: sqlite3.Connection,
    asset: ImmichAsset,
    *,
    now: datetime | None = None,
    immich: _ThumbnailFetcher | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = 0.6,
    stage_b_review_threshold: float = 0.7,
    place_matcher: PlaceMatcher | None = None,
) -> ProcessResult:
```

Update the Stage B success branch — after `_record_stage_b_result`, add venue resolution. Find:

```python
    needs_review = stage_b.confidence < stage_b_review_threshold
    _record_stage_b_result(
        conn, asset.id, stage_b, current_time, needs_review=needs_review
    )
    return ProcessResult.STAGE_A_AND_B_DONE
```

Replace with:

```python
    needs_review = stage_b.confidence < stage_b_review_threshold
    _record_stage_b_result(
        conn, asset.id, stage_b, current_time, needs_review=needs_review
    )

    # Venue resolution (Plan 3). Only runs if a matcher was provided AND the
    # photo has GPS. The matcher itself decides curated vs google vs unknown.
    if place_matcher is not None and asset.latitude is not None and asset.longitude is not None:
        match = place_matcher.match(latitude=asset.latitude, longitude=asset.longitude)
        _record_venue_match(conn, asset.id, match, current_time)

    return ProcessResult.STAGE_A_AND_B_DONE
```

Add a new helper `_record_venue_match` next to the other `_record_*` helpers (at module bottom). Import `MatchResult` at the top:

```python
from home_photo_repo.places.types import MatchResult
```

Add the helper:

```python
def _record_venue_match(
    conn: sqlite3.Connection,
    asset_id: str,
    match: MatchResult,
    now: datetime,
) -> None:
    # If the match itself is ambiguous, escalate review_status; but don't
    # downgrade an already-confirmed/auto status without reason.
    if match.needs_review:
        conn.execute(
            """
            UPDATE photo_analysis
               SET venue_type             = ?,
                   place_id               = ?,
                   place_match_source     = ?,
                   place_match_distance_m = ?,
                   venue_resolved_at      = ?,
                   review_status          = 'needs_review',
                   review_notes           = ?
             WHERE immich_asset_id = ?
            """,
            (
                match.venue_type,
                match.place_id,
                match.source,
                match.distance_m,
                now.isoformat(),
                match.notes,
                asset_id,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE photo_analysis
               SET venue_type             = ?,
                   place_id               = ?,
                   place_match_source     = ?,
                   place_match_distance_m = ?,
                   venue_resolved_at      = ?
             WHERE immich_asset_id = ?
            """,
            (
                match.venue_type,
                match.place_id,
                match.source,
                match.distance_m,
                now.isoformat(),
                asset_id,
            ),
        )
```

### Step 2: Create `tests/test_pipeline_venue.py`

```python
"""Tests for the venue-resolution step appended to the Plan 2 pipeline."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.providers.base import ProviderResult
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace
from home_photo_repo.worker.pipeline import ProcessResult, process_asset

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@dataclass
class FakeImmich:
    bytes_to_return: bytes = b"fake-img"

    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        return self.bytes_to_return


@dataclass
class FakeProvider:
    parsed: dict[str, Any]

    def classify(self, image_bytes, prompt, response_schema, max_tokens=512):
        return ProviderResult(
            parsed=self.parsed, raw=str(self.parsed),
            latency_ms=10, input_tokens=10, output_tokens=10, model="fake:x",
        )


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset(*, lat: float | None = 37.7749, lng: float | None = -122.4194) -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id="asset-1", owner_id="owner-x", original_file_name="x.HEIC",
        updated_at=base, taken_at=base - timedelta(hours=1),
        latitude=lat, longitude=lng, file_created_at=base,
    )


def _matcher(conn: sqlite3.Connection) -> PlaceMatcher:
    return PlaceMatcher(
        repo=PlacesRepository(conn), google=None,
        ambiguous_threshold_m=50, search_radius_m=150,
    )


def _stage_a_food() -> FakeProvider:
    return FakeProvider({"is_food": True, "confidence": 0.95})


def _stage_b_pizza() -> FakeProvider:
    return FakeProvider({"dish_name": "pizza", "cuisine": "Italian", "confidence": 0.9})


def test_pipeline_resolves_curated_home_when_food_photo_at_home_gps(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    PlacesRepository(conn).insert(
        CuratedPlace(
            id="curated:home", name="Home", type="home",
            latitude=37.7749, longitude=-122.4194, radius_m=50,
            google_place_id=None, address=None, notes=None,
        )
    )
    matcher = _matcher(conn)

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    row = conn.execute(
        "SELECT venue_type, place_id, place_match_source, place_match_distance_m, "
        "venue_resolved_at, review_status FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] == "home"
    assert row["place_id"] == "curated:home"
    assert row["place_match_source"] == "curated"
    assert row["place_match_distance_m"] == pytest.approx(0.0, abs=1.0)
    assert row["venue_resolved_at"] is not None
    assert row["review_status"] == "auto"


def test_pipeline_marks_unknown_venue_when_no_curated_and_no_google(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    matcher = _matcher(conn)  # google=None

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    row = conn.execute(
        "SELECT venue_type, place_id, review_status FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] == "unknown"
    assert row["place_id"] is None
    assert row["review_status"] == "needs_review"


def test_pipeline_skips_venue_resolution_when_no_matcher(tmp_path: Path) -> None:
    """Backward compat: no matcher = Plan 2 behavior, venue columns stay NULL."""
    conn = _conn(tmp_path)
    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=None,
    )
    row = conn.execute(
        "SELECT venue_type, venue_resolved_at FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] is None
    assert row["venue_resolved_at"] is None


def test_pipeline_skips_venue_resolution_when_no_gps(tmp_path: Path) -> None:
    """Photo without GPS — even with matcher provided, venue stays NULL."""
    conn = _conn(tmp_path)
    matcher = _matcher(conn)
    asset_no_gps = ImmichAsset(
        id="no-gps", owner_id="o", original_file_name="x.HEIC",
        updated_at=datetime(2026, 5, 28, 0, 0, 0, tzinfo=UTC),
        taken_at=datetime(2026, 5, 28, 0, 0, 0, tzinfo=UTC) - timedelta(hours=1),
        latitude=None, longitude=None, file_created_at=None,
    )
    # Force the asset past readiness so it gets inserted
    later_now = asset_no_gps.updated_at + timedelta(hours=1)

    process_asset(
        conn, asset_no_gps, now=later_now,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    row = conn.execute(
        "SELECT venue_type, venue_resolved_at FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] is None
    assert row["venue_resolved_at"] is None


def test_pipeline_skips_venue_resolution_when_not_food(tmp_path: Path) -> None:
    """Non-food photos never reach venue resolution (it runs after Stage B)."""
    conn = _conn(tmp_path)
    PlacesRepository(conn).insert(
        CuratedPlace(
            id="curated:home", name="Home", type="home",
            latitude=37.7749, longitude=-122.4194, radius_m=50,
            google_place_id=None, address=None, notes=None,
        )
    )
    matcher = _matcher(conn)
    not_food = FakeProvider({"is_food": False, "confidence": 0.95})

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=not_food, stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    assert result is ProcessResult.STAGE_A_NOT_FOOD
    row = conn.execute(
        "SELECT venue_type, venue_resolved_at FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] is None
    assert row["venue_resolved_at"] is None
```

### Step 3: Run tests + lint + typecheck

```bash
uv run pytest tests/test_pipeline_venue.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
Expected: 5 venue tests pass; full suite ~118 tests; mypy + ruff clean.

### Step 4: Commit

```bash
git add src/home_photo_repo/worker/pipeline.py tests/test_pipeline_venue.py
git commit -m "feat: pipeline runs venue resolution after Stage B for food photos with GPS"
```

---

## Task 8: Wire matcher into worker main loop

The main loop builds the matcher from Settings and passes it through `run_once` → `process_asset`. If `GOOGLE_PLACES_API_KEY` is unset or empty, the matcher is built without a Google client (still works for curated-only).

**Files:**
- Modify: `src/home_photo_repo/worker/main.py`
- Modify: `tests/test_worker_main.py` (existing tests stay green)

### Step 1: Update `src/home_photo_repo/worker/main.py`

Add to imports:

```python
from home_photo_repo.places.google_places import GooglePlacesClient
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
```

Add `place_matcher` to `run_once`'s signature (keyword-only, optional, defaults to None):

Find:
```python
def run_once(
    conn: sqlite3.Connection,
    immich: _ImmichLike,
    *,
    batch_size: int,
    now: datetime | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = 0.6,
    stage_b_review_threshold: float = 0.7,
) -> RunSummary:
```

Add `place_matcher: PlaceMatcher | None = None,` at the end:

```python
def run_once(
    conn: sqlite3.Connection,
    immich: _ImmichLike,
    *,
    batch_size: int,
    now: datetime | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = 0.6,
    stage_b_review_threshold: float = 0.7,
    place_matcher: PlaceMatcher | None = None,
) -> RunSummary:
```

In the per-asset call:

Find:
```python
result = process_asset(
    conn,
    asset,
    now=current_time,
    immich=immich,
    stage_a_provider=stage_a_provider,
    stage_b_provider=stage_b_provider,
    rate_limiter=rate_limiter,
    stage_a_food_threshold=stage_a_food_threshold,
    stage_b_review_threshold=stage_b_review_threshold,
)
```

Add the new kwarg:
```python
result = process_asset(
    conn,
    asset,
    now=current_time,
    immich=immich,
    stage_a_provider=stage_a_provider,
    stage_b_provider=stage_b_provider,
    rate_limiter=rate_limiter,
    stage_a_food_threshold=stage_a_food_threshold,
    stage_b_review_threshold=stage_b_review_threshold,
    place_matcher=place_matcher,
)
```

Update `run_forever` to construct the matcher. Find:

```python
    rate_limiter = TokenBucket(
        rate_per_minute=settings.anthropic_rate_limit_per_minute,
        capacity=max(1, settings.anthropic_rate_limit_per_minute // 4),
    )
    log.info(
        "worker starting: poll_interval=%ss batch_size=%s db=%s stage_a=%s stage_b=%s",
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
        stage_a_provider.name,
        stage_b_provider.name,
    )
```

Replace with:

```python
    rate_limiter = TokenBucket(
        rate_per_minute=settings.anthropic_rate_limit_per_minute,
        capacity=max(1, settings.anthropic_rate_limit_per_minute // 4),
    )

    # Place matcher: build Google client only if a real key is configured.
    google_key = settings.google_places_api_key.get_secret_value()
    google_client = (
        GooglePlacesClient(api_key=google_key)
        if google_key and google_key != "replace_me"
        else None
    )
    place_matcher = PlaceMatcher(
        repo=PlacesRepository(conn),
        google=google_client,
        ambiguous_threshold_m=settings.place_match_ambiguous_threshold_m,
        search_radius_m=settings.google_places_search_radius_m,
    )

    log.info(
        "worker starting: poll_interval=%ss batch_size=%s db=%s "
        "stage_a=%s stage_b=%s google_places=%s",
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
        stage_a_provider.name,
        stage_b_provider.name,
        "enabled" if google_client else "disabled (curated places only)",
    )
```

In the `run_forever` loop, pass `place_matcher` through to `run_once`. Find:

```python
            summary = run_once(
                conn, immich,
                batch_size=settings.backfill_batch_size,
                stage_a_provider=stage_a_provider,
                stage_b_provider=stage_b_provider,
                rate_limiter=rate_limiter,
                stage_a_food_threshold=settings.stage_a_food_threshold,
                stage_b_review_threshold=settings.stage_b_confidence_review_threshold,
            )
```

Replace with:

```python
            summary = run_once(
                conn, immich,
                batch_size=settings.backfill_batch_size,
                stage_a_provider=stage_a_provider,
                stage_b_provider=stage_b_provider,
                rate_limiter=rate_limiter,
                stage_a_food_threshold=settings.stage_a_food_threshold,
                stage_b_review_threshold=settings.stage_b_confidence_review_threshold,
                place_matcher=place_matcher,
            )
```

In the `finally` block, also close the Google client if present. Find:

```python
    finally:
        immich.close()
        conn.close()
```

Replace with:

```python
    finally:
        if google_client is not None:
            google_client.close()
        immich.close()
        conn.close()
```

### Step 2: Run full suite

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
Expected: all tests pass; the existing `test_worker_main.py` tests don't pass `place_matcher` (it defaults to None), so they exercise the no-matcher path and stay green.

### Step 3: Commit

```bash
git add src/home_photo_repo/worker/main.py
git commit -m "feat: worker main builds and threads PlaceMatcher through run_once"
```

---

## Task 9: Smoke script + Makefile target

`make smoke-places` performs one real Google Places call to verify the API key and Cloud project are configured correctly. The user supplies a `--lat/--lng` (or it defaults to San Francisco's Ferry Building).

**Files:**
- Create: `scripts/smoke_places.py`
- Modify: `Makefile`

### Step 1: Create `scripts/smoke_places.py`

```python
"""Manual smoke test: run one Google Places Nearby Search to verify the API
key and Cloud project setup.

Run with:
    make smoke-places                    # uses default San Francisco coords
    make smoke-places ARGS='--lat 40.7 --lng -74.0'
"""

from __future__ import annotations

import argparse
import sys

from home_photo_repo.places.google_places import GooglePlacesClient
from home_photo_repo.settings_factory import load_settings

_DEFAULT_LAT = 37.7955  # SF Ferry Building
_DEFAULT_LNG = -122.3937


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=_DEFAULT_LAT)
    parser.add_argument("--lng", type=float, default=_DEFAULT_LNG)
    parser.add_argument("--radius", type=int, default=150)
    args = parser.parse_args()

    settings = load_settings()
    key = settings.google_places_api_key.get_secret_value()
    if not key or key == "replace_me":
        print("ERROR: GOOGLE_PLACES_API_KEY not set in .env", file=sys.stderr)
        return 2

    client = GooglePlacesClient(api_key=key)
    print(f"Searching near ({args.lat}, {args.lng}) within {args.radius}m...")
    results = client.search_nearby(
        latitude=args.lat, longitude=args.lng, radius_m=args.radius
    )
    print(f"Got {len(results)} place(s):")
    for p in results:
        print(f"  - {p.name}  ({p.latitude:.4f}, {p.longitude:.4f})  "
              f"types={','.join(p.types[:3])}")
        if p.address:
            print(f"      {p.address}")
    client.close()
    if results:
        print("\nGoogle Places round-trip succeeded.")
        return 0
    print("\nNo results returned. (Try a denser urban area to verify the key.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Step 2: Append `smoke-places` to `Makefile`

In the `.PHONY` line (top of Makefile), add `smoke-places`:

Find:
```
.PHONY: bootstrap ensure-db dev-worker test lint typecheck format smoke-immich smoke-llm
```

Change to:
```
.PHONY: bootstrap ensure-db dev-worker test lint typecheck format smoke-immich smoke-llm smoke-places
```

At the end of the Makefile, add:

```makefile

smoke-places:
	$(PYTHON) scripts/smoke_places.py $(ARGS)
```

### Step 3: Verify the script imports cleanly

```bash
uv run python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('s', 'scripts/smoke_places.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('ok')
"
```
Expected: `ok`.

### Step 4: Commit

```bash
git add scripts/smoke_places.py Makefile
git commit -m "feat: smoke-places script verifies Google Places API key end-to-end"
```

---

## Task 10: README + final sweep

**Files:**
- Modify: `README.md`
- Modify: `docs/SETUP.md`

### Step 1: Run the full check sweep first

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
All must be green before touching docs.

### Step 2: Update `README.md`

Find the section beginning with `This is **Plan 2 (LLM Pipeline)**.` Replace with:

```markdown
This is **Plan 3 (Place Matching)**. After Stage B identifies dish + cuisine,
the worker resolves the photo's GPS to a venue: either a user-curated
place (home / office / friend's place / a favorite restaurant) or a
restaurant looked up via Google Places. Results land in
`photo_analysis.venue_type` + `place_id`. Plan 4 will surface this in a
dashboard.
```

Find the Roadmap section. The Plan 3 line currently reads:

```markdown
- **Plan 3** — Place matching: curated personal places + Google Places
  fallback for restaurant resolution.
```

Change to:

```markdown
- **Plan 3** ✅ Done — Curated personal places + Google Places fallback
  for venue resolution.
```

Add a new section after the existing `## LLM provider selection`, before `## Project layout`:

```markdown
## Curated places & Google Places

The pipeline resolves each food photo to a venue. Curated places (the
ones you care about — home, office, friends' places, favorite
restaurants) are looked up first from the local `places` table; anything
unmatched falls back to a Google Places Nearby Search.

### Setting up Google Places (optional)

The worker runs fine without a Google Places key — photos at unrecognized
locations just get `venue_type='unknown'` and `review_status='needs_review'`.
To enable the fallback:

1. Open https://console.cloud.google.com → create a new project or pick an
   existing one.
2. Enable the **Places API (New)** under APIs & Services → Library.
3. Create an API key under Credentials. Restrict it to "Places API (New)"
   and, for safety, your home's IP.
4. Put the key in `.env`:
   ```dotenv
   GOOGLE_PLACES_API_KEY=AIza...
   ```
5. Restart the worker (`Ctrl-C` then `make dev-worker`). The log line
   should now say `google_places=enabled`.
6. Verify with `make smoke-places` — it should print real restaurants near
   the default San Francisco Ferry Building coords.

The Google Maps Platform free tier is **$200/month**; at our scale
(~tens of calls/month) this stays comfortably free forever.

### Adding curated places

```bash
# Home, with 60-meter match radius:
uv run python -m home_photo_repo.places.cli add \
    --type home --name "Home" --lat 37.7749 --lng -122.4194 --radius 60

# Your office:
uv run python -m home_photo_repo.places.cli add \
    --type office --name "Work" --lat 37.78 --lng -122.40

# A friend's place:
uv run python -m home_photo_repo.places.cli add \
    --type friend_place --name "Sarah's apartment" \
    --lat 37.765 --lng -122.42 --notes "downstairs neighbor"

# A favorite restaurant (curated entry; bypasses Google Places lookup):
uv run python -m home_photo_repo.places.cli add \
    --type restaurant --name "Mimi's Trattoria" \
    --lat 37.7619 --lng -122.4341 --radius 30

# Review:
uv run python -m home_photo_repo.places.cli list

# Remove:
uv run python -m home_photo_repo.places.cli remove --id curated:<uuid>
```

### Verifying the venue pipeline

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT dish_name, venue_type, place_id, place_match_source, place_match_distance_m \
   FROM photo_analysis \
   WHERE venue_resolved_at IS NOT NULL \
   ORDER BY venue_resolved_at DESC LIMIT 10;"
```
```

Update the Project layout section. Find the existing layout code block and add the `places/` subtree under `src/home_photo_repo/`:

```
src/home_photo_repo/
├── config.py
├── settings_factory.py
├── db.py
├── immich_client.py
├── immich_types.py
├── llm/
│   └── ... (unchanged)
├── places/                  ← Plan 3
│   ├── haversine.py         # great-circle distance
│   ├── types.py             # CuratedPlace, NearbyPlace, MatchResult
│   ├── repository.py        # SQL CRUD + nearby() over places table
│   ├── google_places.py     # Google Places (New) API client
│   ├── matcher.py           # curated → google → unknown orchestrator
│   └── cli.py               # python -m home_photo_repo.places.cli ...
└── worker/
    ├── cursor.py
    ├── main.py              # also builds PlaceMatcher
    └── pipeline.py          # discovered → Stage A → Stage B → venue resolution
```

### Step 3: Append a section to `docs/SETUP.md`

Find the line `## Verification checklist — Plan 1 + Plan 2 complete` and insert before it:

```markdown
## (Plan 3 only) Add curated places + Google Places key

### A. Add your curated places

```bash
uv run python -m home_photo_repo.places.cli add \
    --type home --name "Home" --lat <YOUR-LAT> --lng <YOUR-LNG>

uv run python -m home_photo_repo.places.cli add \
    --type office --name "Work" --lat <LAT> --lng <LNG>

# Add as many friend_place / restaurant entries as you like.
uv run python -m home_photo_repo.places.cli list
```

Finding your home's lat/lng: take a photo of your kitchen with your iPhone
(make sure Camera has Location Services on), upload via Immich, then check:

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT latitude, longitude FROM photo_analysis ORDER BY first_seen_at DESC LIMIT 1;"
```

### B. (Optional) Enable Google Places fallback

1. Google Cloud Console → enable "Places API (New)"
2. Create an API key, restrict to Places API (New)
3. `.env` → `GOOGLE_PLACES_API_KEY=AIza...`
4. `make smoke-places` should print real venues near the default coords.

### C. Restart the worker

```bash
make dev-worker
```

Log line will show `google_places=enabled` (or `disabled (curated only)`).
```

Also update the verification checklist at the bottom of `docs/SETUP.md` to add Plan 3 items:

Find:
```markdown
## Verification checklist — Plan 1 + Plan 2 complete
```

Change to:

```markdown
## Verification checklist — Plans 1, 2, 3 complete
```

Append to the existing checklist:

```markdown
- [ ] `uv run python -m home_photo_repo.places.cli list` shows your curated places
- [ ] (If Google enabled) `make smoke-places` returns real venues
- [ ] Food photo at a curated location populates `venue_type` correctly (home/office/etc.)
- [ ] Food photo at an unknown location either matches via Google Places or shows `venue_type='unknown'`
```

### Step 4: Final test/lint/typecheck

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
All must be green.

### Step 5: Commit

```bash
git add README.md docs/SETUP.md
git commit -m "docs: README + SETUP updated for Plan 3 (curated places + Google Places)"
```

---

## Plan 3 acceptance checklist

- [ ] `make test` — all tests pass (target: ~125 tests)
- [ ] `make lint` clean
- [ ] `make typecheck` clean
- [ ] `make bootstrap` succeeds and applies migration `002`
- [ ] `uv run python -m home_photo_repo.places.cli add ...` creates curated places
- [ ] `uv run python -m home_photo_repo.places.cli list` shows them
- [ ] `make smoke-places` returns real venues (with a real `GOOGLE_PLACES_API_KEY`)
- [ ] Worker startup log shows `google_places=enabled` or `disabled (curated only)`
- [ ] A food photo taken at a curated `home` GPS gets `venue_type='home'`, `place_match_source='curated'`
- [ ] A food photo at an unknown restaurant gets matched via Google and cached as `gplaces:*`
- [ ] A food photo at a truly unknown location gets `venue_type='unknown'`, `review_status='needs_review'`
- [ ] `stage_a_prompt_version` and `stage_b_prompt_version` are populated on rows processed by Plan 3 worker

Once green, Plan 3 is complete. Plan 4 (dashboard) follows.
