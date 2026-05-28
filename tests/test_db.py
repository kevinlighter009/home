"""Tests for home_photo_repo.db.

The migration runner is forward-only: each .sql file in the migrations/
directory is applied once, in lexical order, and recorded in a _migrations
table so subsequent runs skip it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection


def _write_migration(dir_: Path, n: int, name: str, sql: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{n:03d}_{name}.sql").write_text(sql)


def test_get_connection_creates_parent_dirs(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "deeper" / "app.sqlite"
    conn = get_connection(db)
    assert db.exists()
    conn.close()


def test_apply_migrations_runs_in_order(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "init", "CREATE TABLE t1 (id INTEGER);")
    _write_migration(migrations, 2, "add_t2", "CREATE TABLE t2 (id INTEGER);")
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)

    apply_migrations(conn, migrations)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"t1", "t2", "_migrations"}.issubset(tables)


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "init", "CREATE TABLE t1 (id INTEGER);")
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)

    apply_migrations(conn, migrations)
    # Second call must not error on existing table.
    apply_migrations(conn, migrations)

    rows = conn.execute("SELECT id, description FROM _migrations ORDER BY id").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "001_init"


def test_apply_migrations_fails_loudly_on_bad_sql(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "broken", "CREATE TABEL t1 (id INTEGER);")  # typo
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)

    with pytest.raises(sqlite3.Error):
        apply_migrations(conn, migrations)

    rows = conn.execute("SELECT COUNT(*) FROM _migrations").fetchall()
    assert rows[0][0] == 0


def test_apply_migrations_rolls_back_partial_multi_statement(tmp_path: Path) -> None:
    """If statement N of a multi-statement migration fails, statements 1..N-1
    must not be visible on next run."""
    migrations = tmp_path / "migrations"
    # 3 CREATE statements; the 3rd is invalid SQL.
    _write_migration(
        migrations,
        1,
        "multi",
        "CREATE TABLE t1 (id INTEGER);"
        " CREATE TABLE t2 (id INTEGER);"
        " CREATE TABEL t3 (id INTEGER);",  # typo
    )
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)

    with pytest.raises(sqlite3.Error):
        apply_migrations(conn, migrations)

    # Neither t1 nor t2 should exist; migration not recorded.
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "t1" not in tables
    assert "t2" not in tables
    rows = conn.execute("SELECT COUNT(*) FROM _migrations").fetchall()
    assert rows[0][0] == 0


def test_apply_migrations_skips_already_applied(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "init", "CREATE TABLE t1 (id INTEGER);")
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)
    apply_migrations(conn, migrations)

    # Add a second migration and re-run; only the new one should apply.
    _write_migration(migrations, 2, "add_t2", "CREATE TABLE t2 (id INTEGER);")
    apply_migrations(conn, migrations)

    rows = conn.execute("SELECT description FROM _migrations ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["001_init", "002_add_t2"]
