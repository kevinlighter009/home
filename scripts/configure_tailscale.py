"""Configure persistent dashboard access URLs.

Two-tier approach:
  1. mDNS / Bonjour  →  http://home-photo.local:<port>
       Works on the same WiFi with NO software on viewing devices.
       Hostname is persistent even when the LAN IP changes.
       Sets the Mac's Bonjour name once (requires sudo the first time).

  2. Tailscale MagicDNS  →  http://<device>.tail-xyz.ts.net:<port>
       Works anywhere for Tailscale peers.
       Stable hostname even if the Tailscale IP changes.
       Enable MagicDNS at https://login.tailscale.com/admin/dns

The dashboard itself always binds to 0.0.0.0 (all interfaces).

Usage:
    python scripts/configure_tailscale.py [--local-name NAME] [--port PORT] [--env-file PATH]

Options:
    --local-name NAME   Bonjour / mDNS hostname to set (default: home-photo).
                        Skipped if already set to this value.
                        Requires sudo (macOS scutil).
    --port PORT         Dashboard port (default: 8000).
    --env-file PATH     .env file path (default: .env).

Exit codes:
    0  – complete (URLs printed)
    1  – unrecoverable error (.env missing, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

DEFAULT_PORT = 8000
DEFAULT_LOCAL_NAME = "home-food"
DASHBOARD_KEY = "DASHBOARD_BIND"

_TAILSCALE_PATHS = [
    "/opt/homebrew/bin/tailscale",
    "/usr/local/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
]


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------

def _update_env(env_path: Path, key: str, value: str) -> None:
    """Replace or append KEY=value in an .env file, preserving all other lines."""
    text = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# mDNS / Bonjour
# ---------------------------------------------------------------------------

def _get_bonjour_name() -> str | None:
    """Return current Bonjour (LocalHostName) of this Mac."""
    result = subprocess.run(
        ["scutil", "--get", "LocalHostName"],
        capture_output=True, text=True, check=False,
    )
    name = result.stdout.strip()
    return name if result.returncode == 0 and name else None


def _set_bonjour_name(name: str) -> bool:
    """Set LocalHostName via sudo scutil. Returns True on success."""
    print(f"  Setting Bonjour hostname to '{name}' (requires sudo)…")
    result = subprocess.run(
        ["sudo", "scutil", "--set", "LocalHostName", name],
        check=False,
    )
    if result.returncode != 0:
        print(f"  ⚠️  sudo scutil failed (non-interactive shell?). Run once manually:")
        print(f"       sudo scutil --set LocalHostName {name}")
        print(f"       sudo scutil --set ComputerName  {name}")
        return False
    # Also update ComputerName and HostName for consistency
    subprocess.run(["sudo", "scutil", "--set", "ComputerName", name],
                   check=False, capture_output=True)
    subprocess.run(["sudo", "scutil", "--set", "HostName", f"{name}.local"],
                   check=False, capture_output=True)
    return True


def _ensure_bonjour_name(desired: str) -> str | None:
    """Ensure Bonjour name is `desired`; return the active name (or None on failure)."""
    current = _get_bonjour_name()
    if current and current.lower() == desired.lower():
        return current  # already set, nothing to do
    if _set_bonjour_name(desired):
        return desired
    return current  # fall back to whatever it was


# ---------------------------------------------------------------------------
# Tailscale
# ---------------------------------------------------------------------------

def _find_tailscale() -> str | None:
    if (p := shutil.which("tailscale")):
        return p
    for p in _TAILSCALE_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _tailscale_info() -> dict | None:
    """Return dict with 'ip' and 'dns_name' from `tailscale status`, or None."""
    ts = _find_tailscale()
    if not ts:
        return None

    result = subprocess.run(
        [ts, "status", "--json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    self_node = data.get("Self", {})
    # TailscaleIPs is a list; pick the first IPv4
    ips = [ip for ip in self_node.get("TailscaleIPs", []) if ":" not in ip]
    dns_name = self_node.get("DNSName", "").rstrip(".")  # strip trailing dot

    if not ips:
        return None

    return {"ip": ips[0], "dns_name": dns_name or None}


def _install_tailscale() -> None:
    """Install tailscale via Homebrew (best-effort, non-fatal)."""
    brew = shutil.which("brew")
    if not brew:
        print(
            "  ℹ️  Tailscale not found. Install Homebrew (https://brew.sh) then:\n"
            "       brew install tailscale && tailscale login"
        )
        return
    print("  Installing Tailscale via Homebrew…")
    result = subprocess.run([brew, "install", "tailscale"], check=False)
    if result.returncode == 0:
        subprocess.run([brew, "services", "start", "tailscale"],
                       check=False, capture_output=True)
        print("  Tailscale installed. Run `tailscale login` to authenticate,")
        print("  then re-run: make configure-tailscale")
    else:
        print("  brew install tailscale failed — skipping remote access setup.")


def _local_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure persistent dashboard access (mDNS + Tailscale)"
    )
    parser.add_argument("--local-name", default=DEFAULT_LOCAL_NAME,
                        help=f"Bonjour hostname to set (default: {DEFAULT_LOCAL_NAME})")
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

    # Always bind to all interfaces
    _update_env(env_path, DASHBOARD_KEY, f"0.0.0.0:{port}")

    print("\n  ── Dashboard network configuration ──────────────────────────\n")

    # --- Tier 1: mDNS ---
    print("  [1/2] mDNS (home WiFi — no software needed on viewing devices)")
    bonjour_name = _ensure_bonjour_name(args.local_name)
    if bonjour_name:
        local_url = f"http://{bonjour_name}.local"
        print(f"        ✅  http://{bonjour_name}.local  (via nginx on port 80)")
        print(f"             Fallback (no nginx): http://{bonjour_name}.local:{port}")
    else:
        lan_ip = _local_lan_ip()
        local_url = f"http://{lan_ip}:{port}" if lan_ip else f"http://<mac-ip>:{port}"
        print(f"        ⚠️  Bonjour name unavailable — use IP: {local_url}")

    print()

    # --- Tier 2: Tailscale MagicDNS ---
    print("  [2/2] Tailscale MagicDNS (away from home — needs Tailscale on viewing device)")
    ts_info = _tailscale_info()
    if ts_info:
        dns = ts_info["dns_name"]
        ip  = ts_info["ip"]
        if dns:
            print(f"        ✅  http://{dns}:{port}")
            print(f"             (IP: {ip} — but prefer the hostname above, it's stable)")
            print()
            print("        ℹ️  MagicDNS must be enabled in your Tailscale admin panel:")
            print("            https://login.tailscale.com/admin/dns  → Enable MagicDNS")
            print("            Once on, viewing devices with Tailscale can use the hostname.")
        else:
            print(f"        ⚠️  Connected (IP: {ip}) but MagicDNS hostname not assigned.")
            print("            Enable MagicDNS: https://login.tailscale.com/admin/dns")
            print(f"            Until then use: http://{ip}:{port}")
    else:
        ts = _find_tailscale()
        if ts:
            print("        ⚠️  Tailscale installed but not connected.")
            print(f"            Run: {ts} login")
            print("            Then: make configure-tailscale")
        else:
            print("        ℹ️  Tailscale not installed (optional — for remote access only).")
            _install_tailscale()

    print()
    print("  ─────────────────────────────────────────────────────────────")
    print("  Restart the dashboard for DASHBOARD_BIND change to take effect.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
