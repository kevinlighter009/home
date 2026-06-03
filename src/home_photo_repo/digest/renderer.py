"""Build the HTML body and plain-text fallback for the weekly digest email."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

_FOOD_WHERE = """
    stage_a_is_food = 1
    AND stage_a_ran_at IS NOT NULL
    AND taken_at IS NOT NULL
"""


def _week_bounds() -> tuple[date, date]:
    """Return (monday, sunday) for the most recently completed week."""
    today = date.today()
    # 'last' Sunday = today minus its isoweekday (Mon=1 … Sun=7), then -1 more day
    # Simpler: subtract days so we land on Sunday of the *previous* week
    days_since_sunday = today.isoweekday() % 7  # Sun=0, Mon=1 … Sat=6
    last_sunday = today - timedelta(days=days_since_sunday if days_since_sunday > 0 else 7)
    last_monday = last_sunday - timedelta(days=6)
    return last_monday, last_sunday


def _gather(conn: sqlite3.Connection) -> dict[str, Any]:
    monday, sunday = _week_bounds()
    mon_str = monday.isoformat()
    sun_str = sunday.isoformat()

    # This week totals
    week_stats = conn.execute(f"""
        SELECT
          COUNT(*)                               AS total,
          COUNT(DISTINCT COALESCE(place_id,'')) AS venues,
          COUNT(DISTINCT cuisine)               AS cuisines,
          COUNT(DISTINCT uploader_user_id)      AS users
        FROM photo_analysis
        WHERE {_FOOD_WHERE}
          AND DATE(taken_at) BETWEEN ? AND ?
    """, (mon_str, sun_str)).fetchone()

    # New cuisines this week (never eaten before the week started)
    new_cuisines = conn.execute(f"""
        SELECT cuisine
        FROM photo_analysis
        WHERE {_FOOD_WHERE}
          AND DATE(taken_at) BETWEEN ? AND ?
          AND cuisine IS NOT NULL
          AND cuisine NOT IN (
            SELECT DISTINCT cuisine FROM photo_analysis
            WHERE {_FOOD_WHERE} AND DATE(taken_at) < ?
              AND cuisine IS NOT NULL
          )
        GROUP BY cuisine
    """, (mon_str, sun_str, mon_str)).fetchall()

    # Top dishes this week
    top_dishes = conn.execute(f"""
        SELECT dish_name, COUNT(*) AS cnt
        FROM photo_analysis
        WHERE {_FOOD_WHERE}
          AND DATE(taken_at) BETWEEN ? AND ?
          AND dish_name IS NOT NULL
        GROUP BY LOWER(TRIM(dish_name))
        ORDER BY cnt DESC LIMIT 5
    """, (mon_str, sun_str)).fetchall()

    # Shared meals this week
    shared = conn.execute(f"""
        SELECT DATE(pa.taken_at) AS meal_date,
               p.name            AS venue_name,
               p.type            AS venue_type,
               COUNT(DISTINCT pa.uploader_user_id) AS people,
               COUNT(*)          AS photos
        FROM photo_analysis pa
        LEFT JOIN places p ON pa.place_id = p.id
        WHERE {_FOOD_WHERE}
          AND pa.place_id IS NOT NULL
          AND DATE(pa.taken_at) BETWEEN ? AND ?
        GROUP BY meal_date, pa.place_id
        HAVING COUNT(DISTINCT pa.uploader_user_id) >= 2
        ORDER BY meal_date DESC
    """, (mon_str, sun_str)).fetchall()

    # All-time counts for context
    alltime = conn.execute(f"""
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT COALESCE(place_id,'')) AS venues,
               COUNT(DISTINCT cuisine) AS cuisines
        FROM photo_analysis WHERE {_FOOD_WHERE}
    """).fetchone()

    # Per-user all-time
    per_user = conn.execute(f"""
        SELECT COALESCE(u.display_name, u.username, pa.uploader_user_id) AS name,
               COUNT(*) AS meals
        FROM photo_analysis pa
        LEFT JOIN immich_users u ON pa.uploader_user_id = u.user_id
        WHERE {_FOOD_WHERE}
        GROUP BY pa.uploader_user_id ORDER BY meals DESC
    """).fetchall()

    # Top cuisines all-time
    top_cuisines_alltime = conn.execute(f"""
        SELECT cuisine, COUNT(*) AS cnt
        FROM photo_analysis WHERE {_FOOD_WHERE} AND cuisine IS NOT NULL
        GROUP BY cuisine ORDER BY cnt DESC LIMIT 8
    """).fetchall()

    return {
        "monday": monday,
        "sunday": sunday,
        "week_stats": dict(week_stats) if week_stats else {},
        "new_cuisines": [r["cuisine"] for r in new_cuisines],
        "top_dishes": [dict(r) for r in top_dishes],
        "shared_meals": [dict(r) for r in shared],
        "alltime": dict(alltime) if alltime else {},
        "per_user": [dict(r) for r in per_user],
        "top_cuisines": [dict(r) for r in top_cuisines_alltime],
    }


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _date_range_label(monday: date, sunday: date) -> str:
    if monday.month == sunday.month:
        return f"{monday.strftime('%b %-d')}–{sunday.day}, {monday.year}"
    return f"{monday.strftime('%b %-d')} – {sunday.strftime('%b %-d')}, {monday.year}"


def render_digest(conn: sqlite3.Connection) -> tuple[str, str, str]:
    """Return (subject, html_body, plain_body).

    Call with an open SQLite connection (read-only is fine).
    """
    data = _gather(conn)
    monday: date = data["monday"]
    sunday: date = data["sunday"]
    week_label = _date_range_label(monday, sunday)
    ws = data["week_stats"]
    at = data["alltime"]

    subject = f"🍽️ Food Memory Digest — {week_label}"

    # --- HTML ---
    html_parts: list[str] = []

    def h(s: str) -> None:
        html_parts.append(s)

    h("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f7f7f8;color:#1f2227;font-size:14px;margin:0;padding:0}
.wrap{max-width:600px;margin:0 auto;padding:24px 16px}
.card{background:#fff;border:1px solid #e2e2e6;border-radius:8px;
      padding:20px;margin-bottom:16px}
h1{font-size:20px;margin:0 0 4px}
h2{font-size:15px;margin:0 0 12px;color:#1f2227}
.muted{color:#6b7280;font-size:12px}
.stat-row{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:8px}
.stat{text-align:center}
.stat .n{font-size:26px;font-weight:700;line-height:1.1}
.stat .l{color:#6b7280;font-size:11px}
.pill{display:inline-block;padding:3px 12px;border:1px solid #e2e2e6;
      border-radius:20px;font-size:12px;margin:3px;background:#f7f7f8}
table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:7px 10px;border-bottom:1px solid #e2e2e6;font-size:13px}
th{font-weight:600;background:#f7f7f8;color:#6b7280}
.footer{text-align:center;color:#6b7280;font-size:11px;padding:16px 0}
</style>
</head>
<body>
<div class="wrap">
""")

    # Header
    h(f"""<div class="card">
  <h1>🍽️ Food Memory Digest</h1>
  <p class="muted">{week_label}</p>
  <div class="stat-row">
    <div class="stat"><div class="n">{ws.get('total', 0)}</div><div class="l">photos this week</div></div>
    <div class="stat"><div class="n">{ws.get('venues', 0)}</div><div class="l">venues</div></div>
    <div class="stat"><div class="n">{ws.get('cuisines', 0)}</div><div class="l">cuisines</div></div>
    <div class="stat"><div class="n">{ws.get('users', 0)}</div><div class="l">people</div></div>
  </div>
</div>
""")

    # New cuisines discovered
    if data["new_cuisines"]:
        pills = "".join(f'<span class="pill">🆕 {c}</span>' for c in data["new_cuisines"])
        h(f'<div class="card"><h2>New cuisines discovered this week</h2>{pills}</div>\n')

    # Top dishes
    if data["top_dishes"]:
        rows = "".join(
            f'<tr><td>{d["dish_name"]}</td><td style="text-align:right">{d["cnt"]}</td></tr>'
            for d in data["top_dishes"]
        )
        h(f"""<div class="card">
  <h2>Top dishes this week</h2>
  <table><thead><tr><th>Dish</th><th style="text-align:right">Times</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>
""")

    # Shared meals
    if data["shared_meals"]:
        rows = "".join(
            f'<tr><td>{m["meal_date"]}</td>'
            f'<td>{m["venue_name"] or "(unnamed)"}</td>'
            f'<td style="text-align:right">{m["people"]} people · {m["photos"]} photos</td></tr>'
            for m in data["shared_meals"]
        )
        h(f"""<div class="card">
  <h2>💑 Shared meals this week</h2>
  <table><thead><tr><th>Date</th><th>Venue</th><th>Details</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>
""")
    else:
        h('<div class="card"><h2>💑 Shared meals</h2>'
          '<p class="muted">No shared meals recorded this week.</p></div>\n')

    # All-time highlights
    at_total = at.get("total", 0)
    at_venues = at.get("venues", 0)
    at_cuisines = at.get("cuisines", 0)
    h(f"""<div class="card">
  <h2>All-time highlights</h2>
  <div class="stat-row">
    <div class="stat"><div class="n">{at_total}</div><div class="l">total photos</div></div>
    <div class="stat"><div class="n">{at_venues}</div><div class="l">venues</div></div>
    <div class="stat"><div class="n">{at_cuisines}</div><div class="l">cuisines</div></div>
  </div>
""")

    # Per-user
    if data["per_user"]:
        user_bits = "  ".join(
            f'<span class="pill">{u["name"]}: {u["meals"]}</span>'
            for u in data["per_user"]
        )
        h(f'<p style="margin:8px 0 0;">{user_bits}</p>\n')

    h("</div>\n")

    # Footer
    h('<div class="footer">home_photo_repo · unsubscribe by removing your email from DIGEST_TO_EMAILS</div>\n')
    h("</div></body></html>")

    html_body = "".join(html_parts)

    # --- Plain text ---
    plain_lines: list[str] = [
        f"Food Memory Digest — {week_label}",
        "=" * 40,
        "",
        f"This week: {ws.get('total', 0)} photos, {ws.get('venues', 0)} venues, "
        f"{ws.get('cuisines', 0)} cuisines, {ws.get('users', 0)} people",
        "",
    ]
    if data["new_cuisines"]:
        plain_lines += ["New cuisines: " + ", ".join(data["new_cuisines"]), ""]
    if data["top_dishes"]:
        plain_lines.append("Top dishes:")
        for d in data["top_dishes"]:
            plain_lines.append(f"  {d['dish_name']} × {d['cnt']}")
        plain_lines.append("")
    if data["shared_meals"]:
        plain_lines.append("Shared meals:")
        for m in data["shared_meals"]:
            plain_lines.append(
                f"  {m['meal_date']} – {m['venue_name'] or '(unnamed)'} "
                f"({m['people']} people)"
            )
        plain_lines.append("")
    plain_lines += [
        f"All-time: {at_total} photos · {at_venues} venues · {at_cuisines} cuisines",
    ]
    plain_body = "\n".join(plain_lines)

    return subject, html_body, plain_body
