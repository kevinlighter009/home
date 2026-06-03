"""Install and configure nginx as a reverse proxy for home-food.local.

What this does:
  1. Installs nginx via Homebrew if not present.
  2. Symlinks repo/nginx/home-food.conf into nginx's servers/ include directory.
  3. Starts nginx as a root LaunchDaemon (required for port 80 on macOS).
  4. Verifies nginx is listening on port 80.

Port 80 requires root — the script will prompt for your password once via sudo.

Usage:
    python scripts/install_nginx.py [--uninstall] [--port PORT]

Options:
    --uninstall   Remove the config symlink and stop the nginx service.
    --port PORT   Dashboard port nginx proxies to (default: 8000).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT     = Path(__file__).resolve().parent.parent
NGINX_CONF    = REPO_ROOT / "nginx" / "home-food.conf"
SERVER_NAME   = "home-food.local"
DEFAULT_PORT  = 8000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], *, check: bool = True, capture: bool = False, sudo: bool = False) -> subprocess.CompletedProcess:
    if sudo:
        cmd = ["sudo"] + cmd
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def _brew_prefix() -> Path:
    result = subprocess.run(["brew", "--prefix"], capture_output=True, text=True, check=True)
    return Path(result.stdout.strip())


def _nginx_servers_dir(prefix: Path) -> Path:
    return prefix / "etc" / "nginx" / "servers"


def _nginx_bin(prefix: Path) -> Path:
    return prefix / "bin" / "nginx"


def _nginx_installed(prefix: Path) -> bool:
    return _nginx_bin(prefix).exists()


def _symlink_path(servers_dir: Path) -> Path:
    return servers_dir / "home-food.conf"


def _port_listening(port: int) -> bool:
    """Return True if something is already bound to port."""
    result = subprocess.run(
        ["lsof", "-iTCP", f":{port}", "-sTCP:LISTEN", "-n", "-P"],
        capture_output=True, text=True, check=False,
    )
    return bool(result.stdout.strip())


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def install(dashboard_port: int) -> int:
    # 1. Homebrew
    if not shutil.which("brew"):
        print("ERROR: Homebrew not found. Install from https://brew.sh", file=sys.stderr)
        return 1

    prefix = _brew_prefix()
    servers_dir = _nginx_servers_dir(prefix)

    # 2. Install nginx if needed
    if _nginx_installed(prefix):
        print(f"nginx found: {_nginx_bin(prefix)}")
    else:
        print("Installing nginx via Homebrew…")
        _run(["brew", "install", "nginx"])
        print("nginx installed.")

    # 3. Patch the nginx config with the correct dashboard port if needed
    conf_text = NGINX_CONF.read_text()
    if f"proxy_pass         http://127.0.0.1:{dashboard_port};" not in conf_text:
        # Replace whatever port is there
        import re
        conf_text = re.sub(
            r"proxy_pass\s+http://127\.0\.0\.1:\d+;",
            f"proxy_pass         http://127.0.0.1:{dashboard_port};",
            conf_text,
        )
        NGINX_CONF.write_text(conf_text)
        print(f"Updated nginx config: proxy_pass → port {dashboard_port}")

    # 4. Symlink config into nginx servers/ directory
    servers_dir.mkdir(parents=True, exist_ok=True)
    link = _symlink_path(servers_dir)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(NGINX_CONF)
    print(f"Config symlinked: {link} → {NGINX_CONF}")

    # 5. Test config
    print("Testing nginx config…")
    result = _run([str(_nginx_bin(prefix)), "-t"], check=False, capture=True)
    if result.returncode != 0:
        print(f"ERROR: nginx config test failed:\n{result.stderr}", file=sys.stderr)
        return 1
    print("Config OK.")

    # 6. Start / restart nginx as root daemon (port 80 needs root)
    print("\nStarting nginx on port 80 (sudo required for port < 1024)…")
    if _port_listening(80):
        # Already something on 80 — try reload first
        r = _run(["brew", "services", "restart", "nginx"], check=False, sudo=True)
    else:
        r = _run(["brew", "services", "start", "nginx"], check=False, sudo=True)

    if r.returncode != 0:
        print(
            "\nERROR: failed to start nginx service (sudo requires an interactive terminal).\n"
            "Run this once in your terminal:\n\n"
            "    sudo brew services start nginx\n\n"
            "Then verify with:  curl -s -o /dev/null -w '%{http_code}' http://home-food.local",
            file=sys.stderr,
        )
        return 1

    # Give nginx a moment to bind
    time.sleep(1)
    if _port_listening(80):
        print("\n✅  nginx is running on port 80.")
    else:
        print("\n⚠️  nginx started but port 80 check inconclusive — check: sudo brew services list")

    print(f"\n  Dashboard available at:  http://{SERVER_NAME}")
    print( "  (Make sure Bonjour name is set: make configure-tailscale)")
    print( "  (Make sure the dashboard worker is running: make dev-dashboard)")
    return 0


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def uninstall() -> int:
    if not shutil.which("brew"):
        print("ERROR: Homebrew not found.", file=sys.stderr)
        return 1

    prefix = _brew_prefix()
    link = _symlink_path(_nginx_servers_dir(prefix))

    if link.exists() or link.is_symlink():
        link.unlink()
        print(f"Removed {link}")
    else:
        print(f"Config not found at {link} — nothing to remove.")

    print("Stopping nginx service…")
    _run(["brew", "services", "stop", "nginx"], check=False, sudo=True)
    print("nginx stopped.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Install nginx reverse proxy for home-food.local")
    parser.add_argument("--uninstall", action="store_true", help="Remove config and stop nginx")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Dashboard port to proxy to (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    if args.uninstall:
        return uninstall()
    return install(args.port)


if __name__ == "__main__":
    sys.exit(main())
