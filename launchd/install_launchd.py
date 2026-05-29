"""Install home_photo_repo launchd plists.

Reads .plist.template files from this directory, substitutes
{{PLACEHOLDER}} tokens against a per-user context, validates each rendered
plist with `plutil -lint`, copies to ~/Library/LaunchAgents/, and runs
`launchctl bootstrap gui/<uid>`.

Usage:
    python -m launchd.install_launchd                 # install all 3 services
    python -m launchd.install_launchd worker          # one service only
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_LAUNCHD_DIR = Path(__file__).resolve().parent
_LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

# The three core services. MLX is optional and installed separately if desired.
# Install side keeps this list short — installing MLX requires explicit opt-in.
_SERVICES: tuple[str, ...] = ("worker", "dashboard", "backup")


def substitute(template: str, context: dict[str, str]) -> str:
    """Replace {{KEY}} occurrences using the context dict.

    Raises KeyError if the template references a key not in context.
    """
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(key)
        return context[key]
    return _PLACEHOLDER_RE.sub(replace, template)


def default_context(*, repo_root: Path) -> dict[str, str]:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
    home = str(Path.home())
    uv_path = shutil.which("uv") or f"{home}/.local/bin/uv"
    log_dir = f"{home}/Library/Logs/home_photo_repo"
    return {
        "USER": user,
        "HOME": home,
        "REPO_ROOT": str(repo_root),
        "UV": uv_path,
        "LOG_DIR": log_dir,
    }


def _render_and_install(service: str, ctx: dict[str, str]) -> Path:
    template_path = _LAUNCHD_DIR / f"com.homephoto.{service}.plist.template"
    if not template_path.exists():
        raise FileNotFoundError(template_path)
    rendered = substitute(template_path.read_text(), ctx)
    target = _LAUNCH_AGENTS / f"com.homephoto.{service}.plist"
    _LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    Path(ctx["LOG_DIR"]).mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    # Validate with plutil before booting.
    subprocess.run(["plutil", "-lint", str(target)], check=True)
    return target


def _bootstrap(label: str, plist_path: Path) -> None:
    uid = os.getuid()
    domain = f"gui/{uid}"
    # bootout first in case it's already loaded (idempotent install).
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"],
                   capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)],
                   check=True)


def install(services: list[str] | None = None,
            repo_root: Path | None = None) -> list[Path]:
    services = services or list(_SERVICES)
    repo_root = repo_root or Path(__file__).resolve().parents[1]
    ctx = default_context(repo_root=repo_root)
    installed: list[Path] = []
    for service in services:
        plist = _render_and_install(service, ctx)
        _bootstrap(f"com.homephoto.{service}", plist)
        installed.append(plist)
        print(f"installed: {plist}")
    return installed


def main() -> int:  # pragma: no cover - CLI entrypoint
    services = sys.argv[1:] or None
    install(services)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["default_context", "install", "substitute"]
