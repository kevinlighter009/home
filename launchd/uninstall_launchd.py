"""Uninstall home_photo_repo launchd plists.

Reverses install_launchd: runs `launchctl bootout` for each service and
deletes the copied plist from ~/Library/LaunchAgents/.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
# Uninstall side includes 'mlx' even though the default install doesn't —
# `make uninstall-launchd` should clean up MLX if it was previously installed.
_SERVICES: tuple[str, ...] = ("worker", "dashboard", "backup", "mlx")


def uninstall(services: list[str] | None = None) -> list[str]:
    services = services or list(_SERVICES)
    uid = os.getuid()
    domain = f"gui/{uid}"
    removed: list[str] = []
    for service in services:
        label = f"com.homephoto.{service}"
        plist = _LAUNCH_AGENTS / f"{label}.plist"
        # bootout — ignore errors if it wasn't loaded.
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"],
                       capture_output=True)
        if plist.exists():
            plist.unlink()
            removed.append(label)
            print(f"removed: {plist}")
    return removed


def main() -> int:  # pragma: no cover
    services = sys.argv[1:] or None
    uninstall(services)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["uninstall"]
