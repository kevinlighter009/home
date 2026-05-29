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
from home_photo_repo.places.types import VALID_VENUE_TYPES, CuratedPlace, MatchResult, NearbyPlace


class _GoogleLike(Protocol):
    def search_nearby(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> list[NearbyPlace]: ...


_CURATED_VENUE_TYPES = set(VALID_VENUE_TYPES)


# Google Places returns multiple type strings per place; we pick the first
# that maps into our canonical venue_type bucket.
_GOOGLE_TYPE_TO_VENUE: dict[str, str] = {
    "restaurant": "restaurant",
    "cafe": "restaurant",
    "bakery": "restaurant",
    "bar": "restaurant",
    "meal_delivery": "restaurant",
    "meal_takeaway": "restaurant",
    # Future: when we widen included_types to parks etc., map them to 'outdoor'
}


def _classify_google_types(types: tuple[str, ...]) -> str:
    """Map a Google place's types tuple to our canonical venue_type bucket.

    All current `_FOOD_VENUE_TYPES` map to 'restaurant'; the function exists
    so the matcher's caching path doesn't have to hardcode the mapping and
    so we can extend the table later (e.g., parks → outdoor)."""
    for t in types:
        bucket = _GOOGLE_TYPE_TO_VENUE.get(t)
        if bucket is not None:
            return bucket
    return "restaurant"  # fallback — we only call this on results from the food query


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

        venue_bucket = _classify_google_types(chosen.types)
        cached = CuratedPlace(
            id=f"gplaces:{chosen.google_place_id}",
            name=chosen.name,
            type=venue_bucket,
            latitude=chosen.latitude,
            longitude=chosen.longitude,
            # Use the tight ambiguity threshold as the cache row's radius —
            # only a very close future photo should re-match this row, otherwise
            # we'd cluster distinct restaurants on the same block.
            radius_m=self._ambiguous_threshold_m,
            google_place_id=chosen.google_place_id,
            address=chosen.address,
            # Preserve raw Google types for debugging / future re-mapping.
            notes=",".join(chosen.types) if chosen.types else None,
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
            venue_type=venue_bucket,
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
