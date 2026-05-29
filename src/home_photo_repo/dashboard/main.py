"""Process entrypoint: `python -m home_photo_repo.dashboard.main`."""

from __future__ import annotations

import uvicorn

from home_photo_repo.dashboard.app import create_app
from home_photo_repo.settings_factory import load_settings


def main() -> None:  # pragma: no cover - process entrypoint
    settings = load_settings()
    host, _, port_str = settings.dashboard_bind.partition(":")
    port = int(port_str) if port_str else 8000
    app = create_app(
        db_path=settings.db_path,
        immich_base_url=str(settings.immich_base_url),
        immich_api_key=settings.immich_api_key.get_secret_value(),
    )
    uvicorn.run(app, host=host or "127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
