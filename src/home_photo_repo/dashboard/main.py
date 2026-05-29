"""Process entrypoint: `python -m home_photo_repo.dashboard.main`."""

from __future__ import annotations

import uvicorn

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.settings_factory import load_settings


def main() -> None:  # pragma: no cover - process entrypoint
    settings = load_settings()
    host, sep, port_str = settings.dashboard_bind.partition(":")
    if not sep or not port_str:
        raise RuntimeError(
            f"DASHBOARD_BIND must be in the form 'host:port', got "
            f"{settings.dashboard_bind!r}. Example: '127.0.0.1:8000'."
        )
    try:
        port = int(port_str)
    except ValueError as e:
        raise RuntimeError(
            f"DASHBOARD_BIND port must be an integer, got {port_str!r}"
        ) from e
    app = create_app(
        db_path=settings.db_path,
        immich_base_url=str(settings.immich_base_url),
        immich_api_key=settings.immich_api_key.get_secret_value(),
    )
    uvicorn.run(app, host=host or "127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
