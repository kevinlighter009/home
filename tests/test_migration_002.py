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
