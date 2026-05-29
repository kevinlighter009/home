"""Manual smoke test: run Stage A on a synthetic image to verify provider config.

Run with:
    make smoke-llm
"""

from __future__ import annotations

import struct
import sys
import zlib

from home_photo_repo.llm.factory import build_provider
from home_photo_repo.llm.stage_a import run_stage_a
from home_photo_repo.settings_factory import load_settings


def _make_solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Produce a minimal valid RGB PNG of the given dimensions, solid `rgb` color.

    Uses only stdlib (struct + zlib). We need a non-trivial size because
    Anthropic's vision API rejects too-tiny images with "Could not process image".
    """
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data)
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    # IHDR: width, height, bit_depth=8, color_type=2 (RGB), compression=0, filter=0, interlace=0
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    # Image data: each row = [filter_byte=0] + R G B for each pixel
    r, g, b = rgb
    row = bytes([0]) + bytes([r, g, b]) * width
    raw = row * height
    idat = zlib.compress(raw, 9)

    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main() -> int:
    settings = load_settings()
    if settings.anthropic_api_key.get_secret_value() in ("", "replace_me"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        return 2
    provider = build_provider("stage_a", settings)
    print(f"Using provider: {provider.name} (model={settings.llm_stage_a_model})")
    # 256x256 solid magenta PNG — large enough for Anthropic's vision API to
    # accept, but obviously not food. Exercises the full round-trip.
    image_bytes = _make_solid_png(256, 256, (255, 0, 255))
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
