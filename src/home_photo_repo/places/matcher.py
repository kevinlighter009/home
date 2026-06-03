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

import logging
from typing import Protocol

from home_photo_repo.places.haversine import haversine_m
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import VALID_VENUE_TYPES, CuratedPlace, MatchResult, NearbyPlace

# Imported lazily to avoid a circular import (worker → places → worker).
# GoogleBudget is only used at runtime when explicitly passed in.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from home_photo_repo.worker.google_budget import GoogleBudget


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
        budget: "GoogleBudget | None" = None,
    ) -> None:
        self._repo = repo
        self._google = google
        self._ambiguous_threshold_m = ambiguous_threshold_m
        self._search_radius_m = search_radius_m
        self._budget = budget

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(self, *, latitude: float, longitude: float) -> MatchResult:
        """Full resolution: local cache → Google Places (budget-gated) → unknown."""
        local = self._repo.nearby(latitude, longitude)
        if local:
            return self._resolve_local(local)

        if self._google is None:
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                notes="no google_places client configured",
            )

        # Budget gate: check before calling the Google API.
        if self._budget is not None:
            conn = self._repo._conn
            if not self._budget.check_and_consume(conn):
                return MatchResult(
                    place_id=None, venue_type="unknown", distance_m=None,
                    source="unknown", needs_review=True,
                    retry_next_month=True,
                    notes="google_places monthly budget exhausted",
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
                retry_next_month=True,
                notes="no google places candidates",
            )

        return self._rank_and_cache(candidates, latitude, longitude)

    def local_lookup(
        self, latitude: float, longitude: float
    ) -> MatchResult | None:
        """Check only the local cache (curated + previously-cached Google rows).

        Returns a resolved ``MatchResult`` on a hit, or ``None`` on a miss.
        Never calls the Google Places API.  Used by the venue backfill to
        pre-filter photos before issuing concurrent Google requests.
        """
        local = self._repo.nearby(latitude, longitude)
        return self._resolve_local(local) if local else None

    def match_from_candidates(
        self,
        *,
        latitude: float,
        longitude: float,
        candidates: list[NearbyPlace],
    ) -> MatchResult:
        """Resolve a venue given pre-fetched Google candidates.

        The venue backfill fetches candidates concurrently (pure HTTP, no DB)
        then calls this to do the ranking, caching, and ambiguity check on the
        main thread.  Separating the HTTP step from the DB step makes it safe
        to parallelise API calls while keeping SQLite writes single-threaded.
        """
        if not candidates:
            return MatchResult(
                place_id=None, venue_type="unknown", distance_m=None,
                source="unknown", needs_review=True,
                retry_next_month=True,
                notes="no google places candidates",
            )
        return self._rank_and_cache(candidates, latitude, longitude)

    @property
    def search_radius_m(self) -> int:
        return self._search_radius_m

    def _rank_and_cache(
        self,
        candidates: list[NearbyPlace],
        latitude: float,
        longitude: float,
    ) -> MatchResult:
        """Rank candidates by distance, cache the winner, return a MatchResult."""
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
            radius_m=self._ambiguous_threshold_m,
            google_place_id=chosen.google_place_id,
            address=chosen.address,
            notes=",".join(chosen.types) if chosen.types else None,
        )
        try:
            self._repo.insert(cached)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "failed to cache gplaces row id=%s name=%s",
                cached.id, cached.name, exc_info=True,
            )

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
            ambiguous_candidates=tuple(ranked) if ambiguous else (),
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
