# Plan 5 — Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the worker + dashboard auto-start at login via macOS launchd, run a nightly Postgres backup, support `make bootstrap-existing` for new-Mac migration with an already-populated SSD, and document day-2 operations end-to-end.

**Architecture:** launchd plists shipped as `.template` files with `{{USER}}`, `{{HOME}}`, `{{REPO_ROOT}}`, `{{UV}}` placeholders; `make install-launchd` substitutes them via a small Python script, copies to `~/Library/LaunchAgents/`, and `launchctl bootstrap gui/<uid>`s each one. Three services run permanently (worker, dashboard, backup); a fourth (MLX server) is optional. `make uninstall-launchd` reverses; `make logs` tails the unified log directory. The backup script wraps `docker exec immich_postgres pg_dumpall` and rotates dumps older than 14 days.

**Tech Stack:** macOS launchd, bash, Python stdlib for the plist generator, `docker` CLI for the backup. No new runtime deps.

**Spec reference:** `docs/specs/2026-05-28-home-photo-repo-design.md` — §6.5 (scheduling — plists, ThrottleInterval, backup target), §11 (dev workflow including `bootstrap-existing`), §12 (backups + migration).

**Plan 4 follow-ups bundled in:** items #1 (db_conn context manager), #2 (drop `DashboardDeps.get_immich`), #3 (centralize `VALID_VENUE_TYPES`) from `docs/plans/2026-05-28-plan-4-followups.md`. These quality refactors land in Task 1 before the operations work.

**Out of scope:**
- Cloud-backup-of-the-SSD as a project concern (manual rclone is mentioned in docs but not automated)
- Webhook ingestion (spec deferral)
- LAN-exposed dashboard / auth (spec deferral)
- Plan 2 follow-up #1 (Stage B candidate prompting) — separate mini-plan

**Definition of done:**
- `make install-launchd` installs 3 plists (worker, dashboard, backup); each runs and stays running.
- `make uninstall-launchd` removes them cleanly.
- `make logs` tails all three log files concurrently.
- `make bootstrap-existing` works when `app.sqlite` already exists on the SSD (no destructive re-init).
- Nightly backup script produces a timestamped `.sql.gz` file in `$SSD_DATA_DIR/../immich/backups/` and prunes dumps older than 14 days.
- `docs/operations.md` covers install / uninstall / logs / manual backup / restore / new-Mac migration / MLX setup / troubleshooting.
- Plan 4 follow-ups #1, #2, #3 applied.
- All tests pass; ruff + mypy clean.

---

## File map

| Path | Created in task | Responsibility |
|---|---|---|
| `src/home_photo_repo/places/types.py` (modify) | 1 | Export `VALID_VENUE_TYPES` constant |
| `src/home_photo_repo/places/cli.py` (modify) | 1 | Import `VALID_VENUE_TYPES` instead of local copy |
| `src/home_photo_repo/places/matcher.py` (modify) | 1 | Same |
| `src/home_photo_repo/dashboard/routes/places_editor.py` (modify) | 1 | Same |
| `src/home_photo_repo/dashboard/deps.py` (modify) | 1 | Add `db_conn()` context manager; remove `get_immich()` |
| `src/home_photo_repo/dashboard/routes/*.py` (modify, all 7) | 1 | Use `with deps.db_conn() as conn:` instead of manual generator dance |
| `tests/test_places_*.py` (modify if needed) | 1 | No assertion changes; centralization just shifts where the constant lives |
| `launchd/com.homephoto.worker.plist.template` | 2 | Template with substitution placeholders |
| `launchd/com.homephoto.dashboard.plist.template` | 3 | Same |
| `launchd/com.homephoto.backup.plist.template` | 4 | StartCalendarInterval at 03:00 |
| `launchd/install_launchd.py` | 2 | Python script that substitutes placeholders, copies plists, runs `launchctl bootstrap` |
| `launchd/uninstall_launchd.py` | 2 | Reverse: `launchctl bootout` + remove copied plists |
| `Makefile` (modify) | 2, 6, 7 | New targets: `install-launchd`, `uninstall-launchd`, `logs`, `bootstrap-existing`, `backup-now` |
| `scripts/backup_postgres.sh` | 4 | Wraps `docker exec immich_postgres pg_dumpall` + rotates |
| `tests/test_install_launchd.py` | 2 | Substitution produces a valid plist with no remaining placeholders |
| `tests/test_backup_script.py` | 4 | `bash -n` syntax check + dry-run mode produces expected commands |
| `docs/operations.md` | 8 | install / uninstall / backup / restore / migrate / MLX / troubleshooting |
| `README.md` (modify) | 9 | Plan 5 status, ops reference |
| `docs/SETUP.md` (modify) | 9 | Reference operations.md from final-mile checklist |

---

## Conventions

