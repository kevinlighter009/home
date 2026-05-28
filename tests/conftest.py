"""Pytest configuration: enable socket disabling globally (we mock all HTTP)."""

import os

import pytest


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests cannot accidentally read the developer's real .env."""
    for key in list(os.environ):
        if key.startswith(("IMMICH_", "ANTHROPIC_", "GOOGLE_", "LLM_", "MLX_", "SSD_")):
            monkeypatch.delenv(key, raising=False)
