"""Tests for the Plan 2 pipeline extensions: Stage A and Stage B integration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.worker.pipeline import ProcessResult, process_asset

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@dataclass
class FakeImmich:
    """Returns canned thumbnail bytes."""

    bytes_to_return: bytes = b"fake-img"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        self.calls.append((asset_id, size))
        return self.bytes_to_return


@dataclass
class FakeProvider:
    name: str
    parsed: dict[str, Any]
    should_raise: bool = False

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        if self.should_raise:
            raise ProviderError(f"{self.name} simulated failure")
        return ProviderResult(
            parsed=self.parsed,
            raw=str(self.parsed),
            latency_ms=10,
            input_tokens=100,
            output_tokens=10,
            model=f"{self.name}:test",
        )


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset(aid: str = "asset-1") -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id=aid,
        owner_id="owner-x",
        original_file_name=f"{aid}.HEIC",
        updated_at=base,
        taken_at=base - timedelta(hours=1),
        latitude=37.0,
        longitude=-122.0,
        file_created_at=base,
    )


def test_pipeline_runs_stage_a_and_records_food_result(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider(
        "anthropic", {"dish_name": "ramen", "cuisine": "Japanese", "confidence": 0.85}
    )
    immich = FakeImmich()

    result = process_asset(
        conn,
        _asset(),
        now=_asset().updated_at,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_AND_B_DONE
    row = conn.execute(
        "SELECT stage_a_is_food, stage_a_confidence, dish_name, cuisine, "
        "stage_b_confidence, review_status FROM photo_analysis"
    ).fetchone()
    assert row["stage_a_is_food"] == 1
    assert row["stage_a_confidence"] == pytest.approx(0.95)
    assert row["dish_name"] == "ramen"
    assert row["cuisine"] == "Japanese"
    assert row["stage_b_confidence"] == pytest.approx(0.85)
    assert row["review_status"] == "auto"


def test_pipeline_skips_stage_b_when_not_food(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": False, "confidence": 0.99})
    stage_b = FakeProvider(
        "anthropic", {"dish_name": "X", "cuisine": "Y", "confidence": 0.5}
    )
    immich = FakeImmich()

    result = process_asset(
        conn,
        _asset(),
        now=_asset().updated_at,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_NOT_FOOD
    row = conn.execute(
        "SELECT stage_a_is_food, dish_name FROM photo_analysis"
    ).fetchone()
    assert row["stage_a_is_food"] == 0
    assert row["dish_name"] is None  # stage B did not run


def test_pipeline_skips_stage_b_when_confidence_below_threshold(
    tmp_path: Path,
) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider(
        "anthropic", {"is_food": True, "confidence": 0.3}
    )  # below 0.6
    stage_b = FakeProvider(
        "anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9}
    )
    immich = FakeImmich()

    result = process_asset(
        conn,
        _asset(),
        now=_asset().updated_at,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_NOT_FOOD
    row = conn.execute("SELECT dish_name FROM photo_analysis").fetchone()
    assert row["dish_name"] is None


def test_pipeline_flags_low_confidence_stage_b_for_review(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider(
        "anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.4}
    )  # below 0.7
    immich = FakeImmich()

    result = process_asset(
        conn,
        _asset(),
        now=_asset().updated_at,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_AND_B_DONE
    row = conn.execute("SELECT review_status FROM photo_analysis").fetchone()
    assert row["review_status"] == "needs_review"


def test_pipeline_records_stage_a_error_and_stops(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {}, should_raise=True)
    stage_b = FakeProvider(
        "anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9}
    )
    immich = FakeImmich()

    result = process_asset(
        conn,
        _asset(),
        now=_asset().updated_at,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_ONLY_ERROR
    row = conn.execute(
        "SELECT last_error, review_status, error_attempts FROM photo_analysis"
    ).fetchone()
    assert row["last_error"].startswith("stage_a:")
    assert row["review_status"] == "needs_review"
    assert row["error_attempts"] == 1


def test_pipeline_records_stage_b_error(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider("anthropic", {}, should_raise=True)
    immich = FakeImmich()

    result = process_asset(
        conn,
        _asset(),
        now=_asset().updated_at,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_B_ERROR
    row = conn.execute(
        "SELECT stage_a_is_food, dish_name, last_error, review_status FROM photo_analysis"
    ).fetchone()
    assert row["stage_a_is_food"] == 1  # stage A still recorded
    assert row["dish_name"] is None
    assert row["last_error"].startswith("stage_b:")
    assert row["review_status"] == "needs_review"


def test_pipeline_uses_thumbnail_for_a_and_preview_for_b(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider(
        "anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9}
    )
    immich = FakeImmich()

    process_asset(
        conn,
        _asset(),
        now=_asset().updated_at,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )
    sizes_requested = [size for (_, size) in immich.calls]
    assert sizes_requested == ["thumbnail", "preview"]


def test_pipeline_already_present_short_circuits_after_stage_a(
    tmp_path: Path,
) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider(
        "anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9}
    )
    immich = FakeImmich()
    a = _asset()
    now = a.updated_at

    first = process_asset(
        conn,
        a,
        now=now,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )
    assert first is ProcessResult.STAGE_A_AND_B_DONE
    second = process_asset(
        conn,
        a,
        now=now,
        immich=immich,
        stage_a_provider=stage_a,
        stage_b_provider=stage_b,
    )
    assert second is ProcessResult.ALREADY_PRESENT