- Repo root: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home`.
- `from __future__ import annotations` at the top of every new `.py`.
- Plist placeholders: `{{USER}}`, `{{HOME}}`, `{{REPO_ROOT}}`, `{{UV}}`, `{{LOG_DIR}}`.
- launchd Label namespacing: `com.homephoto.<service>` (worker / dashboard / backup / mlx).
- Log directory: `${HOME}/Library/Logs/home_photo_repo/` for all services.
- Substitution script writes to `~/Library/LaunchAgents/com.homephoto.<service>.plist`.

---

## Task 1: Plan 4 follow-ups (db_conn context manager + dead-code cleanup + centralize VALID_VENUE_TYPES)

Bundle the three Important quality items into one focused commit before the operations work.

### Files
- Modify: `src/home_photo_repo/places/types.py`
- Modify: `src/home_photo_repo/places/cli.py`
- Modify: `src/home_photo_repo/places/matcher.py`
- Modify: `src/home_photo_repo/dashboard/routes/places_editor.py`
- Modify: `src/home_photo_repo/dashboard/deps.py`
- Modify: `src/home_photo_repo/dashboard/routes/map_view.py`
- Modify: `src/home_photo_repo/dashboard/routes/place.py`
- Modify: `src/home_photo_repo/dashboard/routes/feed.py`
- Modify: `src/home_photo_repo/dashboard/routes/review.py`
- Modify: `src/home_photo_repo/dashboard/routes/places_editor.py`
- Modify: `src/home_photo_repo/dashboard/routes/status.py`

### Step 1: Add `VALID_VENUE_TYPES` to `src/home_photo_repo/places/types.py`

At the bottom of the file (above `__all__`), add:

```python
VALID_VENUE_TYPES: tuple[str, ...] = (
    "home", "office", "friend_place", "restaurant", "outdoor", "other"
)
```

And update `__all__`:

```python
__all__ = ["CuratedPlace", "MatchResult", "NearbyPlace", "VALID_VENUE_TYPES"]
```

### Step 2: Replace local copies

In `src/home_photo_repo/places/cli.py`:

Find:
```python
_VALID_TYPES = ("home", "office", "friend_place", "restaurant", "outdoor", "other")
```
Delete that line. Add to the imports:
```python
from home_photo_repo.places.types import VALID_VENUE_TYPES as _VALID_TYPES
```
(The alias preserves the existing `_VALID_TYPES` name used elsewhere in the file, so no other changes are needed.)

In `src/home_photo_repo/places/matcher.py`:

Find:
```python
_CURATED_VENUE_TYPES = {"home", "office", "friend_place", "restaurant", "outdoor", "other"}
```
Replace with:
```python
from home_photo_repo.places.types import VALID_VENUE_TYPES

_CURATED_VENUE_TYPES = set(VALID_VENUE_TYPES)
```
(Move the new import into the module's existing import block; ruff will sort it.)

In `src/home_photo_repo/dashboard/routes/places_editor.py`:

Find:
```python
_VALID_TYPES = ("home", "office", "friend_place", "restaurant", "outdoor", "other")
```
Delete. Add to the imports:
```python
from home_photo_repo.places.types import VALID_VENUE_TYPES as _VALID_TYPES
```

### Step 3: Add `db_conn` context manager to `DashboardDeps`

In `src/home_photo_repo/dashboard/deps.py`, replace the entire file with:

```python
"""Request-scoped dependencies for dashboard routes.

A fresh sqlite3 connection per request keeps things simple — SQLite is
fast for open/close, and WAL mode (set by `get_connection`) lets the
dashboard read concurrently with the worker writing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from home_photo_repo.db import get_connection


class DashboardDeps:
    """Configuration injected into each route via FastAPI Depends.

    Holds immutable config (paths, URLs); creates per-request connections.
    """

    def __init__(self, *, db_path: Path, immich_base_url: str, immich_api_key: str) -> None:
        self.db_path = db_path
        self.immich_base_url = immich_base_url
        self.immich_api_key = immich_api_key

    @contextmanager
    def db_conn(self) -> Iterator[sqlite3.Connection]:
        """Yield a sqlite3 connection, closing it on exit (success or exception)."""
        conn = get_connection(self.db_path)
        try:
            yield conn
        finally:
            conn.close()


__all__ = ["DashboardDeps"]
```

Note: the old `get_db()` generator and unused `get_immich()` method are gone. `ImmichClient` import is removed (no longer needed here).

### Step 4: Update each route to use `with deps.db_conn() as conn:`

There are 7 routes to update. The pattern for each:

**Find** (in each route file — `map_view.py`, `place.py`, `feed.py`, `review.py` (twice — list and submit), `places_editor.py` (three times — list, add, delete), `status.py`):

```python
    gen = deps.get_db()
    conn = next(gen)
    try:
        # ... conn.execute(...) ...
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)
```

**Replace** with:

```python
    with deps.db_conn() as conn:
        # ... conn.execute(...) ...
```

(Indentation drops by one level inside the `with` block.)

Also, in EACH route file, you can remove `import contextlib` if it's no longer used (it's only used for the suppress in the old pattern). The implementer should grep each route for `contextlib` after changes and remove unused imports.

### Step 5: Run + lint + typecheck + commit

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

Expected: all 159 tests still pass; mypy + ruff clean.

```bash
git add src/home_photo_repo/places/types.py \
        src/home_photo_repo/places/cli.py \
        src/home_photo_repo/places/matcher.py \
        src/home_photo_repo/dashboard/deps.py \
        src/home_photo_repo/dashboard/routes/
git commit -m "refactor: db_conn context manager + drop dead get_immich + centralize VALID_VENUE_TYPES

Plan 4 follow-ups #1, #2, #3. Replaces the manual generator dance
across 7 dashboard routes with a single contextmanager; removes the
never-called DashboardDeps.get_immich; defines VALID_VENUE_TYPES once
in places/types.py and imports everywhere."
```

---

## Task 2: launchd template substitution + Makefile install/uninstall

This task lays the foundation: a Python script that substitutes placeholders in a `.plist.template` file, validates the output with `plutil -lint`, and runs `launchctl bootstrap`. Tests cover the substitution; the actual `make install-launchd` invocation is documented in Task 8.

### Files
- Create: `launchd/__init__.py` (so the package can hold the script)
- Create: `launchd/install_launchd.py`
- Create: `launchd/uninstall_launchd.py`
- Create: `tests/test_install_launchd.py`
- Modify: `Makefile` (add targets — recipes wire to the scripts; concrete plists arrive in Tasks 3/4/5)

### Step 1: Write the failing test — `tests/test_install_launchd.py`

```python
"""Tests for the launchd template substitution script."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHD_DIR = REPO_ROOT / "launchd"


