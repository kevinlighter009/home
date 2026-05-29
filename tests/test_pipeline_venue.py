"""Tests for the venue-resolution step appended to the Plan 2 pipeline."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.providers.base import ProviderResult
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import CuratedPlace
from home_photo_repo.worker.pipeline import ProcessResult, process_asset

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@dataclass
class FakeImmich:
    bytes_to_return: bytes = b"fake-img"

    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        return self.bytes_to_return


@dataclass
class FakeProvider:
    parsed: dict[str, Any]

    def classify(self, image_bytes, prompt, response_schema, max_tokens=512):
        return ProviderResult(
            parsed=self.parsed, raw=str(self.parsed),
            latency_ms=10, input_tokens=10, output_tokens=10, model="fake:x",
        )


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset(*, lat: float | None = 37.7749, lng: float | None = -122.4194) -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id="asset-1", owner_id="owner-x", original_file_name="x.HEIC",
        updated_at=base, taken_at=base - timedelta(hours=1),
        latitude=lat, longitude=lng, file_created_at=base,
    )


def _matcher(conn: sqlite3.Connection) -> PlaceMatcher:
    return PlaceMatcher(
        repo=PlacesRepository(conn), google=None,
        ambiguous_threshold_m=50, search_radius_m=150,
    )


def _stage_a_food() -> FakeProvider:
    return FakeProvider({"is_food": True, "confidence": 0.95})


def _stage_b_pizza() -> FakeProvider:
    return FakeProvider({"dish_name": "pizza", "cuisine": "Italian", "confidence": 0.9})


def test_pipeline_resolves_curated_home_when_food_photo_at_home_gps(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    PlacesRepository(conn).insert(
        CuratedPlace(
            id="curated:home", name="Home", type="home",
            latitude=37.7749, longitude=-122.4194, radius_m=50,
            google_place_id=None, address=None, notes=None,
        )
    )
    matcher = _matcher(conn)

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    row = conn.execute(
        "SELECT venue_type, place_id, place_match_source, place_match_distance_m, "
        "venue_resolved_at, review_status FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] == "home"
    assert row["place_id"] == "curated:home"
    assert row["place_match_source"] == "curated"
    assert row["place_match_distance_m"] == pytest.approx(0.0, abs=1.0)
    assert row["venue_resolved_at"] is not None
    assert row["review_status"] == "auto"


def test_pipeline_marks_unknown_venue_when_no_curated_and_no_google(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    matcher = _matcher(conn)

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    row = conn.execute(
        "SELECT venue_type, place_id, review_status FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] == "unknown"
    assert row["place_id"] is None
    assert row["review_status"] == "needs_review"


def test_pipeline_skips_venue_resolution_when_no_matcher(tmp_path: Path) -> None:
    """Backward compat: no matcher = Plan 2 behavior, venue columns stay NULL."""
    conn = _conn(tmp_path)
    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=None,
    )
    row = conn.execute(
        "SELECT venue_type, venue_resolved_at FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] is None
    assert row["venue_resolved_at"] is None


def test_pipeline_skips_venue_resolution_when_no_gps(tmp_path: Path) -> None:
    """Photo without GPS — even with matcher provided, venue stays NULL."""
    conn = _conn(tmp_path)
    matcher = _matcher(conn)
    asset_no_gps = ImmichAsset(
        id="no-gps", owner_id="o", original_file_name="x.HEIC",
        updated_at=datetime(2026, 5, 28, 0, 0, 0, tzinfo=UTC),
        taken_at=datetime(2026, 5, 28, 0, 0, 0, tzinfo=UTC) - timedelta(hours=1),
        latitude=None, longitude=None, file_created_at=None,
    )
    later_now = asset_no_gps.updated_at + timedelta(hours=1)

    process_asset(
        conn, asset_no_gps, now=later_now,
        immich=FakeImmich(),
        stage_a_provider=_stage_a_food(), stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    row = conn.execute(
        "SELECT venue_type, venue_resolved_at FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] is None
    assert row["venue_resolved_at"] is None


def test_pipeline_skips_venue_resolution_when_not_food(tmp_path: Path) -> None:
    """Non-food photos never reach venue resolution (it runs after Stage B)."""
    conn = _conn(tmp_path)
    PlacesRepository(conn).insert(
        CuratedPlace(
            id="curated:home", name="Home", type="home",
            latitude=37.7749, longitude=-122.4194, radius_m=50,
            google_place_id=None, address=None, notes=None,
        )
    )
    matcher = _matcher(conn)
    not_food = FakeProvider({"is_food": False, "confidence": 0.95})

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=not_food, stage_b_provider=_stage_b_pizza(),
        place_matcher=matcher,
    )

    assert result is ProcessResult.STAGE_A_NOT_FOOD
    row = conn.execute(
        "SELECT venue_type, venue_resolved_at FROM photo_analysis"
    ).fetchone()
    assert row["venue_type"] is None
    assert row["venue_resolved_at"] is None
