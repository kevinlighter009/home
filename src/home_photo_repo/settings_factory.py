"""Centralized Settings constructor.

Wraps the `Settings()` call once so the `# type: ignore[call-arg]` (required
because pydantic-settings populates required fields from env, but mypy sees
them as missing kwargs) lives in one place.
"""

from __future__ import annotations

from home_photo_repo.config import Settings


def load_settings() -> Settings:
    """Construct a Settings instance from env / .env. Centralizes the mypy ignore."""
    return Settings()  # type: ignore[call-arg]


__all__ = ["load_settings"]