def test_substitute_replaces_all_placeholders(tmp_path: Path) -> None:
    """substitute(template, context) returns the template with all {{X}}
    placeholders replaced; no {{ left in output."""
    from launchd.install_launchd import substitute

    template = (
        "<key>USER</key><string>{{USER}}</string>\n"
        "<key>HOME</key><string>{{HOME}}</string>\n"
        "<key>REPO_ROOT</key><string>{{REPO_ROOT}}</string>\n"
    )
    result = substitute(template, {"USER": "alice", "HOME": "/Users/alice",
                                   "REPO_ROOT": "/Users/alice/repo"})
    assert "{{" not in result
    assert "alice" in result
    assert "/Users/alice/repo" in result


def test_substitute_raises_on_missing_placeholder() -> None:
    """If the context is missing a placeholder used in the template,
    substitute raises KeyError with the missing key's name."""
    from launchd.install_launchd import substitute
    with pytest.raises(KeyError) as exc_info:
        substitute("hello {{MISSING}}", {})
    assert "MISSING" in str(exc_info.value)


def test_default_context_has_required_keys() -> None:
    """default_context() returns a dict with USER, HOME, REPO_ROOT, UV, LOG_DIR."""
    from launchd.install_launchd import default_context

    ctx = default_context(repo_root=Path("/tmp/test"))
    for key in ("USER", "HOME", "REPO_ROOT", "UV", "LOG_DIR"):
        assert key in ctx
        assert ctx[key]  # non-empty


