#!/usr/bin/env python3
"""One-time system setup for a new Mac.

Installs and configures every system-level dependency so the stack
can run with a single `make bootstrap-existing`.

Steps (all idempotent — safe to re-run):
  1. Homebrew        — required prerequisite; prints install URL if missing
  2. uv              — Python package manager (brew install uv)
  3. Docker Desktop  — brew install --cask docker + wait for daemon
  4. nginx           — brew install nginx + symlink config + start on port 80
  5. Bonjour name    — sudo scutil → http://home-food.local on home WiFi
  6. Tailscale       — brew install tailscale (optional, for remote access)

Usage:
    python3 scripts/setup_new_mac.py          # full setup
    python3 scripts/setup_new_mac.py --dry-run  # print what would be done
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT       = Path(__file__).resolve().parent.parent
NGINX_CONF_SRC  = REPO_ROOT / "nginx" / "home-food.conf"
BONJOUR_NAME    = "home-food"
DASHBOARD_PORT  = 8000

# ── helpers ──────────────────────────────────────────────────────────────────

def _banner(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _ok(msg: str)   -> None: print(f"  ✅  {msg}")
def _info(msg: str) -> None: print(f"  ℹ️   {msg}")
def _warn(msg: str) -> None: print(f"  ⚠️   {msg}", file=sys.stderr)
def _err(msg: str)  -> None: print(f"  ❌  {msg}", file=sys.stderr)


def _run(cmd: list[str], *, check: bool = True,
         capture: bool = False, sudo: bool = False) -> subprocess.CompletedProcess:
    if sudo:
        cmd = ["sudo"] + cmd
    return subprocess.run(cmd, check=check,
                          capture_output=capture, text=True)


def _brew(*args: str, check: bool = True, sudo: bool = False) -> subprocess.CompletedProcess:
    brew = shutil.which("brew") or "/opt/homebrew/bin/brew" or "/usr/local/bin/brew"
    return _run([brew] + list(args), check=check, capture=True, sudo=sudo)


# ── Step 1 — Homebrew ────────────────────────────────────────────────────────

def ensure_homebrew() -> bool:
    _banner("Step 1/6 — Homebrew")
    if shutil.which("brew"):
        _ok("Homebrew already installed")
        return True
    # Try common Apple Silicon / Intel paths
    for path in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
        if Path(path).exists():
            _ok(f"Homebrew found at {path}")
            return True

    _err("Homebrew is not installed. It is required for all other steps.")
    print()
    print("  Install it by running this in your terminal, then re-run this script:")
    print()
    print('  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
    print()
    return False


# ── Step 2 — uv ──────────────────────────────────────────────────────────────

def ensure_uv(dry_run: bool) -> None:
    _banner("Step 2/6 — uv (Python package manager)")
    if shutil.which("uv"):
        _ok("uv already installed")
        return
    if dry_run:
        _info("[dry-run] would run: brew install uv")
        return
    print("  Installing uv via Homebrew…")
    _brew("install", "uv")
    _ok("uv installed")


# ── Step 3 — Docker Desktop ──────────────────────────────────────────────────

def _docker_running() -> bool:
    if not shutil.which("docker"):
        return False
    result = subprocess.run(["docker", "info"], capture_output=True, check=False)
    return result.returncode == 0


def ensure_docker(dry_run: bool) -> None:
    _banner("Step 3/6 — Docker Desktop")

    docker_app = Path("/Applications/Docker.app")

    if _docker_running():
        _ok("Docker daemon is running")
        return

    # Install cask if the app is missing
    if not docker_app.exists():
        if dry_run:
            _info("[dry-run] would run: brew install --cask docker")
            return
        print("  Installing Docker Desktop via Homebrew (this may take a few minutes)…")
        _brew("install", "--cask", "docker")
        _ok("Docker Desktop installed")

    # Launch the app so the daemon starts
    if not _docker_running():
        print("  Starting Docker Desktop…")
        if not dry_run:
            subprocess.run(["open", "-a", "Docker"], check=False)
            # Wait up to 90 s for the daemon
            for i in range(18):
                time.sleep(5)
                if _docker_running():
                    _ok("Docker daemon is ready")
                    return
                print(f"    Waiting for Docker… ({(i + 1) * 5}s)", end="\r")
            _warn("Docker Desktop launched but daemon not ready yet.")
            _warn("Open Docker Desktop manually, then re-run this script.")
        else:
            _info("[dry-run] would open Docker Desktop and wait for daemon")


# ── Step 4 — nginx ───────────────────────────────────────────────────────────

def _nginx_bin() -> Path | None:
    prefix = _brew("--prefix", check=True).stdout.strip()
    p = Path(prefix) / "bin" / "nginx"
    return p if p.exists() else None


def _nginx_servers_dir() -> Path:
    prefix = _brew("--prefix", check=True).stdout.strip()
    return Path(prefix) / "etc" / "nginx" / "servers"


def ensure_nginx(dry_run: bool) -> None:
    _banner("Step 4/6 — nginx (reverse proxy → http://home-food.local)")

    # Install
    if not _nginx_bin():
        if dry_run:
            _info("[dry-run] would run: brew install nginx")
        else:
            print("  Installing nginx…")
            _brew("install", "nginx")
            _ok("nginx installed")
    else:
        _ok(f"nginx already installed: {_nginx_bin()}")

    # Symlink config
    servers_dir = _nginx_servers_dir()
    servers_dir.mkdir(parents=True, exist_ok=True)
    link = servers_dir / "home-food.conf"

    if dry_run:
        _info(f"[dry-run] would symlink {NGINX_CONF_SRC} → {link}")
    else:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(NGINX_CONF_SRC)
        _ok(f"Config symlinked: {link}")

    # Test config
    nginx_bin = _nginx_bin()
    if nginx_bin and not dry_run:
        result = subprocess.run([str(nginx_bin), "-t"],
                                capture_output=True, text=True, check=False)
        if result.returncode != 0:
            _err(f"nginx config test failed:\n{result.stderr}")
            return
        _ok("nginx config OK")

    # Start as root daemon (port 80 needs root)
    if dry_run:
        _info("[dry-run] would run: sudo brew services start nginx")
        return

    print("  Starting nginx on port 80 (sudo required)…")
    r = _brew("services", "start", "nginx", check=False, sudo=True)
    if r.returncode == 0:
        _ok("nginx running on port 80")
    else:
        _warn("sudo failed (non-interactive shell). Run manually once:")
        print("      sudo brew services start nginx")


# ── Step 5 — Bonjour hostname ─────────────────────────────────────────────────

def ensure_bonjour(dry_run: bool) -> None:
    _banner(f"Step 5/6 — Bonjour hostname → {BONJOUR_NAME}.local")

    current = subprocess.run(
        ["scutil", "--get", "LocalHostName"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    if current.lower() == BONJOUR_NAME.lower():
        _ok(f"Bonjour name already set to '{BONJOUR_NAME}'")
        return

    _info(f"Current Bonjour name: '{current}' → changing to '{BONJOUR_NAME}'")

    if dry_run:
        _info(f"[dry-run] would run: sudo scutil --set LocalHostName {BONJOUR_NAME}")
        return

    for key, value in [
        ("LocalHostName", BONJOUR_NAME),
        ("ComputerName",  BONJOUR_NAME),
        ("HostName",      f"{BONJOUR_NAME}.local"),
    ]:
        r = subprocess.run(
            ["sudo", "scutil", "--set", key, value],
            check=False,
        )
        if r.returncode != 0:
            _warn(f"sudo scutil --set {key} failed (non-interactive shell).")
            _warn("Run manually once:")
            print(f"      sudo scutil --set LocalHostName {BONJOUR_NAME}")
            print(f"      sudo scutil --set ComputerName  {BONJOUR_NAME}")
            return

    _ok(f"Bonjour name set to '{BONJOUR_NAME}' — reachable at http://{BONJOUR_NAME}.local")


# ── Step 6 — Tailscale ───────────────────────────────────────────────────────

_TAILSCALE_PATHS = [
    "/opt/homebrew/bin/tailscale",
    "/usr/local/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
]


def _find_tailscale() -> str | None:
    if (p := shutil.which("tailscale")):
        return p
    for p in _TAILSCALE_PATHS:
        if Path(p).exists():
            return p
    return None


def ensure_tailscale(dry_run: bool) -> None:
    _banner("Step 6/6 — Tailscale (remote access away from home WiFi)")

    ts = _find_tailscale()
    if not ts:
        if dry_run:
            _info("[dry-run] would run: brew install tailscale")
            return
        print("  Installing Tailscale…")
        _brew("install", "tailscale")
        _brew("services", "start", "tailscale", check=False)
        ts = _find_tailscale()

    if not ts:
        _warn("Tailscale installed but binary not found — open a new shell and re-run.")
        return

    _ok(f"Tailscale found: {ts}")

    # Check if connected
    result = subprocess.run([ts, "ip", "-4"], capture_output=True, text=True, check=False)
    ip = result.stdout.strip()

    if result.returncode == 0 and ip and not ip.startswith("Error"):
        _ok(f"Tailscale connected — IP: {ip}")
        # Update DASHBOARD_BIND to 0.0.0.0 and print URLs
        _update_env_bind()
    else:
        _warn("Tailscale not authenticated. Run:")
        print(f"      {ts} login")
        print( "   Then re-run: make configure-tailscale")


def _update_env_bind() -> None:
    """Ensure DASHBOARD_BIND=0.0.0.0:8000 in .env and print access URLs."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return

    text = env_path.read_text(encoding="utf-8")
    new_line = f"DASHBOARD_BIND=0.0.0.0:{DASHBOARD_PORT}"
    pattern = re.compile(r"^DASHBOARD_BIND\s*=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    env_path.write_text(text, encoding="utf-8")

    # Print access URLs
    lan_ip = _local_lan_ip()
    print()
    print("  Access URLs:")
    print(f"    📡 Home WiFi  →  http://{BONJOUR_NAME}.local  (via nginx, no port)")
    if lan_ip:
        print(f"                    http://{lan_ip}:{DASHBOARD_PORT}  (direct, fallback)")

    ts = _find_tailscale()
    if ts:
        import json
        r = subprocess.run([ts, "status", "--json"], capture_output=True, text=True, check=False)
        try:
            data = json.loads(r.stdout)
            dns = data.get("Self", {}).get("DNSName", "").rstrip(".")
            ts_ip = next(
                (ip for ip in data.get("Self", {}).get("TailscaleIPs", []) if ":" not in ip),
                None,
            )
            if dns:
                print(f"    🔒 Tailscale   →  http://{dns}:{DASHBOARD_PORT}")
            elif ts_ip:
                print(f"    🔒 Tailscale   →  http://{ts_ip}:{DASHBOARD_PORT}")
        except Exception:
            pass


def _local_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time Mac setup: installs all system dependencies"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without making changes")
    args = parser.parse_args()

    if args.dry_run:
        print("  [DRY RUN — no changes will be made]")
    else:
        # Cache sudo credentials once upfront so nginx (brew services) and
        # Bonjour (scutil) steps don't each prompt for a password separately.
        print("  Some steps need sudo (nginx on port 80, hostname). Enter your password once:")
        subprocess.run(["sudo", "-v"], check=False)

    # Step 1: Homebrew is a hard prerequisite
    if not ensure_homebrew():
        return 1  # Cannot continue without brew

    ensure_uv(args.dry_run)
    ensure_docker(args.dry_run)
    ensure_nginx(args.dry_run)
    ensure_bonjour(args.dry_run)
    ensure_tailscale(args.dry_run)

    print()
    print("═" * 60)
    print("  System setup complete.")
    print("  Next: make bootstrap-existing  (Python deps + DB migrations)")
    print("═" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
