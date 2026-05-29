"""End-to-end pipeline test for venue disambiguation."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.providers.base import ProviderResult
from home_photo_repo.llm.venue_disambiguator import DisambiguatedVenue
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import NearbyPlace
from home_photo_repo.worker.pipeline import process_asset

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@dataclass
class FakeImmich:
    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        return b"img"


@dataclass
class FakeProvider:
    parsed: dict[str, Any]

    def classify(self, image_bytes, prompt, response_schema, max_tokens=512):
        return ProviderResult(
            parsed=self.parsed, raw=str(self.parsed),
            latency_ms=1, input_tokens=1, output_tokens=1, model="fake:x",
        )


class FakeGoogle:
    """Returns 2 candidates close together (ambiguous)."""

    def search_nearby(self, *, latitude, longitude, radius_m):
        return [
            NearbyPlace(google_place_id="gp-a", name="Cafe A",
                        latitude=37.762, longitude=-122.434, address=None,
                        types=("restaurant",)),
            NearbyPlace(google_place_id="gp-b", name="Cafe B",
                        latitude=37.7621, longitude=-122.4341, address=None,
                        types=("restaurant",)),
        ]


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset() -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id="a-1", owner_id="o", original_file_name="x.HEIC",
        updated_at=base, taken_at=base - timedelta(hours=1),
        latitude=37.762, longitude=-122.434, file_created_at=base,
    )


def test_disambiguator_refines_ambiguous_match(tmp_path: Path) -> None:
    """Pipeline runs an ambiguous Google fallback through the disambiguator,
    which picks gp-b. Result row should have place_id='gplaces:gp-b',
    review_status='auto' (no longer needs_review), and source='llm_disambiguated'."""
    conn = _conn(tmp_path)
    stage_a = FakeProvider({"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider({"dish_name": "ramen", "cuisine": "Japanese", "confidence": 0.9})
    matcher = PlaceMatcher(
        repo=PlacesRepository(conn), google=FakeGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    def disambiguator(image_bytes: bytes, candidates: list[NearbyPlace]) -> DisambiguatedVenue:
        return DisambiguatedVenue(
            google_place_id="gp-b", confidence=0.85,
            model="fake:dis", raw_json="{}",
        )

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=stage_a, stage_b_provider=stage_b,
        place_matcher=matcher, venue_disambiguator=disambiguator,
    )

    row = conn.execute(
        "SELECT place_id, place_match_source, review_status, review_notes "
        "FROM photo_analysis"
    ).fetchone()
    assert row["place_id"] == "gplaces:gp-b"
    assert row["place_match_source"] == "llm_disambiguated"
    assert row["review_status"] == "auto"
    assert "disambiguat" in (row["review_notes"] or "").lower()


def test_disambiguator_low_confidence_falls_back_to_original(tmp_path: Path) -> None:
    """If disambiguator picks but with confidence < 0.6, keep the matcher's
    nearest pick (the existing ambiguous result)."""
    conn = _conn(tmp_path)
    stage_a = FakeProvider({"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider({"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    matcher = PlaceMatcher(
        repo=PlacesRepository(conn), google=FakeGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    def disambiguator(image_bytes, candidates):
        return DisambiguatedVenue(
            google_place_id="gp-b", confidence=0.3,
            model="fake:dis", raw_json="{}",
        )

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=stage_a, stage_b_provider=stage_b,
        place_matcher=matcher, venue_disambiguator=disambiguator,
    )

    row = conn.execute(
        "SELECT place_match_source, review_status FROM photo_analysis"
    ).fetchone()
    assert row["place_match_source"] == "google_places"
    assert row["review_status"] == "needs_review"


def test_disambiguator_returning_none_falls_back(tmp_path: Path) -> None:
    """Disambiguator returning google_place_id=None means 'none of these' —
    keep the matcher's original pick (still needs_review)."""
    conn = _conn(tmp_path)
    stage_a = FakeProvider({"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider({"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    matcher = PlaceMatcher(
        repo=PlacesRepository(conn), google=FakeGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    def disambiguator(image_bytes, candidates):
        return DisambiguatedVenue(
            google_place_id=None, confidence=0.5,
            model="fake:dis", raw_json="{}",
        )

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=stage_a, stage_b_provider=stage_b,
        place_matcher=matcher, venue_disambiguator=disambiguator,
    )

    row = conn.execute("SELECT review_status FROM photo_analysis").fetchone()
    assert row["review_status"] == "needs_review"
