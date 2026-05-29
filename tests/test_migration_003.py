"""Migration 003 adds indexes on places.google_place_id +
photo_analysis(stage_a_prompt_version, stage_a_ran_at)."""

from __future__ import annotations

from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def test_migration_003_creates_indexes(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    idx_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_places_google_id" in idx_names
    assert "idx_photo_stage_a_version_ran_at" in idx_names
