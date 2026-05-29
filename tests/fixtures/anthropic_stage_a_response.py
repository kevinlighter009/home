"""Recorded shape of an Anthropic SDK response when using tool_use for structured output.

The real SDK returns `anthropic.types.Message` objects; we build a minimal
duck-typed equivalent for tests so we don't depend on SDK internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeUsage:
    input_tokens: int = 200
    output_tokens: int = 12


@dataclass
class FakeContentBlock:
    type: str
    # For type == "tool_use":
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    # For type == "text":
    text: str = ""


@dataclass
class FakeMessage:
    content: list[FakeContentBlock]
    usage: FakeUsage = field(default_factory=FakeUsage)
    model: str = "claude-haiku-4-5"
    stop_reason: str = "tool_use"


def make_tool_use_response(tool_name: str, tool_input: dict[str, Any]) -> FakeMessage:
    return FakeMessage(
        content=[FakeContentBlock(type="tool_use", name=tool_name, input=tool_input)],
    )


def make_text_only_response(text: str) -> FakeMessage:
    return FakeMessage(content=[FakeContentBlock(type="text", text=text)], stop_reason="end_turn")
