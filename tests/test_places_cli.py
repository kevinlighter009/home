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
