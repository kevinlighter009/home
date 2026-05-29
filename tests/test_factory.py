"""Tests for build_provider — chooses Anthropic vs MLX from Settings."""

from __future__ import annotations

import pytest

from home_photo_repo.llm.factory import build_provider
from home_photo_repo.llm.providers.anthropic_provider import AnthropicProvider
from home_photo_repo.llm.providers.mlx_provider import MLXProvider


def _make_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str):
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_factory_test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", overrides.get("anthropic_key", "fake-anthropic"))
    for k, v in overrides.items():
        if k != "anthropic_key":
            monkeypatch.setenv(k, v)
    from home_photo_repo.config import Settings

    return Settings()  # type: ignore[call-arg]


def test_build_anthropic_provider_for_stage_a(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(
        monkeypatch,
        LLM_STAGE_A_PROVIDER="anthropic",
        LLM_STAGE_A_MODEL="claude-haiku-4-5",
    )
    p = build_provider("stage_a", s)
    assert isinstance(p, AnthropicProvider)
    assert p.name == "anthropic"


def test_build_mlx_provider_for_stage_b(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(
        monkeypatch,
        LLM_STAGE_B_PROVIDER="mlx",
        LLM_STAGE_B_MODEL="mlx-community/Qwen2-VL-7B-Instruct-4bit",
    )
    p = build_provider("stage_b", s)
    assert isinstance(p, MLXProvider)
    assert p.name == "mlx"


def test_build_provider_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch, LLM_STAGE_A_PROVIDER="gemini")
    with pytest.raises(ValueError):
        build_provider("stage_a", s)


def test_build_provider_rejects_unknown_role(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch)
    with pytest.raises(ValueError):
        build_provider("stage_z", s)  # type: ignore[arg-type]