def test_worker_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    """The committed worker template, when substituted, is well-formed XML
    that `plutil -lint` accepts as a valid plist."""
    from launchd.install_launchd import default_context, substitute

    # Worker template lands in Task 3 — if it doesn't exist yet, skip.
    template_path = LAUNCHD_DIR / "com.homephoto.worker.plist.template"
    if not template_path.exists():
        pytest.skip("worker template not yet created (Task 3)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected the plist: {result.stderr}"
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_install_launchd.py -v
```
Expected: ModuleNotFoundError on `launchd.install_launchd`.

### Step 3: Create `launchd/__init__.py`

```python
"""launchd plist templates + install / uninstall scripts."""
```

### Step 4: Implement `launchd/install_launchd.py`

```python
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
```

### Step 5: Implement `launchd/uninstall_launchd.py`

```python
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
```

### Step 6: Update `Makefile`

Add to the `.PHONY` line:

```
.PHONY: bootstrap bootstrap-existing ensure-db dev-worker dev-dashboard test lint typecheck format smoke-immich smoke-llm smoke-places smoke-dashboard install-launchd uninstall-launchd logs backup-now
```

At the bottom of the Makefile, add:

```makefile

install-launchd:
	$(PYTHON) -m launchd.install_launchd

uninstall-launchd:
	$(PYTHON) -m launchd.uninstall_launchd

logs:
	@LOG_DIR=$$HOME/Library/Logs/home_photo_repo; \
	test -d "$$LOG_DIR" || (echo "log dir $$LOG_DIR does not exist yet — has install-launchd run?" && exit 1); \
	tail -f $$LOG_DIR/*.log
```

(The `backup-now` and `bootstrap-existing` targets arrive in Tasks 4 and 7.)

### Step 7: Run + lint + typecheck

```bash
uv run pytest tests/test_install_launchd.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

Expected: 3 of 4 tests pass (the worker-template test is skipped because the template doesn't exist yet — it will pass after Task 3). Full suite ~162 tests; mypy + ruff clean.

If mypy errors on the `launchd/` package because it's outside `src/`, add to `pyproject.toml` under `[tool.mypy]`:

```toml
mypy_path = ["src", "."]
packages = ["home_photo_repo", "launchd"]
```

(Keep the existing entries; add `launchd` to packages.)

### Step 8: Commit

```bash
git add launchd/__init__.py launchd/install_launchd.py launchd/uninstall_launchd.py \
        tests/test_install_launchd.py Makefile pyproject.toml
git commit -m "feat: launchd template substitution + install/uninstall/logs Makefile targets"
```

---

## Task 3: Worker launchd plist

### Files
- Create: `launchd/com.homephoto.worker.plist.template`

### Step 1: Create `launchd/com.homephoto.worker.plist.template`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.homephoto.worker</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{UV}}</string>
        <string>run</string>
        <string>python</string>
        <string>-m</string>
        <string>home_photo_repo.worker.main</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{{REPO_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{{HOME}}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>60</integer>

    <key>StandardOutPath</key>
    <string>{{LOG_DIR}}/worker.log</string>

    <key>StandardErrorPath</key>
    <string>{{LOG_DIR}}/worker.err.log</string>
</dict>
</plist>
```

### Step 2: Run the test that was previously skipped

```bash
uv run pytest tests/test_install_launchd.py -v
```

Expected: 4 tests pass (including `test_worker_template_substitutes_to_valid_xml`).

### Step 3: Commit

```bash
git add launchd/com.homephoto.worker.plist.template
git commit -m "feat: launchd plist template for the ingestion worker (RunAtLoad + KeepAlive + throttle)"
```

---

## Task 4: Dashboard launchd plist

### Files
- Create: `launchd/com.homephoto.dashboard.plist.template`

### Step 1: Create `launchd/com.homephoto.dashboard.plist.template`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.homephoto.dashboard</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{UV}}</string>
        <string>run</string>
        <string>python</string>
        <string>-m</string>
        <string>home_photo_repo.dashboard.main</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{{REPO_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{{HOME}}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>{{LOG_DIR}}/dashboard.log</string>

    <key>StandardErrorPath</key>
    <string>{{LOG_DIR}}/dashboard.err.log</string>
</dict>
</plist>
```

### Step 2: Add a test for the dashboard template

In `tests/test_install_launchd.py`, append:

```python
def test_dashboard_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    from launchd.install_launchd import default_context, substitute

    template_path = LAUNCHD_DIR / "com.homephoto.dashboard.plist.template"
    if not template_path.exists():
        pytest.skip("dashboard template not yet created (Task 4)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected the plist: {result.stderr}"
```

### Step 3: Run + commit

```bash
uv run pytest tests/test_install_launchd.py -v
```

Expected: 5 tests pass.

```bash
git add launchd/com.homephoto.dashboard.plist.template tests/test_install_launchd.py
git commit -m "feat: launchd plist template for the dashboard (uvicorn)"
```

---

## Task 5: Backup script + nightly plist

### Files
- Create: `scripts/backup_postgres.sh`
- Create: `launchd/com.homephoto.backup.plist.template`
- Create: `tests/test_backup_script.py`
- Modify: `Makefile` (add `backup-now` target)

### Step 1: Write failing tests — `tests/test_backup_script.py`

```python
"""Tests for the backup_postgres.sh script.

We don't run the real backup (would need Docker); just verify the script is
shell-valid and prints the expected commands in dry-run mode."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "backup_postgres.sh"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@pytest.mark.skipif(not _have("bash"), reason="bash not installed")
def test_script_syntax_is_valid() -> None:
    """`bash -n` parses the script without errors."""
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    result = subprocess.run(["bash", "-n", str(SCRIPT)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not _have("bash"), reason="bash not installed")
def test_dry_run_lists_pg_dumpall_command(tmp_path: Path) -> None:
    """`BACKUP_DRY_RUN=1 bash backup_postgres.sh` echoes the commands it
    would run instead of executing them; output must mention pg_dumpall."""
    env = dict(os.environ)
    env["BACKUP_DRY_RUN"] = "1"
    env["BACKUP_DIR"] = str(tmp_path)
    result = subprocess.run(["bash", str(SCRIPT)],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "pg_dumpall" in result.stdout
    assert str(tmp_path) in result.stdout


@pytest.mark.skipif(not _have("bash"), reason="bash not installed")
def test_dry_run_lists_retention_pruning(tmp_path: Path) -> None:
    """Dry run should also mention removing old backups (rotation)."""
    env = dict(os.environ)
    env["BACKUP_DRY_RUN"] = "1"
    env["BACKUP_DIR"] = str(tmp_path)
    env["RETENTION_DAYS"] = "14"
    result = subprocess.run(["bash", str(SCRIPT)],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert "14" in result.stdout or "retention" in result.stdout.lower()
```

### Step 2: Create `scripts/backup_postgres.sh`

```bash
#!/usr/bin/env bash
# Nightly Postgres backup for Immich.
#
# Runs `pg_dumpall` inside the immich_postgres container, gzips the output,
# and stores under $BACKUP_DIR (default: $HOME/home_photo_repo_dev/immich/backups).
# Prunes dumps older than $RETENTION_DAYS (default: 14).
#
# Env:
#   BACKUP_DIR        target directory for .sql.gz files
#   RETENTION_DAYS    keep dumps newer than this many days (default 14)
#   BACKUP_DRY_RUN    if set to 1, print commands instead of running them
#   POSTGRES_USER     defaults to 'postgres'
#   CONTAINER_NAME    defaults to 'immich_postgres'

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/home_photo_repo_dev/immich/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
CONTAINER_NAME="${CONTAINER_NAME:-immich_postgres}"
DRY_RUN="${BACKUP_DRY_RUN:-0}"

TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/immich_${TIMESTAMP}.sql.gz"

run() {
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY-RUN: $*"
    else
        eval "$@"
    fi
}

# Ensure target dir exists.
run "mkdir -p '$BACKUP_DIR'"

# Run pg_dumpall and gzip in one stream.
run "docker exec -t '$CONTAINER_NAME' pg_dumpall -U '$POSTGRES_USER' | gzip > '$OUT_FILE'"

# Rotate: delete .sql.gz files older than RETENTION_DAYS.
echo "retention: keeping dumps newer than ${RETENTION_DAYS} days in $BACKUP_DIR"
run "find '$BACKUP_DIR' -maxdepth 1 -type f -name 'immich_*.sql.gz' -mtime +${RETENTION_DAYS} -delete"

echo "backup complete: $OUT_FILE"
```

Make it executable:

```bash
chmod +x scripts/backup_postgres.sh
```

### Step 3: Create `launchd/com.homephoto.backup.plist.template`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.homephoto.backup</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{REPO_ROOT}}/scripts/backup_postgres.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{{REPO_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{{HOME}}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>StandardOutPath</key>
    <string>{{LOG_DIR}}/backup.log</string>

    <key>StandardErrorPath</key>
    <string>{{LOG_DIR}}/backup.err.log</string>
</dict>
</plist>
```

### Step 4: Add `backup-now` target to `Makefile`

At the bottom:

```makefile

backup-now:
	scripts/backup_postgres.sh
```

### Step 5: Add backup-template test

Append to `tests/test_install_launchd.py`:

```python
def test_backup_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    from launchd.install_launchd import default_context, substitute

    template_path = LAUNCHD_DIR / "com.homephoto.backup.plist.template"
    if not template_path.exists():
        pytest.skip("backup template not yet created (Task 5)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected the plist: {result.stderr}"
```

### Step 6: Run + commit

```bash
uv run pytest tests/test_backup_script.py tests/test_install_launchd.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add scripts/backup_postgres.sh launchd/com.homephoto.backup.plist.template \
        tests/test_backup_script.py tests/test_install_launchd.py Makefile
git commit -m "feat: nightly pg_dumpall backup script + launchd plist (03:00 daily, 14-day retention)"
```

Expected: 3 new backup tests + 1 new install test + full suite ~166; mypy + ruff clean.

---

## Task 6: `bootstrap-existing` Makefile target

For new-Mac migration: skip DB creation and seed_places because the SSD already has them.

### Files
- Modify: `Makefile`

### Step 1: Add to `.PHONY` if not already there

```
.PHONY: ... bootstrap-existing ...
```

(Should already be in `.PHONY` from Task 2 — verify.)

### Step 2: Add the recipe

At the bottom of the Makefile:

```makefile

bootstrap-existing:
	uv venv
	uv sync --all-extras
	@if [ ! -f .env ]; then \
		echo "ERROR: .env missing. Create it from .env.example first."; \
		exit 1; \
	fi
	@chmod 600 .env
	@if grep -qE '^(IMMICH_API_KEY|ANTHROPIC_API_KEY)=replace_me' .env; then \
		echo "ERROR: .env still contains 'replace_me' placeholder secrets."; \
		exit 1; \
	fi
	@if [ ! -f "$${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db/app.sqlite" ]; then \
		echo "ERROR: app.sqlite not found at $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db/app.sqlite"; \
		echo "       Use 'make bootstrap' on a fresh setup; 'bootstrap-existing' is for migrating to a new Mac with an already-populated SSD."; \
		exit 1; \
	fi
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/logs
	$(PYTHON) -m home_photo_repo.db migrate
	@echo "bootstrap-existing complete — DB is present, deps installed, migrations applied."
```

### Step 3: Verify the Makefile parses (dry-run)

```bash
make -n bootstrap-existing 2>&1 | head -20
```

Expected: prints the recipe lines without errors.

### Step 4: Commit

```bash
git add Makefile
git commit -m "feat: make bootstrap-existing for new-Mac migration with pre-populated SSD"
```

---

## Task 7: (Optional) MLX launchd plist + setup notes

The MLX server is opt-in. We ship the template + a small section in operations.md.

### Files
- Create: `launchd/com.homephoto.mlx.plist.template`

### Step 1: Create `launchd/com.homephoto.mlx.plist.template`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.homephoto.mlx</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{UV}}</string>
        <string>run</string>
        <string>--with</string>
        <string>mlx-vlm</string>
        <string>python</string>
        <string>-m</string>
        <string>mlx_vlm.server</string>
        <string>--model</string>
        <string>mlx-community/Qwen2-VL-2B-Instruct-4bit</string>
        <string>--port</string>
        <string>8081</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{{REPO_ROOT}}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{{HOME}}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>120</integer>

    <key>StandardOutPath</key>
    <string>{{LOG_DIR}}/mlx.log</string>

    <key>StandardErrorPath</key>
    <string>{{LOG_DIR}}/mlx.err.log</string>
</dict>
</plist>
```

### Step 2: Add MLX template test

Append to `tests/test_install_launchd.py`:

```python
def test_mlx_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    from launchd.install_launchd import default_context, substitute

    template_path = LAUNCHD_DIR / "com.homephoto.mlx.plist.template"
    if not template_path.exists():
        pytest.skip("mlx template not present (optional, Task 7)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected: {result.stderr}"
```

### Step 3: Run + commit

```bash
uv run pytest tests/test_install_launchd.py -v

git add launchd/com.homephoto.mlx.plist.template tests/test_install_launchd.py
git commit -m "feat: optional launchd plist template for MLX vision server"
```

---

## Task 8: `docs/operations.md`

### Files
- Create: `docs/operations.md`

### Step 1: Create `docs/operations.md`

```markdown
# Operations Guide

Day-2 operations for `home_photo_repo`: launchd auto-start, backups,
migration to a new Mac, optional MLX setup, and troubleshooting.

## Install auto-start (launchd)

The worker and dashboard run as user-level launchd services. They start at
login, restart on crash, and write logs to `~/Library/Logs/home_photo_repo/`.

```bash
cd ~/Documents/code/home
make install-launchd
```

This installs three services:

| Service | When it runs | Log file |
|---|---|---|
| `com.homephoto.worker` | always (`RunAtLoad`, `KeepAlive`) | `worker.log`, `worker.err.log` |
| `com.homephoto.dashboard` | always | `dashboard.log`, `dashboard.err.log` |
| `com.homephoto.backup` | daily at 03:00 | `backup.log`, `backup.err.log` |

The MLX plist (`com.homephoto.mlx`) is optional and not installed by default.
To opt in:

```bash
uv run python -m launchd.install_launchd mlx
```

### Verify services are running

```bash
launchctl list | grep com.homephoto
```

You should see all three with PIDs (column 1 = PID, column 2 = last exit
code, column 3 = label). PID `-` means the service is loaded but not
currently running (this is normal for `backup`, which only runs at 03:00).

### Tail the logs

```bash
make logs
```

Or look at a single service:

```bash
tail -f ~/Library/Logs/home_photo_repo/worker.log
```

### Uninstall

```bash
make uninstall-launchd
```

This `launchctl bootout`s each service and removes the plists from
`~/Library/LaunchAgents/`. Safe to re-run; idempotent.

---

## Backups

### Automatic (nightly)

Once installed, `com.homephoto.backup` runs at 03:00 daily. Each run:

1. Calls `docker exec immich_postgres pg_dumpall -U postgres`.
2. Pipes the output through `gzip`.
3. Writes to `$BACKUP_DIR/immich_YYYY-MM-DD_HHMMSS.sql.gz` (default
   `$HOME/home_photo_repo_dev/immich/backups`).
4. Deletes any `.sql.gz` older than 14 days.

Tune via env vars in the plist or by overriding before manual runs:

```bash
BACKUP_DIR=/Volumes/PhotoSSD/immich/backups RETENTION_DAYS=30 \
  scripts/backup_postgres.sh
```

### Manual

```bash
make backup-now
```

Or for a different target:

```bash
BACKUP_DIR=/tmp/test-backup scripts/backup_postgres.sh
```

### Restore from a backup

```bash
# Stop the dashboard + worker first so nothing's writing.
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootout gui/$UID/com.homephoto.dashboard

cd ~/Documents/code/home/docker/immich
docker compose down

# Wipe the existing pgdata.
rm -rf $DB_DATA_LOCATION/*

# Bring Postgres up alone and restore.
docker compose up -d database
sleep 10  # let it initialize
gunzip -c /path/to/immich_YYYY-MM-DD_HHMMSS.sql.gz | \
  docker exec -i immich_postgres psql -U postgres

# Bring the rest up.
docker compose up -d

# Re-load launchd services.
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.dashboard.plist
```

---

## Migrate to a new Mac

The SSD holds everything portable; the launchd plists are per-user and
get re-generated on the new Mac.

### On the old Mac

```bash
# Stop everything cleanly.
make uninstall-launchd
cd docker/immich && docker compose down

# Unmount the SSD safely.
diskutil unmountDisk /Volumes/PhotoSSD
```

Physically move the SSD.

### On the new Mac

1. Install Homebrew, Docker Desktop, Python 3.12, and `uv` (see
   `docs/SETUP.md` §1).
2. Plug in the SSD; confirm it mounts as `/Volumes/PhotoSSD`.
3. Clone the repo:
   ```bash
   git clone https://github.com/kevinlighter009/home.git ~/Documents/code/home
   cd ~/Documents/code/home
   ```
4. Copy `.env` from your password manager (or recreate from `.env.example`).
   Ensure `SSD_DATA_DIR=/Volumes/PhotoSSD/home_photo_repo`.
5. Copy `docker/immich/.env` similarly (paths pointing at the SSD).
6. Bring up Immich:
   ```bash
   cd docker/immich && docker compose up -d && cd ../..
   ```
7. Bootstrap the Python side **without re-creating the DB**:
   ```bash
   make bootstrap-existing
   ```
8. Install launchd services:
   ```bash
   make install-launchd
   ```
9. On each family member's iPhone: open the Immich app → Settings → Server
   URL → update if the Mac's hostname changed.

Wall-clock: ~30–60 min depending on Docker image download speed.

---

## Optional: MLX vision server

If you want a local fallback for Stage A and/or Stage B (zero per-call
API cost), enable MLX:

### Install mlx-vlm

```bash
uv add mlx-vlm  # or pip install mlx-vlm
```

### Smoke test the server manually

```bash
uv run mlx_vlm.server --model mlx-community/Qwen2-VL-2B-Instruct-4bit --port 8081
```

(In another terminal, verify with `curl http://localhost:8081/v1/models`.)

### Install the MLX launchd service

```bash
uv run python -m launchd.install_launchd mlx
```

### Switch the pipeline to MLX

Edit `.env`:

```dotenv
LLM_STAGE_A_PROVIDER=mlx
# Or both stages:
LLM_STAGE_B_PROVIDER=mlx
```

Restart the worker:

```bash
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
```

The worker startup log should now print `stage_a=mlx` or `stage_b=mlx`.

To revert: change `.env` back to `anthropic` and restart the worker.

### Uninstall MLX

```bash
uv run python -m launchd.uninstall_launchd mlx
```

---

## Troubleshooting

### Services don't appear in `launchctl list`

```bash
ls -la ~/Library/LaunchAgents/com.homephoto.*
```
If the files are present but `launchctl list` is empty: re-run `make
install-launchd`. The script calls `launchctl bootstrap` after copying.

### Worker / dashboard exits with code 1 on startup

Check the err.log:
```bash
tail -50 ~/Library/Logs/home_photo_repo/worker.err.log
```
Common causes:
- `.env` missing or has placeholder values
- `uv` not on PATH for the launchd process (the plist sets PATH explicitly;
  if you moved uv, edit the template and re-install)
- SSD not mounted (when `SSD_DATA_DIR=/Volumes/PhotoSSD/...`)

### Backups not running at 03:00

```bash
launchctl print gui/$UID/com.homephoto.backup
```
Look at `next run time`. If the Mac was asleep at 03:00, launchd will run
the missed job on next wake. To run manually:
```bash
launchctl kickstart -k gui/$UID/com.homephoto.backup
```

### Backup script fails with "permission denied"

The plist runs as your user, but `docker exec` needs Docker Desktop to
be running. If you log out / fast-user-switch, Docker might pause and
the backup will fail. Either:
- Stay logged in
- Or run `docker context use desktop-linux` first (rare)

### Dashboard reachable from another device

Default binds to `127.0.0.1` (localhost-only). To expose:
- Add HTTP Basic auth first (see spec §7 — not yet implemented).
- Then change `.env`: `DASHBOARD_BIND=0.0.0.0:8000`
- Restart the dashboard.

### Resetting from scratch (DESTRUCTIVE)

```bash
make uninstall-launchd
cd docker/immich && docker compose down -v && cd ../..
rm -rf $SSD_DATA_DIR/db $HOME/home_photo_repo_dev
make bootstrap
```
```

### Step 2: Commit

```bash
git add docs/operations.md
git commit -m "docs: operations guide — install/uninstall/backup/migrate/MLX/troubleshooting"
```

---

## Task 9: README + final sweep

### Files
- Modify: `README.md`
- Modify: `docs/SETUP.md`

### Step 1: Update `README.md`

**1a.** Replace the intro paragraph. Find the paragraph starting "This is **Plan 4 (Dashboard)**." and change to:

```markdown
This is **Plan 5 (Operations)** — and the project is feature-complete.
The worker and dashboard auto-start at login via macOS launchd, a nightly
Postgres backup keeps a rotating 14-day history, and the codebase
supports migration to a new Mac via a single `make bootstrap-existing`
once the SSD is plugged in.

See [`docs/operations.md`](docs/operations.md) for install / uninstall /
backup / migrate / troubleshooting. See
[`docs/SETUP.md`](docs/SETUP.md) for the fresh-Mac install walkthrough.
```

**1b.** Update Roadmap — find the Plan 5 line and change to:

```markdown
- **Plan 5** ✅ Done — launchd plists (auto-start at login), nightly
  `pg_dumpall` backup, `bootstrap-existing` for new-Mac migration,
  optional MLX server.
```

**1c.** Add an `## Operations` section between the `## Dashboard` section
and the `## Project layout` section:

```markdown
## Operations

The worker and dashboard run permanently as macOS launchd services. A
backup job runs nightly at 03:00.

```bash
make install-launchd    # one-time, after make bootstrap
make logs               # tail all service logs
make backup-now         # ad-hoc backup
make uninstall-launchd  # stop & remove the services
```

Full procedures (including new-Mac migration and restoring from a backup)
are in [`docs/operations.md`](docs/operations.md).
```

**1d.** Update Project layout — add `launchd/` to the top-level tree:

```
home/
├── src/home_photo_repo/   # main package (see breakdown below)
├── migrations/             # forward-only .sql files
├── docker/immich/          # Immich Docker Compose config
├── scripts/                # smoke tests, backup, one-shot tools
├── launchd/                # ← Plan 5
│   ├── com.homephoto.worker.plist.template
│   ├── com.homephoto.dashboard.plist.template
│   ├── com.homephoto.backup.plist.template
│   ├── com.homephoto.mlx.plist.template     # optional
│   ├── install_launchd.py
│   └── uninstall_launchd.py
├── tests/                  # pytest suite, no network
└── docs/                   # spec, plans, SETUP.md, operations.md
```

### Step 2: Update `docs/SETUP.md`

**2a.** At the very end of `docs/SETUP.md`, add a final section:

```markdown
## (Plan 5) Make it run forever

After the dashboard works manually:

```bash
make install-launchd
```

This installs three launchd user services that start at login and
restart on crash:

- `com.homephoto.worker`
- `com.homephoto.dashboard`
- `com.homephoto.backup` (daily 03:00)

See [`docs/operations.md`](operations.md) for verification, restoring
from backups, migration to a new Mac, and the optional MLX server.

You're done. Open http://127.0.0.1:8000 whenever you want to browse.
```

**2b.** Update the verification checklist heading and add items:

Find:
```markdown
## Verification checklist — Plans 1–4 complete
```
Change to:
```markdown
## Verification checklist — All plans complete
```

Append to the checklist:

```markdown
- [ ] `make install-launchd` succeeds; `launchctl list | grep com.homephoto` shows 3 services
- [ ] `make logs` tails active worker + dashboard logs
- [ ] `make backup-now` produces a `.sql.gz` under `$BACKUP_DIR`
- [ ] After a reboot, the dashboard is reachable at http://127.0.0.1:8000 without manual start
```

### Step 3: Final sweep

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

All green. Expected total: ~167 tests (~159 prior + 4 install_launchd + 3 backup, give or take depending on optional tests).

### Step 4: Commit

```bash
git add README.md docs/SETUP.md
git commit -m "docs: README + SETUP updated for Plan 5 — project feature-complete"
```

---

## Plan 5 acceptance checklist

- [ ] `make test` passes (~167 tests)
- [ ] `make lint` + `make typecheck` clean
- [ ] `make install-launchd` installs 3 plists; `launchctl list | grep com.homephoto` shows them
- [ ] `make uninstall-launchd` removes them
- [ ] `make logs` tails active logs
- [ ] `make backup-now` produces a `.sql.gz` in the backup dir
- [ ] After reboot, worker + dashboard auto-start (verify by `curl http://127.0.0.1:8000/healthz`)
- [ ] `make bootstrap-existing` works on a new Mac with a pre-populated SSD
- [ ] `docs/operations.md` covers install / uninstall / backup / restore / migrate / MLX / troubleshoot
- [ ] Plan 4 follow-ups #1, #2, #3 applied (db_conn ctx manager; `get_immich` removed; `VALID_VENUE_TYPES` centralized)

Once green, the project is feature-complete. Future work moves to the
follow-up files (Plan 1–4 follow-ups doc set) — Stage B candidate
prompting, dashboard polish items, etc.
