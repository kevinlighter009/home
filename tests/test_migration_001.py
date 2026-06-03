"""Verify migrations/001_initial.sql creates the schema the spec requires."""

from __future__ import annotations

from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _column_names(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_initial_migration_creates_all_tables(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert tables == {
        "_migrations",
        "photo_analysis",
        "places",
        "worker_runs",
        "worker_state",
        "immich_users",       # added by migration 004
    }


def test_photo_analysis_has_expected_columns(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    cols = _column_names(conn, "photo_analysis")
    expected = {
        "immich_asset_id",
        "first_seen_at",
        "taken_at",
        "latitude",
        "longitude",
        "uploader_user_id",
        "stage_a_is_food",
        "stage_a_confidence",
        "stage_a_model",
        "stage_a_ran_at",
        "dish_name",
        "cuisine",
        "stage_b_confidence",
        "stage_b_model",
        "stage_b_ran_at",
        "stage_b_raw_json",
        "venue_type",
        "place_id",
        "place_match_source",
        "place_match_distance_m",
        "review_status",
        "reviewed_at",
        "review_notes",
        "last_error",
        "error_attempts",
    }
    assert expected.issubset(cols)


def test_places_has_expected_columns(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    cols = _column_names(conn, "places")
    assert {
        "id",
        "name",
        "type",
        "latitude",
        "longitude",
        "radius_m",
        "google_place_id",
        "address",
        "created_at",
        "updated_at",
        "notes",
    }.issubset(cols)


def test_indexes_present(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    idx = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert {
        "idx_photo_taken_at",
        "idx_photo_place",
        "idx_photo_review",
        "idx_places_type",
    }.issubset(idx)
