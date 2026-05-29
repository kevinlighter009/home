"""Manual smoke test: verify the local MLX server is reachable and classifies
a synthetic image end-to-end.

Run with:
    make smoke-mlx

Assumes either:
  - The MLX launchd service is running (make install-mlx installed it), OR
  - You started the server manually: uv run mlx_vlm.server --model X --port 8081
"""

from __future__ import annotations

import struct
import sys
import time
import zlib

import httpx

from home_photo_repo.llm.providers.mlx_provider import MLXProvider
from home_photo_repo.llm.stage_a import run_stage_a
from home_photo_repo.settings_factory import load_settings


def _make_solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Generate a minimal valid RGB PNG. Same helper smoke_llm uses."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data)
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    r, g, b = rgb
    row = bytes([0]) + bytes([r, g, b]) * width
    raw = row * height
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _wait_for_server(base_url: str, timeout_s: float = 10.0) -> bool:
    """Poll /v1/models until the server responds 200 or timeout."""
    deadline = time.monotonic() + timeout_s
    url = f"{base_url}/models"
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    settings = load_settings()
    base_url = settings.mlx_base_url
    print(f"MLX server: {base_url}")
    print(f"Stage A model: {settings.mlx_stage_a_model}")

    if not _wait_for_server(base_url):
        print(
            f"\nERROR: MLX server at {base_url} not reachable.\n"
            "Start it manually:\n"
            f"    uv run mlx_vlm.server --model {settings.mlx_stage_a_model} --port 8081\n"
            "Or install the launchd service: make install-mlx\n",
            file=sys.stderr,
        )
        return 2

    provider = MLXProvider(
        base_url=base_url, model=settings.mlx_stage_a_model,
    )
    print("Classifying a 256x256 synthetic image (Stage A)...")
    image_bytes = _make_solid_png(256, 256, (255, 0, 255))
    result = run_stage_a(provider, image_bytes=image_bytes)
    print(f"  is_food   = {result.is_food}")
    print(f"  confidence= {result.confidence}")
    print(f"  model     = {result.model}")
    print(f"  latency   = {result.latency_ms}ms")
    print(f"  raw       = {result.raw_json}")
    print("\nMLX round-trip succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
