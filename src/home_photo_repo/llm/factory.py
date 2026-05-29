"""Provider factory — chooses Anthropic vs MLX per stage from Settings."""

from __future__ import annotations

from typing import Literal

from home_photo_repo.config import Settings
from home_photo_repo.llm.providers.anthropic_provider import AnthropicProvider
from home_photo_repo.llm.providers.base import VisionLLMProvider
from home_photo_repo.llm.providers.mlx_provider import MLXProvider

Role = Literal["stage_a", "stage_b"]


def build_provider(role: Role, settings: Settings) -> VisionLLMProvider:
    if role == "stage_a":
        provider_name = settings.llm_stage_a_provider
        model = settings.llm_stage_a_model
    elif role == "stage_b":
        provider_name = settings.llm_stage_b_provider
        model = settings.llm_stage_b_model
    else:
        raise ValueError(f"unknown role {role!r}; expected 'stage_a' or 'stage_b'")

    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=model,
        )
    if provider_name == "mlx":
        mlx_model = (
            settings.mlx_stage_a_model if role == "stage_a" else settings.mlx_stage_b_model
        )
        return MLXProvider(base_url=settings.mlx_base_url, model=mlx_model)
    raise ValueError(
        f"unknown provider {provider_name!r}; expected 'anthropic' or 'mlx'"
    )


__all__ = ["Role", "build_provider"]
