"""Google Places API (New) — Nearby Search.

Endpoint: POST https://places.googleapis.com/v1/places:searchNearby
Auth: X-Goog-Api-Key header.
Field mask: required header X-Goog-FieldMask listing which fields the response
            should include (also controls billing — smaller mask = cheaper).
"""

from __future__ import annotations

from typing import Any

import httpx

from home_photo_repo.places.types import NearbyPlace

_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"

# Types from Google Places that we treat as food venues.
_FOOD_VENUE_TYPES: tuple[str, ...] = (
    "restaurant",
    "cafe",
    "bakery",
    "bar",
    "meal_delivery",
    "meal_takeaway",
)

# We request only the fields we parse — keeps response small and billing low.
_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.types,"
    "places.location"
)


class GooglePlacesError(RuntimeError):
    """Raised on HTTP error or malformed response from Google Places."""


class GooglePlacesClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GooglePlacesClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def search_nearby(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> list[NearbyPlace]:
        body: dict[str, Any] = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_m,
                }
            },
            "includedTypes": list(_FOOD_VENUE_TYPES),
            "maxResultCount": 10,
            "rankPreference": "DISTANCE",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        try:
            response = self._client.post(_ENDPOINT, headers=headers, json=body)
        except httpx.HTTPError as e:
            raise GooglePlacesError(f"Google Places HTTP error: {e!r}") from e
        if response.status_code >= 400:
            raise GooglePlacesError(
                f"Google Places returned {response.status_code}: "
                f"{response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as e:
            raise GooglePlacesError(f"non-JSON response: {e!r}") from e
        if not isinstance(data, dict):
            raise GooglePlacesError("non-object JSON response")

        places_raw = data.get("places", []) or []
        return [_parse_place(p) for p in places_raw]


def _parse_place(item: dict[str, Any]) -> NearbyPlace:
    try:
        google_id = item["id"]
        display = item["displayName"]
        name = display["text"] if isinstance(display, dict) else str(display)
        location = item["location"]
        lat = float(location["latitude"])
        lng = float(location["longitude"])
    except (KeyError, TypeError, ValueError) as e:
        raise GooglePlacesError(f"malformed Google Places item: {e!r}") from e
    types = tuple(item.get("types", []) or [])
    address = item.get("formattedAddress")
    return NearbyPlace(
        google_place_id=google_id,
        name=name,
        latitude=lat,
        longitude=lng,
        address=address,
        types=types,
    )


__all__ = ["GooglePlacesClient", "GooglePlacesError"]
