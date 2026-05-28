"""Tests for home_photo_repo.config.Settings."""

from pathlib import Path

import pytest


def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "test-key-abc")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    assert str(s.immich_base_url).rstrip("/") == "http://localhost:2283"
    assert s.immich_api_key.get_secret_value() == "test-key-abc"
    assert s.ssd_data_dir == Path("/tmp/hpr_test")


def test_settings_applies_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    assert s.poll_interval_seconds == 300
    assert s.backfill_batch_size == 100
    assert s.stage_a_food_threshold == 0.6


def test_settings_repr_masks_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "super-secret-do-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    text = repr(s)
    assert "super-secret-do-not-leak" not in text
    assert "anthropic-secret" not in text
    # The repr should still show the field names so debugging works.
    assert "immich_api_key" in text


def test_settings_db_path_derives_from_ssd_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    assert s.db_path == Path("/tmp/hpr_test/db/app.sqlite")
