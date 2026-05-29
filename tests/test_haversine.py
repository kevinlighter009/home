"""Tests for the great-circle distance helper.

Reference distances:
- SFO (37.6213, -122.3790) to LAX (33.9416, -118.4085): ~543 km
- 0,0 to 0,1 (one degree longitude at equator): ~111.32 km
- Same point: 0
"""

from __future__ import annotations

import pytest

from home_photo_repo.places.haversine import haversine_m


def test_same_point_returns_zero() -> None:
    assert haversine_m(37.7749, -122.4194, 37.7749, -122.4194) == pytest.approx(0.0)


def test_sfo_to_lax_about_543km() -> None:
    d = haversine_m(37.6213, -122.3790, 33.9416, -118.4085)
    assert d == pytest.approx(543_000, rel=0.01)


def test_one_degree_longitude_at_equator_about_111km() -> None:
    d = haversine_m(0.0, 0.0, 0.0, 1.0)
    assert d == pytest.approx(111_320, rel=0.005)


def test_one_degree_latitude_about_111km() -> None:
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_320, rel=0.005)


def test_short_distance_san_francisco() -> None:
    d = haversine_m(37.7749, -122.4194, 37.7758, -122.4194)
    assert d == pytest.approx(100, rel=0.05)


def test_symmetric() -> None:
    a = haversine_m(37.7749, -122.4194, 40.7128, -74.0060)
    b = haversine_m(40.7128, -74.0060, 37.7749, -122.4194)
    assert a == pytest.approx(b)
