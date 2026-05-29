"""Provider factory — chooses Anthropic vs MLX per stage from Settings.

When `settings.llm_fallback_provider` is set AND differs from the primary,
the result is wrapped in a `FallbackProvider` that retries on transient
errors.
"""

from __future__ import annotations

from typing import Literal

from home_photo_repo.config import Settings
from home_photo_repo.llm.providers.anthropic_provider import AnthropicProvider
from home_photo_repo.llm.providers.base import VisionLLMProvider
from home_photo_repo.llm.providers.fallback_provider import FallbackProvider
from home_photo_repo.llm.providers.mlx_provider import MLXProvider

Role = Literal["stage_a", "stage_b"]


def _build_concrete_provider(
    role: Role, provider_name: str, settings: Settings
) -> VisionLLMProvider:
    """Build the specific provider type — no fallback wrapping."""
    if role == "stage_a":
        model = settings.llm_stage_a_model
    elif role == "stage_b":
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


def build_provider(role: Role, settings: Settings) -> VisionLLMProvider:
    """Build the provider for `role`, optionally wrapping in FallbackProvider.

    If `settings.llm_fallback_provider` is set AND differs from the primary,
    the result is a FallbackProvider that tries the primary first and falls
    back to the secondary on transient errors.
    """
    if role == "stage_a":
        primary_name = settings.llm_stage_a_provider
    elif role == "stage_b":
        primary_name = settings.llm_stage_b_provider
    else:
        raise ValueError(f"unknown role {role!r}; expected 'stage_a' or 'stage_b'")

    primary = _build_concrete_provider(role, primary_name, settings)

    fallback_name = settings.llm_fallback_provider
    if not fallback_name or fallback_name == primary_name:
        # No fallback configured, or fallback is the same as primary — no wrapping.
        return primary

    fallback = _build_concrete_provider(role, fallback_name, settings)
    return FallbackProvider(primary=primary, fallback=fallback)


__all__ = ["Role", "build_provider"]
