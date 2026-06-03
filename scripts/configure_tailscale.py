"""Install Tailscale (if absent) and write the machine's Tailscale IPv4 address
into .env as DASHBOARD_BIND=<ip>:<port>.

Behaviour:
  • If `tailscale` is not found in PATH or common install locations, installs it
    via `brew install tailscale` (Homebrew formula — no GUI needed).
  • If Tailscale is installed but not connected/authenticated, prints clear
    next-step instructions and exits with code 2 (non-fatal for make bootstrap).
  • If connected, rewrites the DASHBOARD_BIND line in .env and prints the URL.

Usage:
    python scripts/configure_tailscale.py [--port PORT] [--env-file PATH]

Exit codes:
    0  – .env updated successfully
    1  – unrecoverable error (e.g., .env missing, brew not found)
    2  – Tailscale installed but not yet authenticated (user action needed)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_PORT = 8000
DASHBOARD_KEY = "DASHBOARD_BIND"

# Locations where the Tailscale CLI might live even when not on PATH
_EXTRA_PATHS = [
    "/opt/homebrew/bin/tailscale",          # brew formula (Apple Silicon)
    "/usr/local/bin/tailscale",             # brew formula (Intel)
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",  # GUI app / cask
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_tailscale() -> str | None:
    """Return path to `tailscale` binary, or None if not found."""
    if (p := shutil.which("tailscale")):
        return p
    for p in _EXTRA_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _install_tailscale() -> str:
    """Install tailscale via Homebrew formula. Returns binary path."""
    brew = shutil.which("brew")
    if not brew:
        print(
            "ERROR: Homebrew is not installed and Tailscale was not found.\n"
            "  Install Homebrew first: https://brew.sh\n"
            "  Then re-run 'make bootstrap' (or 'make configure-tailscale').",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Installing Tailscale via Homebrew…")
    result = subprocess.run([brew, "install", "tailscale"], check=False)
    if result.returncode != 0:
        print(
            "ERROR: `brew install tailscale` failed. "
            "Check the output above and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    # After brew formula install the daemon must be started
    # (brew services or launchctl — try both silently)
    subprocess.run(
        [brew, "services", "start", "tailscale"],
        check=False, capture_output=True,
    )

    ts = _find_tailscale()
    if not ts:
        print(
            "ERROR: tailscale installed but binary still not found — "
            "open a new shell and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Tailscale installed at {ts}")
    return ts


def _get_tailscale_ip(ts_bin: str) -> str | None:
    """Return IPv4 address from `tailscale ip -4`, or None if not connected."""
    result = subprocess.run(
        [ts_bin, "ip", "-4"],
        capture_output=True, text=True, check=False,
    )
    ip = result.stdout.strip()
    if result.returncode == 0 and ip and not ip.startswith("Error"):
        return ip
    return None


def _update_env(env_path: Path, key: str, value: str) -> None:
    """Replace or append KEY=value in an .env file (preserves all other lines)."""
    text = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    new_line = f"{key}={value}"

    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"

    env_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install Tailscale and configure DASHBOARD_BIND in .env"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Dashboard port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--env-file", default=".env",
        help="Path to the .env file (default: .env)",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(
            f"ERROR: {env_path} not found. Run 'make bootstrap' first.",
            file=sys.stderr,
        )
        return 1

    # 1. Locate or install tailscale
    ts_bin = _find_tailscale()
    if ts_bin:
        print(f"Tailscale found: {ts_bin}")
    else:
        print("Tailscale not found — installing…")
        ts_bin = _install_tailscale()

    # 2. Fetch IP
    ip = _get_tailscale_ip(ts_bin)
    if not ip:
        print(
            "\n⚠️  Tailscale is installed but this machine is not connected.\n"
            "   To authenticate:\n"
            f"     {ts_bin} login\n"
            "   (A browser window will open — log in with your Tailscale account.)\n"
            "   Then re-run:\n"
            "     make configure-tailscale\n"
            "   DASHBOARD_BIND has NOT been updated.",
            file=sys.stderr,
        )
        return 2  # non-fatal: bootstrap still finishes

    # 3. Write to .env
    bind_value = f"{ip}:{args.port}"
    _update_env(env_path, DASHBOARD_KEY, bind_value)
    print(
        f"\n✅  DASHBOARD_BIND set to {bind_value}\n"
        f"   Dashboard will be reachable at: http://{bind_value}\n"
        "   (Restart the dashboard for the change to take effect.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
