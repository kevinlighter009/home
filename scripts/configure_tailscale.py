"""Configure dashboard network access and print reachable URLs.

Sets DASHBOARD_BIND=0.0.0.0:<port> in .env so the dashboard is reachable by:
  • Anyone on the same WiFi/LAN  →  http://<local-ip>:<port>
  • Tailscale peers (when away)  →  http://<tailscale-ip>:<port>
  (no Tailscale client required on viewing devices)

Optionally installs Tailscale on the *server* Mac so the host can be reached
remotely, but remote clients never need Tailscale.

Usage:
    python scripts/configure_tailscale.py [--port PORT] [--env-file PATH]

Exit codes:
    0  – .env updated, URLs printed
    1  – unrecoverable error (.env missing)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

DEFAULT_PORT = 8000
DASHBOARD_KEY = "DASHBOARD_BIND"

_TAILSCALE_PATHS = [
    "/opt/homebrew/bin/tailscale",
    "/usr/local/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_env(env_path: Path, key: str, value: str) -> None:
    """Replace or append KEY=value in an .env file."""
    text = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(text, encoding="utf-8")


def _local_lan_ip() -> str | None:
    """Best-effort: return the machine's primary LAN IPv4 address."""
    try:
        # Connect a UDP socket to a public address — no packets sent,
        # but the OS picks the right outbound interface.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


def _tailscale_ip() -> str | None:
    """Return Tailscale IPv4 if the CLI is present and connected, else None."""
    ts = shutil.which("tailscale")
    if not ts:
        for p in _TAILSCALE_PATHS:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                ts = p
                break
    if not ts:
        return None
    result = subprocess.run([ts, "ip", "-4"], capture_output=True, text=True, check=False)
    ip = result.stdout.strip()
    return ip if result.returncode == 0 and ip and not ip.startswith("Error") else None


def _install_tailscale_if_wanted() -> None:
    """Offer to install Tailscale via Homebrew for remote (away-from-home) access."""
    ts = shutil.which("tailscale") or next(
        (p for p in _TAILSCALE_PATHS if os.path.isfile(p)), None
    )
    if ts:
        return  # already installed

    brew = shutil.which("brew")
    if not brew:
        print(
            "  ℹ️  Tailscale not found (optional — needed only for access outside home WiFi).\n"
            "     Install Homebrew (https://brew.sh) then run: brew install tailscale"
        )
        return

    print("  Installing Tailscale for remote access (optional)…")
    result = subprocess.run([brew, "install", "tailscale"], check=False)
    if result.returncode == 0:
        subprocess.run([brew, "services", "start", "tailscale"],
                       check=False, capture_output=True)
        print("  Tailscale installed. Run `tailscale login` to authenticate.")
    else:
        print("  brew install tailscale failed — skipping (remote access won't work).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure DASHBOARD_BIND and print access URLs"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Dashboard port (default: {DEFAULT_PORT})")
    parser.add_argument("--env-file", default=".env",
                        help="Path to the .env file (default: .env)")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"ERROR: {env_path} not found. Run 'make bootstrap' first.", file=sys.stderr)
        return 1

    port = args.port

    # Always bind to all interfaces — no Tailscale client needed on viewers
    bind_value = f"0.0.0.0:{port}"
    _update_env(env_path, DASHBOARD_KEY, bind_value)
    print(f"  DASHBOARD_BIND={bind_value}  (listens on all interfaces)")

    # Print access URLs for reference
    lan_ip = _local_lan_ip()
    ts_ip = _tailscale_ip()

    print("\n  Access URLs:")
    if lan_ip:
        print(f"    📡 Same WiFi/LAN  →  http://{lan_ip}:{port}   (no Tailscale needed)")
    if ts_ip:
        print(f"    🔒 Tailscale      →  http://{ts_ip}:{port}   (when away from home)")
    if not ts_ip:
        print( "    🔒 Tailscale not connected — remote access unavailable.")
        print( "       To enable: install Tailscale on this Mac, run `tailscale login`,")
        print( "       then re-run: make configure-tailscale")

    print("\n  Restart the dashboard for the change to take effect.")

    # Attempt Tailscale install on the server (for remote access), but never block
    if not ts_ip:
        print()
        _install_tailscale_if_wanted()

    return 0


if __name__ == "__main__":
    sys.exit(main())
