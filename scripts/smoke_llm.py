"""Manual smoke test: run Stage A on a synthetic image to verify provider config.

Run with:
    make smoke-llm
"""

from __future__ import annotations

import base64
import sys

from home_photo_repo.llm.factory import build_provider
from home_photo_repo.llm.stage_a import run_stage_a
from home_photo_repo.settings_factory import load_settings

# 16x16 solid-magenta PNG, base64-encoded. Pure synthetic — won't classify as food
# but will exercise the entire round-trip (API key, image upload, JSON parse).
_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAH0lEQVQ4jWP8//8/AzZAxh"
    "MnGEYNGDVg1IBRA0YNoCYAAFMWAv8XOmAvAAAAAElFTkSuQmCC"
)


def main() -> int:
    settings = load_settings()
    if settings.anthropic_api_key.get_secret_value() in ("", "replace_me"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        return 2
    provider = build_provider("stage_a", settings)
    print(f"Using provider: {provider.name} (model={settings.llm_stage_a_model})")
    image_bytes = base64.b64decode(_TINY_PNG_BASE64)
    result = run_stage_a(provider, image_bytes=image_bytes)
    print("Stage A result on synthetic image:")
    print(f"  is_food   = {result.is_food}")
    print(f"  confidence= {result.confidence}")
    print(f"  model     = {result.model}")
    print(f"  latency   = {result.latency_ms}ms")
    print(f"  raw       = {result.raw_json}")
    print("\nProvider round-trip succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
