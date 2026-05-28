"""Application configuration loaded from environment / .env file.

Secrets are wrapped in `SecretStr` so their values do not appear in repr/log output.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Immich
    immich_base_url: HttpUrl
    immich_api_key: SecretStr

    # Other provider keys — accepted but unused in Plan 1.
    anthropic_api_key: SecretStr = SecretStr("")
    google_places_api_key: SecretStr = SecretStr("")

    # Storage
    ssd_data_dir: Path

    # Worker tunables
    poll_interval_seconds: int = 300
    backfill_batch_size: int = 100
    stage_a_food_threshold: float = 0.6
    stage_b_confidence_review_threshold: float = 0.7
    place_match_ambiguous_threshold_m: int = 50
    curated_place_default_radius_m: int = 50
    google_places_search_radius_m: int = 150
    anthropic_rate_limit_per_minute: int = 30
    dashboard_bind: str = "127.0.0.1:8000"

    # LLM provider selection (consumed in Plan 2)
    llm_stage_a_provider: str = "anthropic"
    llm_stage_a_model: str = "claude-haiku-4-5"
    llm_stage_b_provider: str = "anthropic"
    llm_stage_b_model: str = "claude-sonnet-4-5"

    # MLX placeholder
    mlx_base_url: str = "http://localhost:8081/v1"
    mlx_stage_a_model: str = "mlx-community/Qwen2-VL-2B-Instruct-4bit"
    mlx_stage_b_model: str = "mlx-community/Qwen2-VL-7B-Instruct-4bit"

    @property
    def db_path(self) -> Path:
        return self.ssd_data_dir / "db" / "app.sqlite"


__all__ = ["Settings"]
