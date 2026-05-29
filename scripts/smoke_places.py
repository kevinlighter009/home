"""Manual smoke test: run one Google Places Nearby Search to verify the API
key and Cloud project setup.

Run with:
    make smoke-places                    # uses default San Francisco coords
    make smoke-places ARGS='--lat 40.7 --lng -74.0'
"""

from __future__ import annotations

import argparse
import sys

from home_photo_repo.places.google_places import GooglePlacesClient
from home_photo_repo.settings_factory import load_settings

_DEFAULT_LAT = 37.7955  # SF Ferry Building
_DEFAULT_LNG = -122.3937


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=_DEFAULT_LAT)
    parser.add_argument("--lng", type=float, default=_DEFAULT_LNG)
    parser.add_argument("--radius", type=int, default=150)
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero if zero candidates are returned.")
    args = parser.parse_args()

    settings = load_settings()
    key = settings.google_places_api_key.get_secret_value()
    if not key or key == "replace_me":
        print("ERROR: GOOGLE_PLACES_API_KEY not set in .env", file=sys.stderr)
        return 2

    client = GooglePlacesClient(api_key=key)
    print(f"Searching near ({args.lat}, {args.lng}) within {args.radius}m...")
    results = client.search_nearby(
        latitude=args.lat, longitude=args.lng, radius_m=args.radius
    )
    print(f"Got {len(results)} place(s):")
    for p in results:
        print(f"  - {p.name}  ({p.latitude:.4f}, {p.longitude:.4f})  "
              f"types={','.join(p.types[:3])}")
        if p.address:
            print(f"      {p.address}")
    client.close()
    if results:
        print("\nGoogle Places round-trip succeeded.")
        return 0
    print("\nNo results returned. (Try a denser urban area to verify the key.)")
    return 2 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
