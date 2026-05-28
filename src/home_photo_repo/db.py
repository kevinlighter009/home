"""SQLite connection helper and forward-only migration runner.

A migration is any file `migrations/NNN_description.sql`. They are applied
in lexical order, exactly once each, tracked in a `_migrations` table.
"""

from __future__ import annotations

import contextlib
import sqlite3
import sys
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a SQLite connection at `db_path`.

    Enables foreign keys and WAL mode for safer concurrent reads.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        isolation_level=None,  # autocommit; we manage tx with BEGIN/COMMIT explicitly
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            id          INTEGER PRIMARY KEY,
            applied_at  DATETIME NOT NULL,
            description TEXT NOT NULL
        )
        """
    )


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[str]:
    """Apply any pending migrations. Returns the descriptions applied this call."""
    _ensure_migrations_table(conn)
    applied = {
        row[0] for row in conn.execute("SELECT description FROM _migrations").fetchall()
    }
    files = sorted(p for p in migrations_dir.glob("*.sql"))
    newly_applied: list[str] = []
    for path in files:
        desc = path.stem  # e.g. "001_initial"
        if desc in applied:
            continue
        sql = path.read_text()
        # NOTE: sqlite3.executescript() issues an implicit COMMIT before
        # running and then runs its statements in autocommit, so wrapping it
        # in an explicit BEGIN/COMMIT raises "cannot commit - no transaction
        # is active". Run the script as-is; record the migration in its own
        # short transaction.
        conn.executescript(sql)
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO _migrations (id, applied_at, description) "
                "VALUES (?, datetime('now'), ?)",
                (int(desc.split("_", 1)[0]), desc),
            )
            conn.execute("COMMIT")
        except sqlite3.Error:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        newly_applied.append(desc)
    return newly_applied


def _cli_migrate() -> None:
    """`python -m home_photo_repo.db migrate` — apply migrations using Settings."""
    from home_photo_repo.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    repo_root = Path(__file__).resolve().parents[2]
    migrations_dir = repo_root / "migrations"
    conn = get_connection(settings.db_path)
    applied = apply_migrations(conn, migrations_dir)
    if applied:
        print(f"Applied: {', '.join(applied)}")
    else:
        print("No pending migrations.")


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) >= 2 and sys.argv[1] == "migrate":
        _cli_migrate()
    else:
        print("Usage: python -m home_photo_repo.db migrate", file=sys.stderr)
        sys.exit(2)
