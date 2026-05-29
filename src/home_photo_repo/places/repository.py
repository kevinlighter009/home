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
