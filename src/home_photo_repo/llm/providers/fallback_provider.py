"""FallbackProvider — composes two VisionLLMProviders with auto-fallback.

The primary provider is tried first. If it raises a *transient* error
(connection refused, timeout, 5xx HTTP response), the fallback is invoked.
Configuration errors (4xx auth, malformed responses) propagate so the
operator can see them.

Usage:
    primary = MLXProvider(base_url="http://localhost:8081/v1", model=...)
    fallback = AnthropicProvider(api_key=..., model=...)
    provider = FallbackProvider(primary=primary, fallback=fallback)
"""

from __future__ import annotations

import logging
from typing import Any

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
    VisionLLMProvider,
)

log = logging.getLogger(__name__)

# Substrings in a ProviderError message that indicate a transient failure
# where falling over to another provider could succeed.
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "ConnectError",
    "ConnectTimeout",
    "TimeoutException",
    "ReadTimeout",
    "Network is unreachable",
    "Connection refused",
    "connection refused",
    "returned 500",
    "returned 502",
    "returned 503",
    "returned 504",
)


def _looks_transient(error: BaseException) -> bool:
    msg = str(error)
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


class FallbackProvider(VisionLLMProvider):
    """Try primary, fall back to secondary on transient failures only."""

    name: str

    def __init__(
        self,
        *,
        primary: VisionLLMProvider,
        fallback: VisionLLMProvider,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self.name = f"{primary.name}→{fallback.name}"

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        try:
            return self._primary.classify(
                image_bytes=image_bytes,
                prompt=prompt,
                response_schema=response_schema,
                max_tokens=max_tokens,
            )
        except ProviderError as primary_err:
            if not _looks_transient(primary_err):
                # Not a transient error — propagate so operator notices
                # configuration / model problems immediately.
                raise
            log.warning(
                "primary provider %s failed (%s); falling back to %s",
                self._primary.name, primary_err, self._fallback.name,
            )
            try:
                return self._fallback.classify(
                    image_bytes=image_bytes,
                    prompt=prompt,
                    response_schema=response_schema,
                    max_tokens=max_tokens,
                )
            except ProviderError as fallback_err:
                raise ProviderError(
                    f"both providers failed — primary {self._primary.name}: "
                    f"{primary_err!r}; fallback {self._fallback.name}: {fallback_err!r}"
                ) from fallback_err


__all__ = ["FallbackProvider"]
