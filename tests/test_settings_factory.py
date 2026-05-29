"""Tests for load_settings() — centralizes the pydantic-settings call-arg ignore."""

from __future__ import annotations

import pytest


def test_load_settings_returns_settings_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings
    from home_photo_repo.settings_factory import load_settings

    s = load_settings()
    assert isinstance(s, Settings)
    assert s.immich_api_key.get_secret_value() == "k"
