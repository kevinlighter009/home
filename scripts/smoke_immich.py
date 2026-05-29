"""Manual smoke test: list the 5 most recently updated assets from Immich.

Run with:
    make smoke-immich
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from home_photo_repo.immich_client import ImmichClient
from home_photo_repo.settings_factory import load_settings


def main() -> None:
    settings = load_settings()
    client = ImmichClient(
        base_url=str(settings.immich_base_url),
        api_key=settings.immich_api_key.get_secret_value(),
    )
    # Look back 30 days so the script works on quiet days.
    since = datetime.now(tz=UTC) - timedelta(days=30)
    assets = client.search_metadata(updated_after=since, size=5, order="desc")
    print(f"Connected to {settings.immich_base_url}; got {len(assets)} most recent assets:")
    for a in assets:
        gps = (
            f"({a.latitude:.4f},{a.longitude:.4f})"
            if a.latitude is not None and a.longitude is not None
            else "(no gps)"
        )
        print(f"  - {a.id}  {a.original_file_name}  updated={a.updated_at}  {gps}")
    client.close()


if __name__ == "__main__":
    main()
