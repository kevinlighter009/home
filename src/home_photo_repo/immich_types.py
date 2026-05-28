"""Typed value objects for Immich API responses we consume."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ImmichAsset:
    id: str
    owner_id: str
    original_file_name: str
    updated_at: datetime
    taken_at: datetime | None
    latitude: float | None
    longitude: float | None
    file_created_at: datetime | None


__all__ = ["ImmichAsset"]
