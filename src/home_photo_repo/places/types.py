"""Typed value objects for place data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedPlace:
    """A row from the places table — user-curated or cached from Google Places."""

    id: str
    name: str
    type: str
    latitude: float
    longitude: float
    radius_m: int
    google_place_id: str | None
    address: str | None
    notes: str | None


@dataclass(frozen=True)
class NearbyPlace:
    """A candidate place returned by the Google Places client (not yet cached)."""

    google_place_id: str
    name: str
    latitude: float
    longitude: float
    address: str | None
    types: tuple[str, ...]


@dataclass(frozen=True)
class MatchResult:
    """The outcome of `PlaceMatcher.match()`."""

    place_id: str | None
    venue_type: str
    distance_m: float | None
    source: str
    needs_review: bool
    notes: str | None = None


__all__ = ["CuratedPlace", "MatchResult", "NearbyPlace"]
