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
    from pathlib import Path

    from home_photo_repo.db import apply_migrations, get_connection
    from home_photo_repo.settings_factory import load_settings

    settings = load_settings()
    repo_root = Path(__file__).resolve().parents[3]
    conn = get_connection(settings.db_path)
    apply_migrations(conn, repo_root / "migrations")
    rc = run(sys.argv[1:], conn=conn)
    sys.exit(rc)


if __name__ == "__main__":  # pragma: no cover
    main()
