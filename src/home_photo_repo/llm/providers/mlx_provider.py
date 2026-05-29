"""OpenAI-compatible vision provider for a localhost MLX server.

Works against any server speaking the OpenAI Chat Completions wire protocol:
mlx-vlm's `mlx_vlm.server`, mlx-omni-server, llama.cpp's server, LM Studio,
vLLM. We ask the model to respond with strictly JSON matching the supplied
schema (we put the schema into the prompt — OpenAI-compat servers vary in
their structured-output support).
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
)


def _strip_code_fences(text: str) -> str:
    """Strip leading/trailing ```json...``` or ``` fences if present."""
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence and any 'json' marker
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
    if s.endswith("```"):
        s = s[: -3].rstrip()
    return s


class MLXProvider:
    name: str = "mlx"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        # Some local servers don't honor `response_format`; instruct the model
        # in the prompt to emit strict JSON matching the schema. Stage A/B
        # validators handle deviations downstream.
        schema_hint = json.dumps(response_schema, indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            "Respond with ONLY a JSON object matching this schema, no prose:\n"
            f"{schema_hint}"
        )
        body = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                        {"type": "text", "text": full_prompt},
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        url = f"{self._base_url}/chat/completions"
        started = time.perf_counter()
        try:
            response = self._client.post(url, json=body)
        except httpx.HTTPError as e:
            raise ProviderError(f"mlx HTTP error: {e!r}") from e
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise ProviderError(
                f"mlx server returned {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as e:
            raise ProviderError(f"mlx returned non-JSON body: {e!r}") from e

        try:
            content = data["choices"][0]["message"]["content"]
            usage = data["usage"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"mlx response missing expected fields: {e!r}") from e

        try:
            parsed = json.loads(_strip_code_fences(content))
        except ValueError as e:
            raise ProviderError(
                f"mlx model did not emit valid JSON: {content[:200]!r}"
            ) from e
        if not isinstance(parsed, dict):
            raise ProviderError(f"mlx model emitted non-object JSON: {type(parsed).__name__}")

        return ProviderResult(
            parsed=parsed,
            raw=content,
            latency_ms=elapsed_ms,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            model=f"mlx:{self._model}",
        )


__all__ = ["MLXProvider"]
