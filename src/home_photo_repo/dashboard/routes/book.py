"""Family Food Memory Book — routes for /book/*.

Six views, all read-only against the existing photo_analysis + places tables:

  /book              Overview / landing
  /book/cuisines     Cuisine gallery
  /book/cuisine/{x}  Cuisine detail (paginated)
  /book/timeline     Weekly timeline
  /book/together     Social dining tracker (shared meals)
  /book/stats        Insights & analytics
"""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/book")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FOOD_WHERE = """
    stage_a_is_food = 1
    AND stage_a_ran_at IS NOT NULL
    AND taken_at IS NOT NULL
"""


def _sqlite_week_to_monday(week_str: str) -> date:
    """Convert SQLite '%Y-%W' (Sunday-based, 00-53) to the Monday of that week.

    SQLite's %W counts weeks starting from the first Monday of the year.
    Week 00 contains days before the first Monday; we treat those as Jan 1's week.
    We parse via strptime with %W and a fixed weekday anchor (%w=1 = Monday).
    """
    try:
        year, week = int(week_str[:4]), int(week_str[5:])
        if week == 0:
            # Days before the first Monday — just return Jan 1 of that year
            return date(year, 1, 1)
        # strptime: %Y-%W-%w where %w=1 is Monday
        return datetime.strptime(f"{year}-{week:02d}-1", "%Y-%W-%w").date()
    except Exception:  # noqa: BLE001
        return date.today()


def _week_label(week_str: str) -> str:
    """Convert SQLite '%Y-%W' string to a human-readable range like 'Jun 2–8, 2026'."""
    try:
        monday = _sqlite_week_to_monday(week_str)
        sunday = monday + timedelta(days=6)
        if monday.month == sunday.month:
            return f"{monday.strftime('%b %-d')}–{sunday.day}, {monday.year}"
        return f"{monday.strftime('%b %-d')} – {sunday.strftime('%b %-d')}, {monday.year}"
    except Exception:  # noqa: BLE001
        return week_str


def _compute_streaks(shared_weeks: list[str]) -> dict:
    """Given sorted (desc) list of '%Y-%W' week strings, compute streak info."""
    if not shared_weeks:
        return {"current": 0, "longest": 0}

    # Convert to Monday dates using the same parser as _week_label
    def _monday(w: str) -> date:
        return _sqlite_week_to_monday(w)

    dated = sorted({_monday(w) for w in shared_weeks}, reverse=True)

    # Current streak: consecutive weeks from most-recent going back
    current = 1
    for i in range(1, len(dated)):
        if (dated[i - 1] - dated[i]).days == 7:
            current += 1
        else:
            break

    # Longest streak
    longest = 1
    run = 1
    for i in range(1, len(dated)):
        if (dated[i - 1] - dated[i]).days == 7:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return {"current": current, "longest": longest}


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def book_index(request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    templates = request.app.state.templates

    with deps.db_conn() as conn:
        totals = conn.execute(f"""
            SELECT
              COUNT(*)                                      AS total_meals,
              COUNT(DISTINCT COALESCE(place_id, ''))        AS total_venues,
              COUNT(DISTINCT cuisine)                       AS total_cuisines,
              COUNT(DISTINCT uploader_user_id)              AS total_users,
              MIN(taken_at)                                 AS first_meal,
              MAX(taken_at)                                 AS latest_meal
            FROM photo_analysis
            WHERE {_FOOD_WHERE}
        """).fetchone()

        # Shared meals count
        shared_count = conn.execute(f"""
            SELECT COUNT(*) FROM (
              SELECT DATE(taken_at) AS d, place_id
              FROM photo_analysis
              WHERE {_FOOD_WHERE} AND place_id IS NOT NULL
              GROUP BY d, place_id
              HAVING COUNT(DISTINCT uploader_user_id) >= 2
            )
        """).fetchone()[0]

        # Recent meals (last 7 days)
        recent = conn.execute(f"""
            SELECT pa.immich_asset_id, pa.dish_name, pa.cuisine,
                   pa.taken_at, pa.place_id,
                   p.name AS venue_name,
                   u.display_name AS user_name
            FROM photo_analysis pa
            LEFT JOIN places p ON pa.place_id = p.id
            LEFT JOIN immich_users u ON pa.uploader_user_id = u.user_id
            WHERE {_FOOD_WHERE}
              AND taken_at >= DATE('now', '-7 days')
            ORDER BY taken_at DESC
            LIMIT 12
        """).fetchall()

        # Top cuisines (for quick overview)
        top_cuisines = conn.execute(f"""
            SELECT cuisine, COUNT(*) AS cnt
            FROM photo_analysis
            WHERE {_FOOD_WHERE} AND cuisine IS NOT NULL
            GROUP BY cuisine ORDER BY cnt DESC LIMIT 5
        """).fetchall()

    return cast(HTMLResponse, templates.TemplateResponse(request, "book/index.html", {
        "active": "book",
        "totals": dict(totals) if totals else {},
        "shared_count": shared_count,
        "recent": [dict(r) for r in recent],
        "top_cuisines": [dict(r) for r in top_cuisines],
    }))


# ---------------------------------------------------------------------------
# Cuisines
# ---------------------------------------------------------------------------

@router.get("/cuisines", response_class=HTMLResponse)
def book_cuisines(request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    templates = request.app.state.templates

    with deps.db_conn() as conn:
        cuisines = conn.execute(f"""
            SELECT
              cuisine,
              COUNT(*)                       AS meal_count,
              COUNT(DISTINCT uploader_user_id) AS user_count,
              COUNT(DISTINCT COALESCE(place_id,'')) AS venue_count,
              MIN(taken_at)                  AS first_eaten,
              MAX(taken_at)                  AS last_eaten,
              MIN(immich_asset_id)           AS sample_id
            FROM photo_analysis
            WHERE {_FOOD_WHERE} AND cuisine IS NOT NULL
            GROUP BY cuisine
            ORDER BY meal_count DESC
        """).fetchall()

    return cast(HTMLResponse, templates.TemplateResponse(request, "book/cuisines.html", {
        "active": "book",
        "cuisines": [dict(r) for r in cuisines],
    }))


@router.get("/cuisine/{cuisine_name}", response_class=HTMLResponse)
def book_cuisine_detail(cuisine_name: str, request: Request, page: int = 1) -> HTMLResponse:
    deps = request.app.state.deps
    templates = request.app.state.templates
    per_page = 24
    offset = (page - 1) * per_page

    with deps.db_conn() as conn:
        total = conn.execute(f"""
            SELECT COUNT(*) FROM photo_analysis
            WHERE {_FOOD_WHERE} AND cuisine = ?
        """, (cuisine_name,)).fetchone()[0]

        photos = conn.execute(f"""
            SELECT pa.immich_asset_id, pa.dish_name, pa.taken_at,
                   pa.place_id, p.name AS venue_name,
                   u.display_name AS user_name
            FROM photo_analysis pa
            LEFT JOIN places p ON pa.place_id = p.id
            LEFT JOIN immich_users u ON pa.uploader_user_id = u.user_id
            WHERE {_FOOD_WHERE} AND pa.cuisine = ?
            ORDER BY pa.taken_at DESC
            LIMIT ? OFFSET ?
        """, (cuisine_name, per_page, offset)).fetchall()

        # Stats for this cuisine
        stats = conn.execute(f"""
            SELECT
              COUNT(DISTINCT COALESCE(place_id,'')) AS venues,
              COUNT(DISTINCT uploader_user_id)      AS users,
              MIN(taken_at) AS first, MAX(taken_at) AS last
            FROM photo_analysis
            WHERE {_FOOD_WHERE} AND cuisine = ?
        """, (cuisine_name,)).fetchone()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return cast(HTMLResponse, templates.TemplateResponse(request, "book/cuisine_detail.html", {
        "active": "book",
        "cuisine_name": cuisine_name,
        "photos": [dict(r) for r in photos],
        "stats": dict(stats) if stats else {},
        "page": page,
        "total_pages": total_pages,
        "total": total,
    }))


# ---------------------------------------------------------------------------
# Timeline (weekly)
# ---------------------------------------------------------------------------

@router.get("/timeline", response_class=HTMLResponse)
def book_timeline(request: Request, page: int = 1) -> HTMLResponse:
    deps = request.app.state.deps
    templates = request.app.state.templates
    per_page = 12  # weeks per page

    with deps.db_conn() as conn:
        weeks_raw = conn.execute(f"""
            SELECT
              strftime('%Y-%W', taken_at)              AS week_key,
              COUNT(*)                                 AS meal_count,
              COUNT(DISTINCT uploader_user_id)         AS user_count,
              COUNT(DISTINCT COALESCE(place_id, ''))   AS venue_count,
              GROUP_CONCAT(DISTINCT cuisine)           AS cuisines_raw,
              -- pick one sample photo per week
              MIN(immich_asset_id)                     AS sample_id,
              MIN(taken_at)                            AS week_start_raw
            FROM photo_analysis
            WHERE {_FOOD_WHERE}
            GROUP BY week_key
            ORDER BY week_key DESC
            LIMIT ? OFFSET ?
        """, (per_page, (page - 1) * per_page)).fetchall()

        total_weeks = conn.execute(f"""
            SELECT COUNT(DISTINCT strftime('%Y-%W', taken_at))
            FROM photo_analysis WHERE {_FOOD_WHERE}
        """).fetchone()[0]

        # For each week, fetch its top meals (up to 6 photos)
        weeks = []
        for row in weeks_raw:
            r = dict(row)
            r["label"] = _week_label(r["week_key"])
            r["cuisines"] = sorted(set((r["cuisines_raw"] or "").split(",")))[:5]

            photos = conn.execute(f"""
                SELECT pa.immich_asset_id, pa.dish_name, pa.cuisine,
                       pa.taken_at, p.name AS venue_name,
                       u.display_name AS user_name
                FROM photo_analysis pa
                LEFT JOIN places p ON pa.place_id = p.id
                LEFT JOIN immich_users u ON pa.uploader_user_id = u.user_id
                WHERE {_FOOD_WHERE}
                  AND strftime('%Y-%W', pa.taken_at) = ?
                ORDER BY pa.taken_at DESC
                LIMIT 6
            """, (r["week_key"],)).fetchall()
            r["photos"] = [dict(p) for p in photos]
            weeks.append(r)

    total_pages = max(1, (total_weeks + per_page - 1) // per_page)
    return cast(HTMLResponse, templates.TemplateResponse(request, "book/timeline.html", {
        "active": "book",
        "weeks": weeks,
        "page": page,
        "total_pages": total_pages,
    }))


# ---------------------------------------------------------------------------
# Together (Social Dining Tracker)
# ---------------------------------------------------------------------------

@router.get("/together", response_class=HTMLResponse)
def book_together(request: Request, page: int = 1) -> HTMLResponse:
    deps = request.app.state.deps
    templates = request.app.state.templates
    per_page = 10

    with deps.db_conn() as conn:
        users = conn.execute(
            "SELECT user_id, COALESCE(display_name, username) AS name "
            "FROM immich_users ORDER BY username"
        ).fetchall()

        # Shared meal dates + venues (≥2 distinct uploaders, same place, same day)
        shared_raw = conn.execute(f"""
            SELECT
              DATE(pa.taken_at)                         AS meal_date,
              pa.place_id,
              p.name                                    AS venue_name,
              p.type                                    AS venue_type,
              p.address,
              COUNT(DISTINCT pa.uploader_user_id)       AS user_count,
              COUNT(*)                                  AS photo_count
            FROM photo_analysis pa
            LEFT JOIN places p ON pa.place_id = p.id
            WHERE {_FOOD_WHERE} AND pa.place_id IS NOT NULL
            GROUP BY meal_date, pa.place_id
            HAVING user_count >= 2
            ORDER BY meal_date DESC
            LIMIT ? OFFSET ?
        """, (per_page, (page - 1) * per_page)).fetchall()

        total_shared = conn.execute(f"""
            SELECT COUNT(*) FROM (
              SELECT DATE(taken_at) AS d, place_id
              FROM photo_analysis
              WHERE {_FOOD_WHERE} AND place_id IS NOT NULL
              GROUP BY d, place_id HAVING COUNT(DISTINCT uploader_user_id) >= 2
            )
        """).fetchone()[0]

        # For each shared meal fetch one photo per user
        shared_meals = []
        for row in shared_raw:
            r = dict(row)
            photos = conn.execute(f"""
                SELECT pa.immich_asset_id, pa.dish_name,
                       pa.uploader_user_id,
                       u.display_name AS user_name
                FROM photo_analysis pa
                LEFT JOIN immich_users u ON pa.uploader_user_id = u.user_id
                WHERE {_FOOD_WHERE}
                  AND pa.place_id = ?
                  AND DATE(pa.taken_at) = ?
                ORDER BY pa.uploader_user_id, pa.taken_at
            """, (r["place_id"], r["meal_date"])).fetchall()

            # One photo per user (first of that day)
            seen: set[str] = set()
            user_photos = []
            for p in photos:
                if p["uploader_user_id"] not in seen:
                    user_photos.append(dict(p))
                    seen.add(p["uploader_user_id"])
            r["user_photos"] = user_photos
            shared_meals.append(r)

        # Lifetime stats
        lifetime = conn.execute(f"""
            SELECT
              COUNT(*) AS total_shared,
              COUNT(DISTINCT place_id) AS shared_venues,
              COUNT(DISTINCT DATE(taken_at)) AS shared_days
            FROM (
              SELECT DATE(taken_at) AS d, place_id, taken_at
              FROM photo_analysis
              WHERE {_FOOD_WHERE} AND place_id IS NOT NULL
              GROUP BY d, place_id
              HAVING COUNT(DISTINCT uploader_user_id) >= 2
            )
        """).fetchone()

        top_shared_venues = conn.execute(f"""
            SELECT p.name, p.type, COUNT(*) AS times
            FROM (
              SELECT DATE(pa.taken_at) AS d, pa.place_id
              FROM photo_analysis pa
              WHERE {_FOOD_WHERE} AND pa.place_id IS NOT NULL
              GROUP BY d, pa.place_id
              HAVING COUNT(DISTINCT pa.uploader_user_id) >= 2
            ) sh
            JOIN places p ON sh.place_id = p.id
            GROUP BY sh.place_id
            ORDER BY times DESC LIMIT 5
        """).fetchall()

        # First time together at each venue
        first_times = conn.execute(f"""
            SELECT p.name, p.type,
                   MIN(DATE(pa.taken_at)) AS first_date,
                   COUNT(DISTINCT DATE(pa.taken_at)) AS total_visits
            FROM photo_analysis pa
            JOIN places p ON pa.place_id = p.id
            WHERE {_FOOD_WHERE} AND pa.place_id IS NOT NULL
            GROUP BY pa.place_id
            HAVING COUNT(DISTINCT pa.uploader_user_id) >= 2
            ORDER BY first_date DESC
            LIMIT 10
        """).fetchall()

        # Weeks with shared meals (for streak calculation)
        shared_weeks = [r[0] for r in conn.execute(f"""
            SELECT DISTINCT strftime('%Y-%W', taken_at) AS wk
            FROM photo_analysis
            WHERE {_FOOD_WHERE} AND place_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM photo_analysis b
                WHERE b.place_id = photo_analysis.place_id
                  AND DATE(b.taken_at) = DATE(photo_analysis.taken_at)
                  AND b.uploader_user_id != photo_analysis.uploader_user_id
                  AND b.stage_a_is_food = 1
              )
            ORDER BY wk DESC
        """).fetchall()]

        streaks = _compute_streaks(shared_weeks)

    total_pages = max(1, (total_shared + per_page - 1) // per_page)
    return cast(HTMLResponse, templates.TemplateResponse(request, "book/together.html", {
        "active": "book",
        "users": [dict(u) for u in users],
        "shared_meals": shared_meals,
        "lifetime": dict(lifetime) if lifetime else {},
        "top_shared_venues": [dict(r) for r in top_shared_venues],
        "first_times": [dict(r) for r in first_times],
        "streaks": streaks,
        "page": page,
        "total_pages": total_pages,
        "total_shared": total_shared,
    }))


# ---------------------------------------------------------------------------
# Stats & Insights
# ---------------------------------------------------------------------------

@router.get("/stats", response_class=HTMLResponse)
def book_stats(request: Request) -> HTMLResponse:
    deps = request.app.state.deps
    templates = request.app.state.templates

    with deps.db_conn() as conn:
        top_venues = conn.execute(f"""
            SELECT p.name, p.type,
                   COUNT(*)                           AS total_photos,
                   COUNT(DISTINCT DATE(pa.taken_at))  AS days_visited,
                   MAX(pa.taken_at)                   AS last_visit
            FROM photo_analysis pa
            JOIN places p ON pa.place_id = p.id
            WHERE {_FOOD_WHERE}
            GROUP BY pa.place_id
            ORDER BY total_photos DESC LIMIT 10
        """).fetchall()

        cuisines = conn.execute(f"""
            SELECT cuisine, COUNT(*) AS cnt,
                   COUNT(DISTINCT uploader_user_id) AS users
            FROM photo_analysis
            WHERE {_FOOD_WHERE} AND cuisine IS NOT NULL
            GROUP BY cuisine ORDER BY cnt DESC LIMIT 15
        """).fetchall()

        top_dishes = conn.execute(f"""
            SELECT dish_name, COUNT(*) AS cnt, MAX(taken_at) AS last_eaten
            FROM photo_analysis
            WHERE {_FOOD_WHERE} AND dish_name IS NOT NULL
            GROUP BY LOWER(TRIM(dish_name))
            ORDER BY cnt DESC LIMIT 10
        """).fetchall()

        # Weekly meal counts for the past 16 weeks (sparkline data)
        weekly = conn.execute(f"""
            SELECT strftime('%Y-%W', taken_at) AS wk, COUNT(*) AS cnt
            FROM photo_analysis
            WHERE {_FOOD_WHERE}
              AND taken_at >= DATE('now', '-112 days')
            GROUP BY wk ORDER BY wk
        """).fetchall()

        # Per-user totals
        per_user = conn.execute(f"""
            SELECT COALESCE(u.display_name, u.username) AS name,
                   COUNT(*) AS meals,
                   COUNT(DISTINCT cuisine) AS cuisines,
                   COUNT(DISTINCT COALESCE(pa.place_id,'')) AS venues
            FROM photo_analysis pa
            LEFT JOIN immich_users u ON pa.uploader_user_id = u.user_id
            WHERE {_FOOD_WHERE}
            GROUP BY pa.uploader_user_id
            ORDER BY meals DESC
        """).fetchall()

    # Compute max for CSS bar widths
    cuisine_max = max((r["cnt"] for r in cuisines), default=1)
    venue_max = max((r["total_photos"] for r in top_venues), default=1)

    return cast(HTMLResponse, templates.TemplateResponse(request, "book/stats.html", {
        "active": "book",
        "top_venues": [dict(r) for r in top_venues],
        "cuisines": [dict(r) for r in cuisines],
        "top_dishes": [dict(r) for r in top_dishes],
        "weekly": [dict(r) for r in weekly],
        "per_user": [dict(r) for r in per_user],
        "cuisine_max": cuisine_max,
        "venue_max": venue_max,
    }))
