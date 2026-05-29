"""Tests for AnthropicProvider. The Anthropic SDK is dependency-injected
via the `client` kwarg, so we never need a real key in tests."""

from __future__ import annotations

from typing import Any

import pytest

from home_photo_repo.llm.providers.anthropic_provider import AnthropicProvider
from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from tests.fixtures.anthropic_stage_a_response import (
    FakeMessage,
    make_text_only_response,
    make_tool_use_response,
)


class FakeAnthropicClient:
    """Duck-types enough of `anthropic.Anthropic` for testing."""

    def __init__(self, response: FakeMessage) -> None:
        self._response = response
        self.messages = self  # SDK exposes .messages.create(...)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeMessage:
        self.calls.append(kwargs)
        return self._response


def _provider(client: FakeAnthropicClient, model: str = "claude-haiku-4-5") -> AnthropicProvider:
    return AnthropicProvider(api_key="test", model=model, client=client)


def test_classify_returns_parsed_dict_from_tool_use() -> None:
    response = make_tool_use_response(
        "classify_food", {"is_food": True, "confidence": 0.92}
    )
    client = FakeAnthropicClient(response)
    p = _provider(client)
    result = p.classify(
        image_bytes=b"fake-image",
        prompt="Is this food?",
        response_schema={
            "type": "object",
            "properties": {
                "is_food": {"type": "boolean"},
                "confidence": {"type": "number"},
            },
            "required": ["is_food", "confidence"],
        },
    )
    assert isinstance(result, ProviderResult)
    assert result.parsed == {"is_food": True, "confidence": 0.92}
    assert result.model == "anthropic:claude-haiku-4-5"
    assert result.input_tokens == 200
    assert result.output_tokens == 12


def test_classify_sends_image_and_prompt_to_sdk() -> None:
    response = make_tool_use_response("classify_food", {"is_food": False, "confidence": 0.1})
    client = FakeAnthropicClient(response)
    _provider(client).classify(
        image_bytes=b"hello-image",
        prompt="Classify.",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    call = client.calls[0]
    # Verify the message structure
    msg = call["messages"][0]
    assert msg["role"] == "user"
    content = msg["content"]
    # Should have one image block + one text block
    image_blocks = [c for c in content if c.get("type") == "image"]
    text_blocks = [c for c in content if c.get("type") == "text"]
    assert len(image_blocks) == 1
    assert len(text_blocks) == 1
    assert text_blocks[0]["text"] == "Classify."
    # Tool was passed
    assert len(call["tools"]) == 1
    assert call["tool_choice"]["type"] == "tool"


def test_classify_raises_provider_error_when_no_tool_use() -> None:
    """If the model returns text instead of tool_use, that's a failure."""
    response = make_text_only_response("Sorry, I can't classify this.")
    client = FakeAnthropicClient(response)
    p = _provider(client)
    with pytest.raises(ProviderError):
        p.classify(
            image_bytes=b"x",
            prompt="x",
            response_schema={"type": "object", "properties": {}, "required": []},
        )


def test_classify_raises_provider_error_on_sdk_exception() -> None:
    class ExplodingClient:
        messages = None

        def __init__(self) -> None:
            self.messages = self

        def create(self, **kwargs: Any) -> Any:
            raise RuntimeError("boom: rate limit or whatever")

    p = AnthropicProvider(api_key="test", model="claude-haiku-4-5", client=ExplodingClient())
    with pytest.raises(ProviderError):
        p.classify(b"", "p", {"type": "object", "properties": {}, "required": []})


def test_name_is_anthropic() -> None:
    client = FakeAnthropicClient(make_tool_use_response("x", {}))
    p = _provider(client)
    assert p.name == "anthropic"
