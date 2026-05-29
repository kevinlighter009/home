"""Claude provider using the official Anthropic SDK.

Uses the SDK's tool-use feature to coerce structured JSON output: we declare
a single tool whose input schema matches the desired response shape, then
force the model to call it with `tool_choice={"type": "tool", "name": ...}`.
The tool's `input` is our parsed result.
"""

from __future__ import annotations

import base64
import time
from typing import Any

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
)

_TOOL_NAME = "record_classification"


class AnthropicProvider:
    """VisionLLMProvider implemented against anthropic.Anthropic."""

    name: str = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any = None,
    ) -> None:
        if client is None:
            # Late import so test envs that don't need the SDK don't pay for it.
            from anthropic import Anthropic

            client = Anthropic(api_key=api_key)
        self._client = client
        self._model = model

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        message_content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            },
            {"type": "text", "text": prompt},
        ]
        tool = {
            "name": _TOOL_NAME,
            "description": "Record the structured classification result.",
            "input_schema": response_schema,
        }
        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": message_content}],
                tools=[tool],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
            )
        except Exception as e:  # noqa: BLE001 - re-raise as ProviderError
            raise ProviderError(f"anthropic SDK call failed: {e!r}") from e
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        # Extract the tool_use block.
        tool_use = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                tool_use = block
                break
        if tool_use is None:
            raise ProviderError(
                f"anthropic returned no tool_use block; stop_reason="
                f"{getattr(response, 'stop_reason', '?')!r}"
            )

        parsed = dict(tool_use.input)
        # We don't have the literal JSON string back from the SDK; serialize the
        # parsed dict deterministically so stage_b_raw_json has a useful value.
        import json

        raw = json.dumps(parsed, sort_keys=True)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        return ProviderResult(
            parsed=parsed,
            raw=raw,
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=f"anthropic:{self._model}",
        )


__all__ = ["AnthropicProvider"]
