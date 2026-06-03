"""Application configuration loaded from environment / .env file.

Secrets are wrapped in `SecretStr` so their values do not appear in repr/log output.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for pipeline thresholds. Settings and pipeline both
# read from these so defaults stay in lockstep.
DEFAULT_STAGE_A_FOOD_THRESHOLD: float = 0.6
DEFAULT_STAGE_B_REVIEW_THRESHOLD: float = 0.7


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Immich connection
    immich_base_url: HttpUrl

    # --- API keys (multi-user) -------------------------------------------
    # Preferred: IMMICH_API_KEYS=key1,key2,key3  (one key per Immich user)
    # The worker resolves each key to a username via /api/users/me at startup.
    # No labels needed — just add a key for each user who joins.
    #
    # Legacy fallback (single-user): IMMICH_API_KEY=key
    # Both are accepted; IMMICH_API_KEYS takes precedence if set.
    # -----------------------------------------------------------------------
    immich_api_keys: SecretStr = SecretStr("")   # preferred: comma-separated list
    immich_api_key: SecretStr = SecretStr("")    # legacy single-key fallback

    # Other provider keys
    anthropic_api_key: SecretStr = SecretStr("")
    google_places_api_key: SecretStr = SecretStr("")

    # Storage
    ssd_data_dir: Path

    # Worker tunables
    poll_interval_seconds: int = 300
    backfill_batch_size: int = 100
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD
    stage_b_confidence_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD
    place_match_ambiguous_threshold_m: int = 50
    curated_place_default_radius_m: int = 50
    google_places_search_radius_m: int = 150
    anthropic_rate_limit_per_minute: int = 30
    dashboard_bind: str = "127.0.0.1:8000"

    # LLM provider selection
    llm_stage_a_provider: str = "mlx"
    llm_stage_a_model: str = "claude-haiku-4-5"
    llm_stage_b_provider: str = "mlx"
    llm_stage_b_model: str = "claude-sonnet-4-5"
    llm_fallback_provider: str = "anthropic"

    # MLX
    mlx_base_url: str = "http://localhost:8081/v1"
    mlx_stage_a_model: str = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
    mlx_stage_b_model: str = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"

    @property
    def db_path(self) -> Path:
        return self.ssd_data_dir / "db" / "app.sqlite"

    @property
    def all_api_keys_list(self) -> list[str]:
        """All configured Immich API keys, deduped, in order.

        Resolution order:
        1. IMMICH_API_KEYS (comma-separated, preferred for multi-user)
        2. IMMICH_API_KEY  (legacy single-key fallback)

        Empty / blank entries and duplicates are silently dropped.
        """
        keys: list[str] = []

        multi = self.immich_api_keys.get_secret_value().strip()
        if multi:
            for k in multi.split(","):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)

        # Fall back to legacy single-key only when the new var is absent.
        if not keys:
            single = self.immich_api_key.get_secret_value().strip()
            if single:
                keys.append(single)

        return keys


__all__ = [
    "DEFAULT_STAGE_A_FOOD_THRESHOLD",
    "DEFAULT_STAGE_B_REVIEW_THRESHOLD",
    "Settings",
]
