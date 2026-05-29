"""Tests for MLXProvider — OpenAI-compatible HTTP client for a localhost MLX server."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
import respx

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.providers.mlx_provider import MLXProvider

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _provider(model: str = "mlx-community/Qwen2-VL-2B-Instruct-4bit") -> MLXProvider:
    return MLXProvider(base_url="http://localhost:8081/v1", model=model)


@respx.mock
def test_classify_returns_parsed_dict() -> None:
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_load_fixture("openai_compat_stage_a_response.json"))
    )
    result = _provider().classify(
        image_bytes=b"fake-image",
        prompt="Is this food?",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    assert isinstance(result, ProviderResult)
    assert result.parsed == {"is_food": True, "confidence": 0.88}
    assert result.model.startswith("mlx:")
    assert result.input_tokens == 180
    assert result.output_tokens == 24


@respx.mock
def test_classify_sends_base64_image_in_messages() -> None:
    route = respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_load_fixture("openai_compat_stage_a_response.json"))
    )
    _provider().classify(
        image_bytes=b"hello",
        prompt="classify",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    body = json.loads(route.calls.last.request.content)
    message = body["messages"][0]
    assert message["role"] == "user"
    content = message["content"]
    image_part = next(c for c in content if c["type"] == "image_url")
    text_part = next(c for c in content if c["type"] == "text")
    assert text_part["text"].startswith("classify")
    expected_b64 = base64.standard_b64encode(b"hello").decode("ascii")
    assert image_part["image_url"]["url"] == f"data:image/jpeg;base64,{expected_b64}"


@respx.mock
def test_classify_raises_on_http_error() -> None:
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(ProviderError):
        _provider().classify(b"", "p", {"type": "object", "properties": {}, "required": []})


@respx.mock
def test_classify_raises_when_content_not_json() -> None:
    bad = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "I think yes!"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=bad)
    )
    with pytest.raises(ProviderError):
        _provider().classify(b"", "p", {"type": "object", "properties": {}, "required": []})


def test_name_is_mlx() -> None:
    assert _provider().name == "mlx"


@respx.mock
def test_classify_strips_markdown_code_fences_from_json() -> None:
    """Local models sometimes wrap JSON in ```json ... ``` fences. Strip them."""
    fixture = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant",
                     "content": "```json\n{\"is_food\": true, \"confidence\": 0.9}\n```"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    result = _provider().classify(
        image_bytes=b"x", prompt="p",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    assert result.parsed == {"is_food": True, "confidence": 0.9}


@respx.mock
def test_classify_strips_plain_code_fences_too() -> None:
    """Some models use ``` without 'json' marker."""
    fixture = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant",
                     "content": "```\n{\"x\": 1}\n```"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    result = _provider().classify(
        image_bytes=b"x", prompt="p",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    assert result.parsed == {"x": 1}
