"""Manual smoke test: hit the dashboard /healthz route locally.

Assumes the dashboard is already running (`make dev-dashboard` in another
terminal). Verifies the process is up and responding."""

from __future__ import annotations

import sys

import httpx

from home_photo_repo.settings_factory import load_settings


def main() -> int:
    settings = load_settings()
    host, _, port_str = settings.dashboard_bind.partition(":")
    host = host or "127.0.0.1"
    port = int(port_str) if port_str else 8000
    url = f"http://{host}:{port}/healthz"
    try:
        r = httpx.get(url, timeout=2.0)
    except httpx.HTTPError as e:
        print(f"ERROR: dashboard not reachable at {url}: {e}", file=sys.stderr)
        return 2
    if r.status_code != 200:
        print(f"ERROR: {url} returned {r.status_code}", file=sys.stderr)
        return 2
    print(f"OK: {url} → {r.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
