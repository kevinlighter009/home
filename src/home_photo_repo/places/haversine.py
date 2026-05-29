"""Great-circle distance helper using the haversine formula.

Returns meters between two (lat, lng) points on Earth's surface. Accurate
enough for our use case (matching photos to venues within ~150m); for
sub-meter accuracy you'd want Vincenty or geodesic instead.
"""

from __future__ import annotations

import math

_EARTH_RADIUS_M: float = 6_371_000.0  # mean Earth radius in meters


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in meters between two lat/lng points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _EARTH_RADIUS_M * c


__all__ = ["haversine_m"]
