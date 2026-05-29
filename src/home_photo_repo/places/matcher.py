"""Place resolution orchestration.

Resolution order (per spec 4.3):
  1. Local lookup in the `places` table (covers both user-curated and
     previously-cached Google Places rows).
  2. Google Places Nearby Search (only if step 1 missed and a client is
     configured). Result is cached as a new `places` row keyed
     `gplaces:<id>` so subsequent matches at the same location resolve
     locally.
  3. Else: unknown + needs_review.
"""

from __future__ import annotations

import contextlib
from typing import Protocol

from home_photo_repo.places.haversine import haversine_m
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace, MatchResult, NearbyPlace


class _GoogleLike(Protocol):
    def search_nearby(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> list[NearbyPlace]: ...


_CURATED_VENUE_TYPES = {"home", "office", "friend_place", "restaurant", "other"}


class PlaceMatcher:
    def __init__(
        self,
        *,
        repo: PlacesRepository,
        google: _GoogleLike | None,
        ambiguous_threshold_m: int,
        search_radius_m: int,
    ) -> None:
        self._repo = repo
        self._google = google
        self._ambiguous_threshold_m = ambiguous_threshold_m
        self._search_radius_m = search_radius_m

    def match(self, *, latitude: float, longitude: float) -> MatchResult:
        local = self._repo.nearby(latitude, longitude)
        if local:
            return self._resolve_local(local)

        if self._google is None:
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                notes="no google_places client configured",
            )
        try:
            candidates = self._google.search_nearby(
                latitude=latitude, longitude=longitude,
                radius_m=self._search_radius_m,
            )
        except Exception as e:  # noqa: BLE001
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                notes=f"google places error: {e!r}",
            )
        if not candidates:
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                notes="no google places candidates",
            )

        ranked = sorted(
            candidates,
            key=lambda c: haversine_m(latitude, longitude, c.latitude, c.longitude),
        )
        chosen = ranked[0]
        chosen_dist = haversine_m(latitude, longitude, chosen.latitude, chosen.longitude)

        cached = CuratedPlace(
            id=f"gplaces:{chosen.google_place_id}",
            name=chosen.name,
            type="restaurant",
            latitude=chosen.latitude,
            longitude=chosen.longitude,
            radius_m=self._ambiguous_threshold_m,
            google_place_id=chosen.google_place_id,
            address=chosen.address,
            notes=None,
        )
        with contextlib.suppress(Exception):
            self._repo.insert(cached)

        ambiguous = False
        if len(ranked) > 1:
            second = ranked[1]
            sep = haversine_m(
                chosen.latitude, chosen.longitude,
                second.latitude, second.longitude,
            )
            if sep <= self._ambiguous_threshold_m:
                ambiguous = True
        notes = (
            f"ambiguous: {len(ranked)} google candidates within "
            f"{self._ambiguous_threshold_m}m"
            if ambiguous
            else None
        )
        return MatchResult(
            place_id=cached.id,
            venue_type="restaurant",
            distance_m=chosen_dist,
            source="google_places",
            needs_review=ambiguous,
            notes=notes,
        )

    def _resolve_local(
        self, candidates: list[tuple[CuratedPlace, float]]
    ) -> MatchResult:
        winner_place, winner_dist = candidates[0]
        venue_type = (
            winner_place.type if winner_place.type in _CURATED_VENUE_TYPES else "other"
        )
        ambiguous = False
        if len(candidates) > 1:
            second_place, _ = candidates[1]
            sep = haversine_m(
                winner_place.latitude, winner_place.longitude,
                second_place.latitude, second_place.longitude,
            )
            if sep <= self._ambiguous_threshold_m:
                ambiguous = True
        notes = (
            f"ambiguous: {len(candidates)} curated places within "
            f"{self._ambiguous_threshold_m}m"
            if ambiguous
            else None
        )
        return MatchResult(
            place_id=winner_place.id,
            venue_type=venue_type,
            distance_m=winner_dist,
            source="curated",
            needs_review=ambiguous,
            notes=notes,
        )


__all__ = ["PlaceMatcher"]
