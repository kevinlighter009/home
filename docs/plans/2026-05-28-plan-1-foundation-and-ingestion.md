# Plan 1 — Foundation & Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `home_photo_repo` project skeleton with a working ingestion worker that polls a local Immich instance every 5 minutes and inserts a `discovered`-state row (with EXIF/GPS copied from Immich) into `app.sqlite` for every new asset, idempotently and crash-safely.

**Architecture:** A single Python package (`home_photo_repo`) managed by `uv`. Configuration loaded from `.env` via `pydantic-settings`. SQLite database with a forward-only migration runner. Immich accessed via a thin `httpx`-backed REST client. The worker is a sequential loop with a persistent cursor — no LLM, no place matching, no dashboard yet (those are Plans 2–4).

**Tech Stack:** Python 3.12, `uv`, `httpx`, `pydantic-settings`, `pytest`, `respx`, `pytest-socket`, `ruff`, `mypy`. Docker Compose for the Immich service (configured here but managed independently from the Python code).

**Spec reference:** `docs/specs/2026-05-28-home-photo-repo-design.md`, sections 2 (architecture), 3 (ingestion), 5 (storage & schema), 6.1/6.5 (worker loop, scheduling), 10 (config & secrets), 11 (dev workflow).

**Out of scope for this plan (explicitly):**
- LLM providers, Stage A, Stage B (Plan 2)
- Place matching, Google Places (Plan 3)
- FastAPI dashboard (Plan 4)
- launchd plists, backup script, MLX setup (Plan 5)
- Webhooks, auth, away-from-home upload (deferred per spec section 14)

**Definition of done:** With Immich running locally and a real iPhone upload, executing `make dev-worker` in the foreground causes a row to appear in `app.sqlite`'s `photo_analysis` table within one poll cycle, and `worker_state` advances. All pytest tests pass with zero network usage; `ruff` and `mypy` clean.

---

## File map

| Path | Created in task | Responsibility |
|---|---|---|
| `pyproject.toml` | 1 | Python project metadata, deps, tool config (ruff, mypy, pytest) |
| `.gitignore` | 1 | Standard Python ignores + `.env`, `*.sqlite`, `.venv`, logs |
| `.env.example` | 1 | All env keys with placeholders + inline comments |
| `Makefile` | 1, 9, 10 | `bootstrap`, `dev-worker`, `test`, `lint`, `smoke-immich` |
| `README.md` | 1 (skeleton), 10 (fill out) | Setup, run, verify |
| `src/home_photo_repo/__init__.py` | 1 | Empty package marker |
| `tests/__init__.py` | 1 | Empty package marker |
| `tests/conftest.py` | 3 | `pytest-socket` enablement; shared fixtures |
| `docker/immich/docker-compose.yml` | 2 | Upstream Immich compose, paths via env |
| `docker/immich/.env.example` | 2 | UPLOAD_LOCATION, DB_DATA_LOCATION pointed at SSD |
| `src/home_photo_repo/config.py` | 3 | `Settings` pydantic model; loads `.env`; secret-masking `__repr__` |
| `tests/test_config.py` | 3 | Required fields, defaults, secret masking |
| `src/home_photo_repo/db.py` | 4 | `get_connection()`, `apply_migrations()`, `_migrations` tracking |
| `tests/test_db.py` | 4 | Connection, migration apply/skip behavior |
| `migrations/001_initial.sql` | 5 | Full schema from spec §5.2 (all columns; most unused in Plan 1) |
| `tests/test_migration_001.py` | 5 | After apply, expected tables and columns exist |
| `src/home_photo_repo/immich_client.py` | 6 | `ImmichClient.search_metadata(updated_after, size, order)` |
| `src/home_photo_repo/immich_types.py` | 6 | Typed dicts/dataclasses for Immich API responses |
| `tests/test_immich_client.py` | 6 | respx-backed: happy path, 401, 500, pagination, GPS parsing |
| `src/home_photo_repo/worker/__init__.py` | 7 | Empty |
| `src/home_photo_repo/worker/pipeline.py` | 7 | `process_asset(asset, conn)` — inserts discovered row idempotently, applies readiness check |
| `tests/test_pipeline.py` | 7 | Insert, idempotent re-insert, readiness check skips young GPS-less, GPS-less old asset is recorded as needs_review |
| `src/home_photo_repo/worker/cursor.py` | 8 | `read_cursor(conn)`, `write_cursor(conn, ts)` against `worker_state` |
| `tests/test_cursor.py` | 8 | Default-empty, write+read round-trip, monotonic guard |
| `src/home_photo_repo/worker/main.py` | 8 | `run_once(...)` and `run_forever(...)`; CLI entrypoint via `python -m` |
| `tests/test_worker_main.py` | 8 | `run_once` polls, processes, advances cursor; transient error doesn't advance; backfill mode (empty cursor) starts from epoch |
| `scripts/smoke_immich.py` | 9 | Hits real local Immich, prints 5 most recent assets |
| `tests/fixtures/immich_search_metadata.json` | 6 | Recorded sample response for respx |

---

## Conventions used in this plan

- **All file paths are absolute or repo-relative from `home_photo_repo/`**. Repo root = `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home_photo_repo`.
- **Every code step shows the complete file contents** for newly-created files (no "fill in the rest"). For edits to existing files, the relevant region is shown.
- **TDD order:** write the failing test → run it to confirm it fails → write the minimal code → run it to confirm it passes → commit.
- **One conceptual change per commit.** Commit messages follow `<type>: <summary>` (`feat:`, `test:`, `chore:`, `docs:`).
- **Git context:** the `home_photo_repo/` directory is already an initialized git repo (one commit: the spec). All commits in this plan happen in that repo.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `Makefile`
- Create: `README.md`
- Create: `src/home_photo_repo/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "home_photo_repo"
version = "0.1.0"
description = "Local home-photo ingestion + analysis service on top of Immich"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-socket>=0.7",
    "respx>=0.21",
    "ruff>=0.5",
    "mypy>=1.10",
    "types-requests",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/home_photo_repo"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --disable-socket"
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
packages = ["home_photo_repo"]
```

- [ ] **Step 2: Create `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
*.egg-info/

# Project
.env
*.sqlite
*.sqlite-journal
logs/
.DS_Store
```

- [ ] **Step 3: Create `.env.example`**

```dotenv
# Immich
IMMICH_BASE_URL=http://localhost:2283
IMMICH_API_KEY=replace_me_generate_in_immich_ui

# Anthropic (used in Plan 2; ignored by Plan 1 code)
ANTHROPIC_API_KEY=replace_me

# Google Places (used in Plan 3; ignored by Plan 1 code)
GOOGLE_PLACES_API_KEY=replace_me

# Storage — point at the external SSD once available; for dev a local path is fine
SSD_DATA_DIR=/Volumes/PhotoSSD/home_photo_repo

# Worker tunables (defaults from spec §10)
POLL_INTERVAL_SECONDS=300
BACKFILL_BATCH_SIZE=100
STAGE_A_FOOD_THRESHOLD=0.6
STAGE_B_CONFIDENCE_REVIEW_THRESHOLD=0.7
PLACE_MATCH_AMBIGUOUS_THRESHOLD_M=50
CURATED_PLACE_DEFAULT_RADIUS_M=50
GOOGLE_PLACES_SEARCH_RADIUS_M=150
ANTHROPIC_RATE_LIMIT_PER_MINUTE=30
DASHBOARD_BIND=127.0.0.1:8000

# LLM provider selection (used in Plan 2)
LLM_STAGE_A_PROVIDER=anthropic
LLM_STAGE_A_MODEL=claude-haiku-4-5
LLM_STAGE_B_PROVIDER=anthropic
LLM_STAGE_B_MODEL=claude-sonnet-4-5

# MLX placeholder (Plan 2)
MLX_BASE_URL=http://localhost:8081/v1
MLX_STAGE_A_MODEL=mlx-community/Qwen2-VL-2B-Instruct-4bit
MLX_STAGE_B_MODEL=mlx-community/Qwen2-VL-7B-Instruct-4bit
```

- [ ] **Step 4: Create `Makefile`**

```makefile
.PHONY: bootstrap dev-worker test lint typecheck format

PYTHON := uv run python
PYTEST := uv run pytest

bootstrap:
	uv venv
	uv sync --all-extras
	@test -f .env || (cp .env.example .env && chmod 600 .env && echo "Created .env from template — fill in keys then re-run bootstrap")
	@test -f .env && chmod 600 .env
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/logs
	$(PYTHON) -m home_photo_repo.db migrate
	@echo "Bootstrap complete."

dev-worker:
	$(PYTHON) -m home_photo_repo.worker.main

test:
	$(PYTEST)

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy

format:
	uv run ruff format src tests
```

- [ ] **Step 5: Create `README.md` (skeleton — fleshed out in Task 10)**

```markdown
# home_photo_repo

Local home-photo ingestion + analysis service. Sits on top of a self-hosted
[Immich](https://immich.app/) instance and adds food/dish recognition and
venue (restaurant / home / office) tagging.

See `docs/specs/2026-05-28-home-photo-repo-design.md` for the full design.

## Status

Plan 1 (Foundation & Ingestion) — in progress.

Full setup instructions land in Task 10.
```

- [ ] **Step 6: Create empty package markers**

`src/home_photo_repo/__init__.py`:
```python
"""home_photo_repo — local home-photo ingestion & analysis service."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 7: Verify `uv sync` works**

Run:
```bash
cd home_photo_repo && uv sync --all-extras
```
Expected: creates `.venv/`, resolves and installs dependencies, exits 0.

- [ ] **Step 8: Verify `pytest` discovers an empty test suite cleanly**

Run:
```bash
cd home_photo_repo && uv run pytest
```
Expected: `no tests ran in 0.XXs` (exit 0). This confirms pytest config is loadable and `pytest-socket` is wired without blowing up.

- [ ] **Step 9: Commit**

```bash
cd home_photo_repo
git add pyproject.toml .gitignore .env.example Makefile README.md src tests
git commit -m "chore: project scaffolding (pyproject, makefile, gitignore, package skeleton)"
```

---

## Task 2: Immich Docker Compose configuration

This task only records the Immich configuration the user will run *outside* the Python code. No tests — config files are inert.

**Files:**
- Create: `docker/immich/docker-compose.yml`
- Create: `docker/immich/.env.example`
- Create: `docker/immich/README.md`

- [ ] **Step 1: Create `docker/immich/docker-compose.yml`**

This is a minimally-adapted copy of the official Immich compose file (https://immich.app). Volumes for the library and Postgres come from env variables so the user can point them at the external SSD.

```yaml
name: immich

services:
  immich-server:
    container_name: immich_server
    image: ghcr.io/immich-app/immich-server:release
    volumes:
      - ${UPLOAD_LOCATION}:/usr/src/app/upload
      - /etc/localtime:/etc/localtime:ro
    env_file:
      - .env
    ports:
      - "2283:2283"
    depends_on:
      - redis
      - database
    restart: always
    healthcheck:
      disable: false

  immich-machine-learning:
    container_name: immich_machine_learning
    image: ghcr.io/immich-app/immich-machine-learning:release
    volumes:
      - model-cache:/cache
    env_file:
      - .env
    restart: always
    healthcheck:
      disable: false

  redis:
    container_name: immich_redis
    image: docker.io/redis:6.2-alpine
    healthcheck:
      test: redis-cli ping || exit 1
    restart: always

  database:
    container_name: immich_postgres
    image: ghcr.io/immich-app/postgres:14-vectorchord0.3.0-pgvectors0.2.0
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_USER: ${DB_USERNAME}
      POSTGRES_DB: ${DB_DATABASE_NAME}
      POSTGRES_INITDB_ARGS: '--data-checksums'
    volumes:
      - ${DB_DATA_LOCATION}:/var/lib/postgresql/data
    healthcheck:
      test: >-
        pg_isready --dbname="$${POSTGRES_DB}" --username="$${POSTGRES_USER}" || exit 1;
        Chksum="$$(psql --dbname="$${POSTGRES_DB}" --username="$${POSTGRES_USER}" --tuples-only --no-align
        --command='SELECT COALESCE(SUM(checksum_failures),0) FROM pg_stat_database')";
        echo "checksum_failure_count=$$Chksum";
        [ "$$Chksum" = '0' ] || exit 1
      interval: 5m
      start_interval: 30s
      start_period: 5m
    restart: always

volumes:
  model-cache:
```

> Note: if the upstream Immich `docker-compose.yml` has changed by the time this plan runs, prefer the upstream file and only re-apply the `${UPLOAD_LOCATION}` / `${DB_DATA_LOCATION}` volume edits.

- [ ] **Step 2: Create `docker/immich/.env.example`**

```dotenv
# Point these at the external SSD when available.
UPLOAD_LOCATION=/Volumes/PhotoSSD/immich/library
DB_DATA_LOCATION=/Volumes/PhotoSSD/immich/pgdata

# Postgres credentials (used only inside the Docker network)
DB_PASSWORD=changeme_use_a_strong_random_value
DB_USERNAME=postgres
DB_DATABASE_NAME=immich

# Immich version pin — keep matched between Macs to avoid pgdata incompatibility.
# Override with a specific version (e.g. v1.118.2) instead of 'release' if you want pinning.
IMMICH_VERSION=release

TZ=America/Los_Angeles
```

- [ ] **Step 3: Create `docker/immich/README.md`**

```markdown
# Immich (Docker Compose)

This directory contains the Immich service configuration. Immich runs
independently from the `home_photo_repo` Python code.

## First-time setup

1. Format the external SSD as **APFS** (Mac-only) and create the target dirs:
   ```bash
   mkdir -p /Volumes/PhotoSSD/immich/{library,pgdata,backups}
   ```
2. Exclude `pgdata/` from Spotlight and Time Machine:
   ```bash
   mdutil -i off /Volumes/PhotoSSD
   ```
   System Settings → Time Machine → Options → add `/Volumes/PhotoSSD`.
3. Copy this directory's `.env.example` to `.env` and edit the paths and
   `DB_PASSWORD`.
4. Bring it up:
   ```bash
   cd docker/immich
   docker compose up -d
   ```
5. Visit http://localhost:2283 in a browser, create the admin account, then
   create per-family-member user accounts.
6. In Immich UI → Account → API Keys, generate one for `home_photo_repo` and
   put it in the top-level `home_photo_repo/.env` as `IMMICH_API_KEY`.
7. On each family member's iPhone: install the **Immich** app from the App
   Store, point at `http://<your-mac-hostname>.local:2283`, sign in, enable
   "Backup" → "Foreground" and "Background" with WiFi-only.

## Safe shutdown

Always stop Immich cleanly before unplugging the SSD:
```bash
cd docker/immich && docker compose down
```
```

- [ ] **Step 4: Commit**

```bash
cd home_photo_repo
git add docker/
git commit -m "chore: docker compose config for Immich (SSD-backed volumes)"
```

---

## Task 3: Config module

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`
- Create: `src/home_photo_repo/config.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
"""Pytest configuration: enable socket disabling globally (we mock all HTTP)."""

import os

import pytest


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests cannot accidentally read the developer's real .env."""
    for key in list(os.environ):
        if key.startswith(("IMMICH_", "ANTHROPIC_", "GOOGLE_", "LLM_", "MLX_", "SSD_")):
            monkeypatch.delenv(key, raising=False)
```

- [ ] **Step 2: Write the failing test — `tests/test_config.py`**

```python
"""Tests for home_photo_repo.config.Settings."""

from pathlib import Path

import pytest


def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "test-key-abc")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    assert str(s.immich_base_url).rstrip("/") == "http://localhost:2283"
    assert s.immich_api_key.get_secret_value() == "test-key-abc"
    assert s.ssd_data_dir == Path("/tmp/hpr_test")


def test_settings_applies_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    assert s.poll_interval_seconds == 300
    assert s.backfill_batch_size == 100
    assert s.stage_a_food_threshold == 0.6


def test_settings_repr_masks_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "super-secret-do-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    text = repr(s)
    assert "super-secret-do-not-leak" not in text
    assert "anthropic-secret" not in text
    # The repr should still show the field names so debugging works.
    assert "immich_api_key" in text


def test_settings_db_path_derives_from_ssd_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings

    s = Settings()
    assert s.db_path == Path("/tmp/hpr_test/db/app.sqlite")
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_config.py -v
```
Expected: collection error or `ModuleNotFoundError: No module named 'home_photo_repo.config'`.

- [ ] **Step 4: Implement `src/home_photo_repo/config.py`**

```python
"""Application configuration loaded from environment / .env file.

Secrets are wrapped in `SecretStr` so their values do not appear in repr/log output.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Immich
    immich_base_url: HttpUrl
    immich_api_key: SecretStr

    # Other provider keys — accepted but unused in Plan 1.
    anthropic_api_key: SecretStr = SecretStr("")
    google_places_api_key: SecretStr = SecretStr("")

    # Storage
    ssd_data_dir: Path

    # Worker tunables
    poll_interval_seconds: int = 300
    backfill_batch_size: int = 100
    stage_a_food_threshold: float = 0.6
    stage_b_confidence_review_threshold: float = 0.7
    place_match_ambiguous_threshold_m: int = 50
    curated_place_default_radius_m: int = 50
    google_places_search_radius_m: int = 150
    anthropic_rate_limit_per_minute: int = 30
    dashboard_bind: str = "127.0.0.1:8000"

    # LLM provider selection (consumed in Plan 2)
    llm_stage_a_provider: str = "anthropic"
    llm_stage_a_model: str = "claude-haiku-4-5"
    llm_stage_b_provider: str = "anthropic"
    llm_stage_b_model: str = "claude-sonnet-4-5"

    # MLX placeholder
    mlx_base_url: str = "http://localhost:8081/v1"
    mlx_stage_a_model: str = "mlx-community/Qwen2-VL-2B-Instruct-4bit"
    mlx_stage_b_model: str = "mlx-community/Qwen2-VL-7B-Instruct-4bit"

    @property
    def db_path(self) -> Path:
        return self.ssd_data_dir / "db" / "app.sqlite"


__all__ = ["Settings"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_config.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd home_photo_repo
git add src/home_photo_repo/config.py tests/conftest.py tests/test_config.py
git commit -m "feat: config module with pydantic-settings and secret masking"
```

---

## Task 4: DB module — connection and migration runner

**Files:**
- Create: `tests/test_db.py`
- Create: `src/home_photo_repo/db.py`

- [ ] **Step 1: Write the failing test — `tests/test_db.py`**

```python
"""Tests for home_photo_repo.db.

The migration runner is forward-only: each .sql file in the migrations/
directory is applied once, in lexical order, and recorded in a _migrations
table so subsequent runs skip it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection


def _write_migration(dir_: Path, n: int, name: str, sql: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{n:03d}_{name}.sql").write_text(sql)


def test_get_connection_creates_parent_dirs(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "deeper" / "app.sqlite"
    conn = get_connection(db)
    assert db.exists()
    conn.close()


def test_apply_migrations_runs_in_order(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "init", "CREATE TABLE t1 (id INTEGER);")
    _write_migration(migrations, 2, "add_t2", "CREATE TABLE t2 (id INTEGER);")
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)

    apply_migrations(conn, migrations)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"t1", "t2", "_migrations"}.issubset(tables)


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "init", "CREATE TABLE t1 (id INTEGER);")
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)

    apply_migrations(conn, migrations)
    # Second call must not error on existing table.
    apply_migrations(conn, migrations)

    rows = conn.execute("SELECT id, description FROM _migrations ORDER BY id").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "001_init"


def test_apply_migrations_fails_loudly_on_bad_sql(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "broken", "CREATE TABEL t1 (id INTEGER);")  # typo
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)

    with pytest.raises(sqlite3.Error):
        apply_migrations(conn, migrations)


def test_apply_migrations_skips_already_applied(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    _write_migration(migrations, 1, "init", "CREATE TABLE t1 (id INTEGER);")
    db = tmp_path / "app.sqlite"
    conn = get_connection(db)
    apply_migrations(conn, migrations)

    # Add a second migration and re-run; only the new one should apply.
    _write_migration(migrations, 2, "add_t2", "CREATE TABLE t2 (id INTEGER);")
    apply_migrations(conn, migrations)

    rows = conn.execute("SELECT description FROM _migrations ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["001_init", "002_add_t2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_db.py -v
```
Expected: `ModuleNotFoundError: No module named 'home_photo_repo.db'`.

- [ ] **Step 3: Implement `src/home_photo_repo/db.py`**

```python
"""SQLite connection helper and forward-only migration runner.

A migration is any file `migrations/NNN_description.sql`. They are applied
in lexical order, exactly once each, tracked in a `_migrations` table.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a SQLite connection at `db_path`.

    Enables foreign keys and WAL mode for safer concurrent reads.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        isolation_level=None,  # autocommit; we manage tx with BEGIN/COMMIT explicitly
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            id          INTEGER PRIMARY KEY,
            applied_at  DATETIME NOT NULL,
            description TEXT NOT NULL
        )
        """
    )


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[str]:
    """Apply any pending migrations. Returns the descriptions applied this call."""
    _ensure_migrations_table(conn)
    applied = {
        row[0] for row in conn.execute("SELECT description FROM _migrations").fetchall()
    }
    files = sorted(p for p in migrations_dir.glob("*.sql"))
    newly_applied: list[str] = []
    for path in files:
        desc = path.stem  # e.g. "001_initial"
        if desc in applied:
            continue
        sql = path.read_text()
        try:
            conn.execute("BEGIN")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO _migrations (id, applied_at, description) VALUES (?, datetime('now'), ?)",
                (int(desc.split("_", 1)[0]), desc),
            )
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
        newly_applied.append(desc)
    return newly_applied


def _cli_migrate() -> None:
    """`python -m home_photo_repo.db migrate` — apply migrations using Settings."""
    from home_photo_repo.config import Settings

    settings = Settings()
    repo_root = Path(__file__).resolve().parents[2]
    migrations_dir = repo_root / "migrations"
    conn = get_connection(settings.db_path)
    applied = apply_migrations(conn, migrations_dir)
    if applied:
        print(f"Applied: {', '.join(applied)}")
    else:
        print("No pending migrations.")


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) >= 2 and sys.argv[1] == "migrate":
        _cli_migrate()
    else:
        print("Usage: python -m home_photo_repo.db migrate", file=sys.stderr)
        sys.exit(2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_db.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd home_photo_repo
git add src/home_photo_repo/db.py tests/test_db.py
git commit -m "feat: sqlite connection helper and forward-only migration runner"
```

---

## Task 5: Initial migration — full schema

Per the spec (§5.2), all tables are created at once. Most columns are nullable and only get written in later plans. Putting the full schema in one migration avoids needing schema bumps as Plans 2/3 land.

**Files:**
- Create: `migrations/001_initial.sql`
- Create: `tests/test_migration_001.py`

- [ ] **Step 1: Write the failing test — `tests/test_migration_001.py`**

```python
"""Verify migrations/001_initial.sql creates the schema the spec requires."""

from __future__ import annotations

from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _column_names(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_initial_migration_creates_all_tables(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert tables == {
        "_migrations",
        "photo_analysis",
        "places",
        "worker_runs",
        "worker_state",
    }


def test_photo_analysis_has_expected_columns(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    cols = _column_names(conn, "photo_analysis")
    expected = {
        "immich_asset_id",
        "first_seen_at",
        "taken_at",
        "latitude",
        "longitude",
        "uploader_user_id",
        "stage_a_is_food",
        "stage_a_confidence",
        "stage_a_model",
        "stage_a_ran_at",
        "dish_name",
        "cuisine",
        "stage_b_confidence",
        "stage_b_model",
        "stage_b_ran_at",
        "stage_b_raw_json",
        "venue_type",
        "place_id",
        "place_match_source",
        "place_match_distance_m",
        "review_status",
        "reviewed_at",
        "review_notes",
        "last_error",
        "error_attempts",
    }
    assert expected.issubset(cols)


def test_places_has_expected_columns(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    cols = _column_names(conn, "places")
    assert {
        "id",
        "name",
        "type",
        "latitude",
        "longitude",
        "radius_m",
        "google_place_id",
        "address",
        "created_at",
        "updated_at",
        "notes",
    }.issubset(cols)


def test_indexes_present(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    idx = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert {
        "idx_photo_taken_at",
        "idx_photo_place",
        "idx_photo_review",
        "idx_places_type",
    }.issubset(idx)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_migration_001.py -v
```
Expected: failures because `migrations/` does not exist or is empty.

- [ ] **Step 3: Create `migrations/001_initial.sql`**

```sql
-- 001_initial.sql — full schema per spec §5.2.
-- Most stage_*/venue_* columns are populated only by later plans;
-- they are nullable here so Plan 1's worker can insert minimal rows.

CREATE TABLE photo_analysis (
    immich_asset_id     TEXT PRIMARY KEY,
    first_seen_at       DATETIME NOT NULL,
    taken_at            DATETIME,
    latitude            REAL,
    longitude           REAL,
    uploader_user_id    TEXT,

    stage_a_is_food     INTEGER,                            -- BOOLEAN as 0/1
    stage_a_confidence  REAL,
    stage_a_model       TEXT,
    stage_a_ran_at      DATETIME,

    dish_name           TEXT,
    cuisine             TEXT,
    stage_b_confidence  REAL,
    stage_b_model       TEXT,
    stage_b_ran_at      DATETIME,
    stage_b_raw_json    TEXT,

    venue_type          TEXT,
    place_id            TEXT,
    place_match_source  TEXT,
    place_match_distance_m  REAL,

    review_status       TEXT NOT NULL DEFAULT 'auto',
    reviewed_at         DATETIME,
    review_notes        TEXT,

    last_error          TEXT,
    error_attempts      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_photo_taken_at ON photo_analysis(taken_at);
CREATE INDEX idx_photo_place    ON photo_analysis(place_id);
CREATE INDEX idx_photo_review   ON photo_analysis(review_status);

CREATE TABLE places (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    radius_m        INTEGER NOT NULL DEFAULT 50,
    google_place_id TEXT,
    address         TEXT,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    notes           TEXT
);
CREATE INDEX idx_places_type ON places(type);

CREATE TABLE worker_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       DATETIME NOT NULL,
    finished_at      DATETIME,
    assets_seen      INTEGER DEFAULT 0,
    assets_processed INTEGER DEFAULT 0,
    errors           INTEGER DEFAULT 0,
    notes            TEXT
);

CREATE TABLE worker_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_migration_001.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd home_photo_repo
git add migrations/001_initial.sql tests/test_migration_001.py
git commit -m "feat: initial schema migration (photo_analysis, places, worker_runs, worker_state)"
```

---

## Task 6: Immich REST client

**Files:**
- Create: `tests/fixtures/immich_search_metadata.json`
- Create: `src/home_photo_repo/immich_types.py`
- Create: `src/home_photo_repo/immich_client.py`
- Create: `tests/test_immich_client.py`

- [ ] **Step 1: Create the fixture — `tests/fixtures/immich_search_metadata.json`**

This is a trimmed, representative sample of the response shape from `POST /api/search/metadata`. Two assets: one with GPS, one without.

```json
{
  "assets": {
    "total": 2,
    "count": 2,
    "items": [
      {
        "id": "asset-uuid-1",
        "ownerId": "user-uuid-a",
        "originalFileName": "IMG_0001.HEIC",
        "fileCreatedAt": "2026-05-27T18:42:11.000Z",
        "updatedAt": "2026-05-27T18:42:15.000Z",
        "type": "IMAGE",
        "exifInfo": {
          "latitude": 37.7749,
          "longitude": -122.4194,
          "dateTimeOriginal": "2026-05-27T11:42:09.000-07:00",
          "make": "Apple",
          "model": "iPhone 15 Pro"
        }
      },
      {
        "id": "asset-uuid-2",
        "ownerId": "user-uuid-b",
        "originalFileName": "IMG_0002.HEIC",
        "fileCreatedAt": "2026-05-28T09:00:00.000Z",
        "updatedAt": "2026-05-28T09:00:03.000Z",
        "type": "IMAGE",
        "exifInfo": {
          "latitude": null,
          "longitude": null,
          "dateTimeOriginal": null,
          "make": "Apple",
          "model": "iPhone 13"
        }
      }
    ],
    "facets": [],
    "nextPage": null
  },
  "albums": {"total": 0, "count": 0, "items": [], "facets": []}
}
```

- [ ] **Step 2: Write the failing test — `tests/test_immich_client.py`**

```python
"""Tests for the Immich REST client.

All HTTP is mocked with respx; the test runner has sockets disabled.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from home_photo_repo.immich_client import ImmichClient, ImmichClientError

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client() -> ImmichClient:
    return ImmichClient(base_url="http://immich.local:2283", api_key="test-key")


@respx.mock
def test_search_metadata_happy_path() -> None:
    route = respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=_load_fixture("immich_search_metadata.json"))
    )
    client = _client()
    assets = client.search_metadata(
        updated_after=datetime(2026, 5, 27, tzinfo=timezone.utc), size=100
    )
    assert route.called
    # The request body should include the cursor and pagination.
    body = json.loads(route.calls.last.request.content)
    assert body["updatedAfter"] == "2026-05-27T00:00:00+00:00"
    assert body["size"] == 100
    assert body["order"] == "asc"
    assert body["withExif"] is True
    # Result shape: a list of assets with parsed GPS where present.
    assert len(assets) == 2
    assert assets[0].id == "asset-uuid-1"
    assert assets[0].latitude == pytest.approx(37.7749)
    assert assets[0].longitude == pytest.approx(-122.4194)
    assert assets[0].owner_id == "user-uuid-a"
    assert assets[1].latitude is None
    assert assets[1].longitude is None


@respx.mock
def test_search_metadata_sends_api_key_header() -> None:
    route = respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json={"assets": {"items": []}})
    )
    _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=timezone.utc))
    assert route.calls.last.request.headers["x-api-key"] == "test-key"


@respx.mock
def test_search_metadata_401_raises() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(401, json={"message": "unauthorized"})
    )
    with pytest.raises(ImmichClientError):
        _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=timezone.utc))


@respx.mock
def test_search_metadata_5xx_raises() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(ImmichClientError):
        _client().search_metadata(updated_after=datetime(2026, 5, 27, tzinfo=timezone.utc))


@respx.mock
def test_search_metadata_handles_empty_items() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json={"assets": {"items": []}})
    )
    assets = _client().search_metadata(
        updated_after=datetime(2026, 5, 27, tzinfo=timezone.utc)
    )
    assert assets == []


@respx.mock
def test_search_metadata_parses_taken_at_as_utc() -> None:
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=_load_fixture("immich_search_metadata.json"))
    )
    assets = _client().search_metadata(
        updated_after=datetime(2026, 5, 27, tzinfo=timezone.utc)
    )
    # dateTimeOriginal "2026-05-27T11:42:09.000-07:00" → 2026-05-27T18:42:09+00:00
    assert assets[0].taken_at == datetime(2026, 5, 27, 18, 42, 9, tzinfo=timezone.utc)
    # updatedAt "2026-05-27T18:42:15.000Z"
    assert assets[0].updated_at == datetime(2026, 5, 27, 18, 42, 15, tzinfo=timezone.utc)
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_immich_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'home_photo_repo.immich_client'`.

- [ ] **Step 4: Implement `src/home_photo_repo/immich_types.py`**

```python
"""Typed value objects for Immich API responses we consume."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ImmichAsset:
    id: str
    owner_id: str
    original_file_name: str
    updated_at: datetime
    taken_at: datetime | None
    latitude: float | None
    longitude: float | None
    file_created_at: datetime | None


__all__ = ["ImmichAsset"]
```

- [ ] **Step 5: Implement `src/home_photo_repo/immich_client.py`**

```python
"""Thin HTTP client for the subset of Immich's REST API we use."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from home_photo_repo.immich_types import ImmichAsset


class ImmichClientError(RuntimeError):
    """Raised when Immich returns a non-2xx response or a malformed body."""


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string from Immich and normalize to UTC.

    Immich returns timestamps with either `Z` or an explicit offset;
    `fromisoformat` in 3.11+ handles both once `Z` is replaced with `+00:00`.
    We always normalize to UTC so equality comparisons in tests work.
    """
    if not value:
        return None
    from datetime import timezone

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ImmichClient:
    """Minimal Immich client. All methods are synchronous; the worker is sequential."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key, "Accept": "application/json"}
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    # --- public API ---------------------------------------------------------

    def search_metadata(
        self,
        *,
        updated_after: datetime,
        size: int = 100,
        order: str = "asc",
    ) -> list[ImmichAsset]:
        """Fetch assets updated after `updated_after`, oldest-first by default."""
        body = {
            "updatedAfter": updated_after.isoformat(),
            "withExif": True,
            "order": order,
            "size": size,
        }
        resp = self._post("/api/search/metadata", json=body)
        try:
            items = resp["assets"]["items"]
        except (KeyError, TypeError) as e:
            raise ImmichClientError(f"unexpected response shape: {e!r}") from e
        return [self._parse_asset(item) for item in items]

    # --- internals ----------------------------------------------------------

    def _post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = self._client.post(url, headers=self._headers, json=json)
        except httpx.HTTPError as e:
            raise ImmichClientError(f"network error calling {path}: {e!r}") from e
        if response.status_code >= 400:
            raise ImmichClientError(
                f"Immich {path} returned {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as e:
            raise ImmichClientError(f"non-JSON response from {path}") from e
        if not isinstance(data, dict):
            raise ImmichClientError(f"non-object JSON response from {path}")
        return data

    @staticmethod
    def _parse_asset(item: dict[str, Any]) -> ImmichAsset:
        exif = item.get("exifInfo") or {}
        return ImmichAsset(
            id=item["id"],
            owner_id=item.get("ownerId", ""),
            original_file_name=item.get("originalFileName", ""),
            updated_at=_parse_dt(item["updatedAt"]),  # type: ignore[arg-type]
            taken_at=_parse_dt(exif.get("dateTimeOriginal")),
            latitude=exif.get("latitude"),
            longitude=exif.get("longitude"),
            file_created_at=_parse_dt(item.get("fileCreatedAt")),
        )


__all__ = ["ImmichClient", "ImmichClientError"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_immich_client.py -v
```
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
cd home_photo_repo
git add src/home_photo_repo/immich_client.py src/home_photo_repo/immich_types.py tests/test_immich_client.py tests/fixtures/immich_search_metadata.json
git commit -m "feat: immich rest client with search_metadata + parsed asset DTOs"
```

---

## Task 7: Pipeline — `process_asset` (discovered state only)

**Files:**
- Create: `src/home_photo_repo/worker/__init__.py`
- Create: `src/home_photo_repo/worker/pipeline.py`
- Create: `tests/test_pipeline.py`

The Plan-1 pipeline does one thing: take an `ImmichAsset` and insert/update a `discovered`-state row in `photo_analysis`. Plan 2 adds Stage A/B transitions; Plan 3 adds place matching.

**Readiness rule (spec §3.3):** if `latitude is None` and the asset is younger than 10 minutes (by `updated_at`), skip it for now — let the next poll cycle catch it after Immich's EXIF job completes. If it's older than 10 minutes and still has no GPS, record the row with `review_status='needs_review'` and `last_error='no_gps'`.

- [ ] **Step 1: Write the failing test — `tests/test_pipeline.py`**

```python
"""Tests for the Plan-1 pipeline: insert discovered rows idempotently."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.worker.pipeline import (
    READINESS_MAX_AGE,
    ProcessResult,
    process_asset,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset(
    *,
    aid: str = "asset-1",
    lat: float | None = 37.7749,
    lon: float | None = -122.4194,
    updated_at: datetime | None = None,
) -> ImmichAsset:
    now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    return ImmichAsset(
        id=aid,
        owner_id="owner-x",
        original_file_name="IMG.HEIC",
        updated_at=updated_at or now,
        taken_at=now - timedelta(hours=1),
        latitude=lat,
        longitude=lon,
        file_created_at=now,
    )


def test_process_asset_inserts_discovered_row(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    a = _asset()
    now = a.updated_at

    result = process_asset(conn, a, now=now)

    assert result is ProcessResult.INSERTED
    row = conn.execute(
        "SELECT immich_asset_id, latitude, longitude, uploader_user_id, review_status "
        "FROM photo_analysis WHERE immich_asset_id = ?",
        (a.id,),
    ).fetchone()
    assert row is not None
    assert row["latitude"] == pytest.approx(37.7749)
    assert row["longitude"] == pytest.approx(-122.4194)
    assert row["uploader_user_id"] == "owner-x"
    assert row["review_status"] == "auto"


def test_process_asset_is_idempotent(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    a = _asset()
    now = a.updated_at

    assert process_asset(conn, a, now=now) is ProcessResult.INSERTED
    assert process_asset(conn, a, now=now) is ProcessResult.ALREADY_PRESENT

    count = conn.execute(
        "SELECT COUNT(*) FROM photo_analysis WHERE immich_asset_id = ?", (a.id,)
    ).fetchone()[0]
    assert count == 1


def test_process_asset_skips_young_gpsless_asset(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    young_updated = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    now = young_updated + (READINESS_MAX_AGE / 2)  # within readiness window
    a = _asset(lat=None, lon=None, updated_at=young_updated)

    result = process_asset(conn, a, now=now)

    assert result is ProcessResult.DEFERRED_NOT_READY
    count = conn.execute("SELECT COUNT(*) FROM photo_analysis").fetchone()[0]
    assert count == 0


def test_process_asset_records_old_gpsless_for_review(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    old_updated = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    now = old_updated + READINESS_MAX_AGE + timedelta(seconds=1)
    a = _asset(lat=None, lon=None, updated_at=old_updated)

    result = process_asset(conn, a, now=now)

    assert result is ProcessResult.INSERTED
    row = conn.execute(
        "SELECT review_status, last_error FROM photo_analysis WHERE immich_asset_id = ?",
        (a.id,),
    ).fetchone()
    assert row["review_status"] == "needs_review"
    assert row["last_error"] == "no_gps"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_pipeline.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/home_photo_repo/worker/__init__.py`**

```python
"""Worker package — ingestion polling loop and per-asset pipeline."""
```

- [ ] **Step 4: Implement `src/home_photo_repo/worker/pipeline.py`**

```python
"""Per-asset pipeline.

Plan 1 scope: insert a `discovered` row, idempotent on immich_asset_id,
respecting a readiness window that lets Immich's EXIF job finish before
we either record-or-defer GPS-less photos.
"""

from __future__ import annotations

import enum
import sqlite3
from datetime import datetime, timedelta, timezone

from home_photo_repo.immich_types import ImmichAsset

READINESS_MAX_AGE: timedelta = timedelta(minutes=10)


class ProcessResult(enum.Enum):
    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"
    DEFERRED_NOT_READY = "deferred_not_ready"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def process_asset(
    conn: sqlite3.Connection,
    asset: ImmichAsset,
    *,
    now: datetime | None = None,
) -> ProcessResult:
    """Insert (or no-op) one Immich asset into photo_analysis.

    `now` is injectable for tests. In production callers pass nothing.
    """
    current_time = now or _utcnow()

    # Idempotency: skip if already present.
    existing = conn.execute(
        "SELECT 1 FROM photo_analysis WHERE immich_asset_id = ?", (asset.id,)
    ).fetchone()
    if existing is not None:
        return ProcessResult.ALREADY_PRESENT

    # Readiness check: if GPS is missing and the asset is recent,
    # defer — Immich's EXIF job may not have completed yet.
    has_gps = asset.latitude is not None and asset.longitude is not None
    age = current_time - asset.updated_at
    if not has_gps and age < READINESS_MAX_AGE:
        return ProcessResult.DEFERRED_NOT_READY

    review_status = "auto" if has_gps else "needs_review"
    last_error = None if has_gps else "no_gps"

    conn.execute(
        """
        INSERT INTO photo_analysis (
            immich_asset_id, first_seen_at, taken_at, latitude, longitude,
            uploader_user_id, review_status, last_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset.id,
            current_time.isoformat(),
            asset.taken_at.isoformat() if asset.taken_at else None,
            asset.latitude,
            asset.longitude,
            asset.owner_id or None,
            review_status,
            last_error,
        ),
    )
    return ProcessResult.INSERTED


__all__ = ["READINESS_MAX_AGE", "ProcessResult", "process_asset"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd home_photo_repo && uv run pytest tests/test_pipeline.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd home_photo_repo
git add src/home_photo_repo/worker/__init__.py src/home_photo_repo/worker/pipeline.py tests/test_pipeline.py
git commit -m "feat: per-asset pipeline inserts discovered rows with readiness gating"
```

---

## Task 8: Cursor + main loop

**Files:**
- Create: `src/home_photo_repo/worker/cursor.py`
- Create: `tests/test_cursor.py`
- Create: `src/home_photo_repo/worker/main.py`
- Create: `tests/test_worker_main.py`

### Part A — Cursor

- [ ] **Step 1: Write the failing test — `tests/test_cursor.py`**

```python
"""Tests for cursor persistence in worker_state."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.worker.cursor import EPOCH_CURSOR, read_cursor, write_cursor

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _conn(tmp_path: Path):
    c = get_connection(tmp_path / "app.sqlite")
    apply_migrations(c, MIGRATIONS)
    return c


def test_read_cursor_defaults_to_epoch(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assert read_cursor(conn) == EPOCH_CURSOR


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    write_cursor(conn, ts)
    assert read_cursor(conn) == ts


def test_write_cursor_is_monotonic(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    later = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    earlier = datetime(2025, 1, 1, tzinfo=timezone.utc)
    write_cursor(conn, later)
    write_cursor(conn, earlier)  # must not regress
    assert read_cursor(conn) == later
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd home_photo_repo && uv run pytest tests/test_cursor.py -v
```

- [ ] **Step 3: Implement `src/home_photo_repo/worker/cursor.py`**

```python
"""Persistent ingestion cursor stored in worker_state."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

CURSOR_KEY = "immich_cursor"
EPOCH_CURSOR: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)


def read_cursor(conn: sqlite3.Connection) -> datetime:
    row = conn.execute(
        "SELECT value FROM worker_state WHERE key = ?", (CURSOR_KEY,)
    ).fetchone()
    if row is None:
        return EPOCH_CURSOR
    return datetime.fromisoformat(row["value"])


def write_cursor(conn: sqlite3.Connection, ts: datetime) -> None:
    """Write `ts` if it is strictly greater than the current cursor; otherwise no-op."""
    current = read_cursor(conn)
    if ts <= current:
        return
    conn.execute(
        """
        INSERT INTO worker_state (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (CURSOR_KEY, ts.isoformat()),
    )


__all__ = ["CURSOR_KEY", "EPOCH_CURSOR", "read_cursor", "write_cursor"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd home_photo_repo && uv run pytest tests/test_cursor.py -v
```
Expected: 3 passed.

### Part B — Main loop

- [ ] **Step 5: Write the failing test — `tests/test_worker_main.py`**

```python
"""Tests for the worker main loop's run_once() function.

We test the loop with a fake ImmichClient so no HTTP is involved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.worker.cursor import EPOCH_CURSOR, read_cursor
from home_photo_repo.worker.main import RunSummary, run_once

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


class FakeImmich:
    def __init__(self, batches: list[list[ImmichAsset]]):
        self._batches = list(batches)
        self.calls: list[dict[str, Any]] = []

    def search_metadata(self, *, updated_after, size=100, order="asc"):
        self.calls.append({"updated_after": updated_after, "size": size, "order": order})
        if not self._batches:
            return []
        return self._batches.pop(0)


def _conn(tmp_path: Path):
    c = get_connection(tmp_path / "app.sqlite")
    apply_migrations(c, MIGRATIONS)
    return c


def _asset(aid: str, updated_offset_sec: int) -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    return ImmichAsset(
        id=aid,
        owner_id="owner-x",
        original_file_name=f"{aid}.HEIC",
        updated_at=base + timedelta(seconds=updated_offset_sec),
        taken_at=base,
        latitude=37.0,
        longitude=-122.0,
        file_created_at=base,
    )


def test_run_once_processes_assets_and_advances_cursor(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assets = [_asset("a", 1), _asset("b", 2), _asset("c", 3)]
    fake = FakeImmich(batches=[assets, []])  # second call returns empty → stop
    fixed_now = datetime(2026, 5, 28, 13, 0, 0, tzinfo=timezone.utc)  # later than all updates

    summary = run_once(conn, fake, batch_size=100, now=fixed_now)

    assert isinstance(summary, RunSummary)
    assert summary.assets_seen == 3
    assert summary.assets_processed == 3
    assert summary.errors == 0
    # Cursor advanced to the latest updated_at
    assert read_cursor(conn) == assets[-1].updated_at
    # Initial call used EPOCH_CURSOR
    assert fake.calls[0]["updated_after"] == EPOCH_CURSOR


def test_run_once_catches_up_when_batch_full(tmp_path: Path) -> None:
    """Full batch (== batch_size) triggers an immediate catch-up call.
    A partial batch (< batch_size) means we're caught up; loop exits.
    """
    conn = _conn(tmp_path)
    batch1 = [_asset(f"a{i}", i + 1) for i in range(3)]      # full
    batch2 = [_asset(f"b{i}", 100 + i) for i in range(2)]    # partial → stop
    fake = FakeImmich(batches=[batch1, batch2])
    fixed_now = datetime(2026, 5, 28, 14, 0, 0, tzinfo=timezone.utc)

    summary = run_once(conn, fake, batch_size=3, now=fixed_now)

    assert summary.assets_seen == 5
    assert summary.assets_processed == 5
    assert len(fake.calls) == 2  # batch1 was full → catch-up; batch2 was partial → done


def test_run_once_records_run_in_worker_runs(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    fake = FakeImmich(batches=[[]])
    fixed_now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)

    run_once(conn, fake, batch_size=100, now=fixed_now)

    rows = conn.execute(
        "SELECT assets_seen, assets_processed, errors, finished_at FROM worker_runs"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["finished_at"] is not None


def test_run_once_on_immich_error_records_error_and_does_not_advance(tmp_path: Path) -> None:
    from home_photo_repo.immich_client import ImmichClientError

    class BrokenImmich:
        calls = 0

        def search_metadata(self, *, updated_after, size=100, order="asc"):
            BrokenImmich.calls += 1
            raise ImmichClientError("simulated outage")

    conn = _conn(tmp_path)
    fixed_now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    summary = run_once(conn, BrokenImmich(), batch_size=100, now=fixed_now)

    assert summary.errors == 1
    assert read_cursor(conn) == EPOCH_CURSOR  # unchanged
    row = conn.execute("SELECT errors, notes FROM worker_runs").fetchone()
    assert row["errors"] == 1
    assert "simulated outage" in (row["notes"] or "")
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
cd home_photo_repo && uv run pytest tests/test_worker_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'home_photo_repo.worker.main'`.

- [ ] **Step 7: Implement `src/home_photo_repo/worker/main.py`**

```python
"""Worker main loop.

`run_once` does one poll-and-catch-up cycle: it fetches assets newer than the
cursor and processes each through the pipeline, advancing the cursor per-asset.
It loops internally as long as Immich returns full batches (catch-up).

`run_forever` schedules `run_once` on a timer with sleep-between-polls.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from home_photo_repo.config import Settings
from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_client import ImmichClient, ImmichClientError
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.worker.cursor import read_cursor, write_cursor
from home_photo_repo.worker.pipeline import ProcessResult, process_asset

log = logging.getLogger(__name__)


class _ImmichLike(Protocol):
    def search_metadata(
        self, *, updated_after: datetime, size: int = ..., order: str = ...
    ) -> list[ImmichAsset]: ...


@dataclass
class RunSummary:
    assets_seen: int = 0
    assets_processed: int = 0
    errors: int = 0
    last_error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def run_once(
    conn: sqlite3.Connection,
    immich: _ImmichLike,
    *,
    batch_size: int,
    now: datetime | None = None,
) -> RunSummary:
    """Poll Immich until it returns a non-full batch; process every asset."""
    summary = RunSummary()
    current_time = now or _utcnow()

    run_id = _begin_run(conn, current_time)
    try:
        while True:
            cursor = read_cursor(conn)
            try:
                assets = immich.search_metadata(
                    updated_after=cursor, size=batch_size, order="asc"
                )
            except ImmichClientError as e:
                summary.errors += 1
                summary.last_error = str(e)
                log.error("immich poll failed: %s", e)
                break

            if not assets:
                break

            for asset in assets:
                summary.assets_seen += 1
                try:
                    result = process_asset(conn, asset, now=current_time)
                except Exception as e:  # noqa: BLE001 - per-asset isolation
                    summary.errors += 1
                    summary.last_error = f"{asset.id}: {e!r}"
                    log.exception("pipeline failed on asset %s", asset.id)
                    # Do NOT advance the cursor past a failed asset.
                    break
                else:
                    if result is not ProcessResult.DEFERRED_NOT_READY:
                        summary.assets_processed += 1
                    write_cursor(conn, asset.updated_at)
            else:
                # whole batch processed without break
                if len(assets) < batch_size:
                    break
                continue
            break  # broke out of for-loop due to per-asset failure
    finally:
        _finish_run(conn, run_id, summary)
    return summary


def _begin_run(conn: sqlite3.Connection, now: datetime) -> int:
    cur = conn.execute(
        "INSERT INTO worker_runs (started_at) VALUES (?)", (now.isoformat(),)
    )
    return int(cur.lastrowid)


def _finish_run(conn: sqlite3.Connection, run_id: int, summary: RunSummary) -> None:
    conn.execute(
        """
        UPDATE worker_runs
           SET finished_at      = datetime('now'),
               assets_seen      = ?,
               assets_processed = ?,
               errors           = ?,
               notes            = ?
         WHERE id = ?
        """,
        (
            summary.assets_seen,
            summary.assets_processed,
            summary.errors,
            summary.last_error,
            run_id,
        ),
    )


def run_forever(settings: Settings) -> None:  # pragma: no cover - integration entrypoint
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    repo_root = Path(__file__).resolve().parents[3]
    conn = get_connection(settings.db_path)
    apply_migrations(conn, repo_root / "migrations")
    immich = ImmichClient(
        base_url=str(settings.immich_base_url),
        api_key=settings.immich_api_key.get_secret_value(),
    )
    log.info(
        "worker starting: poll_interval=%ss batch_size=%s db=%s",
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
    )
    try:
        while True:
            summary = run_once(conn, immich, batch_size=settings.backfill_batch_size)
            log.info(
                "run complete: seen=%d processed=%d errors=%d",
                summary.assets_seen,
                summary.assets_processed,
                summary.errors,
            )
            time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        log.info("worker shutting down (KeyboardInterrupt)")
    finally:
        immich.close()
        conn.close()


def main() -> None:  # pragma: no cover - process entrypoint
    settings = Settings()
    run_forever(settings)


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd home_photo_repo && uv run pytest tests/test_worker_main.py tests/test_cursor.py -v
```
Expected: 7 passed.

- [ ] **Step 9: Run the full suite to confirm nothing regressed**

```bash
cd home_photo_repo && uv run pytest -v
```
Expected: all tests across all files pass.

- [ ] **Step 10: Commit**

```bash
cd home_photo_repo
git add src/home_photo_repo/worker/cursor.py src/home_photo_repo/worker/main.py tests/test_cursor.py tests/test_worker_main.py
git commit -m "feat: worker main loop with cursor, catch-up batching, and run logging"
```

---

## Task 9: Smoke script + Makefile target

The smoke script is the only Plan-1 artifact that touches the real network — it is not run as part of `pytest`. It exists so the user can manually verify `IMMICH_BASE_URL` and `IMMICH_API_KEY` are valid before relying on the worker.

**Files:**
- Create: `scripts/smoke_immich.py`
- Modify: `Makefile` (add `smoke-immich` target)

- [ ] **Step 1: Create `scripts/smoke_immich.py`**

```python
"""Manual smoke test: list the 5 most recently updated assets from Immich.

Run with:
    make smoke-immich
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from home_photo_repo.config import Settings
from home_photo_repo.immich_client import ImmichClient


def main() -> None:
    settings = Settings()
    client = ImmichClient(
        base_url=str(settings.immich_base_url),
        api_key=settings.immich_api_key.get_secret_value(),
    )
    # Look back 30 days so the script works on quiet days.
    since = datetime.now(tz=timezone.utc) - timedelta(days=30)
    assets = client.search_metadata(updated_after=since, size=5, order="asc")
    print(f"Connected to {settings.immich_base_url}; got {len(assets)} assets:")
    for a in assets:
        gps = (
            f"({a.latitude:.4f},{a.longitude:.4f})"
            if a.latitude is not None and a.longitude is not None
            else "(no gps)"
        )
        print(f"  - {a.id}  {a.original_file_name}  updated={a.updated_at}  {gps}")
    client.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add `smoke-immich` target to `Makefile`**

Append to `Makefile`:
```makefile

smoke-immich:
	$(PYTHON) scripts/smoke_immich.py
```

- [ ] **Step 3: Verify the script imports cleanly (no run, no network)**

Run:
```bash
cd home_photo_repo && uv run python -c "import scripts.smoke_immich as m; print('ok')"
```
Expected: prints `ok` (no exception). `scripts/` is not a package; if the import fails because of that, instead verify by:
```bash
cd home_photo_repo && uv run python -c "from home_photo_repo.config import Settings; from home_photo_repo.immich_client import ImmichClient; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
cd home_photo_repo
git add scripts/smoke_immich.py Makefile
git commit -m "feat: smoke-immich script and make target for manual verification"
```

---

## Task 10: Lint, type-check, and finalize README

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml` (only if mypy needs an exclude for `scripts/`)

- [ ] **Step 1: Run `ruff` and fix any reported issues**

Run:
```bash
cd home_photo_repo && uv run ruff check src tests
```
Expected: clean. If anything is flagged, fix in place. Run again to confirm.

- [ ] **Step 2: Run `mypy` and fix any reported issues**

Run:
```bash
cd home_photo_repo && uv run mypy
```
Expected: clean. If mypy complains about `scripts/`, add to `pyproject.toml`:
```toml
[tool.mypy]
# ... existing ...
exclude = ["scripts/"]
```
Re-run.

- [ ] **Step 3: Run the full test suite one more time**

```bash
cd home_photo_repo && uv run pytest -v
```
Expected: all tests pass; exit 0.

- [ ] **Step 4: Replace `README.md` with the full version**

```markdown
# home_photo_repo

Local home-photo ingestion + analysis service. Sits on top of a self-hosted
[Immich](https://immich.app/) instance and (in later plans) adds food/dish
recognition and venue tagging (restaurant via GPS / home / office / etc.),
plus a localhost dashboard.

This is **Plan 1 (Foundation & Ingestion)**. At this stage the project is
just the ingestion plumbing: a Python worker polls Immich every 5 minutes
and inserts a row per new asset into a local SQLite database. No LLM, no
place matching, no dashboard yet.

See `docs/specs/2026-05-28-home-photo-repo-design.md` for the full design
and `docs/plans/` for per-phase implementation plans.

## Prerequisites

- macOS with Apple Silicon recommended (Intel works for Plan 1)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [`uv`](https://github.com/astral-sh/uv) for Python dep management
- An external SSD (APFS-formatted) for production; for dev you can use a
  local path

## Setup

### 1. Run Immich

See `docker/immich/README.md`. In short:
```bash
cp docker/immich/.env.example docker/immich/.env
# edit paths and DB_PASSWORD
cd docker/immich && docker compose up -d
```
Open http://localhost:2283, create the admin account and per-family-member
accounts, generate an API key under Account → API Keys.

### 2. Configure home_photo_repo

```bash
cp .env.example .env
chmod 600 .env
# edit IMMICH_BASE_URL, IMMICH_API_KEY, SSD_DATA_DIR
```

### 3. Bootstrap

```bash
make bootstrap
```

This creates the virtualenv, installs deps, creates the data directories,
and applies database migrations.

### 4. Verify

```bash
make smoke-immich
```
Should print up to 5 recent assets from your Immich instance.

### 5. Run the worker

```bash
make dev-worker
```
The worker polls every 5 minutes. Take a photo on a paired iPhone (or copy
one into Immich via the web UI); within 5–10 minutes you should see a row
appear:

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT immich_asset_id, latitude, longitude, taken_at FROM photo_analysis ORDER BY first_seen_at DESC LIMIT 5;"
```

## Development

```bash
make test         # pytest, no network
make lint         # ruff
make typecheck    # mypy
make format       # ruff format
```

All tests are offline (`pytest-socket` blocks sockets). HTTP behavior is
covered by `respx`-mocked tests for the Immich client.

## Project layout

```
src/home_photo_repo/
├── config.py            # pydantic-settings; loads .env
├── db.py                # sqlite + forward-only migration runner
├── immich_client.py     # thin httpx client for Immich REST
├── immich_types.py      # typed dataclasses for Immich responses
└── worker/
    ├── cursor.py        # persistent ingestion cursor
    ├── main.py          # poll loop, run_once / run_forever
    └── pipeline.py      # per-asset state machine (Plan 1: discovered only)

migrations/              # forward-only .sql files
docker/immich/           # Immich docker compose config
scripts/                 # smoke tests, one-shot tools
tests/                   # pytest suite, no network
```

## Roadmap (subsequent plans)

- **Plan 2** — LLM pipeline: Stage A (Haiku is-this-food) + Stage B
  (Sonnet dish + venue) with a pluggable provider interface (Anthropic
  default, MLX optional).
- **Plan 3** — Place matching: curated personal places + Google Places
  fallback for restaurant resolution.
- **Plan 4** — FastAPI + HTMX + Leaflet dashboard at `localhost:8000`.
- **Plan 5** — Operations: launchd plists, nightly pg_dumpall, MLX
  setup, migration to a new Mac.
```

- [ ] **Step 5: Final full-suite + lint + typecheck pass**

```bash
cd home_photo_repo && uv run pytest -v && uv run ruff check src tests && uv run mypy
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd home_photo_repo
git add README.md pyproject.toml
git commit -m "docs: complete README for Plan 1 (setup, run, verify, roadmap)"
```

---

## Plan 1 — Acceptance checklist

When the user is ready to mark Plan 1 done, verify each:

- [ ] `make test` exits 0 with all tests passing
- [ ] `make lint` and `make typecheck` are clean
- [ ] `make bootstrap` succeeds on a fresh checkout (modulo Immich being up)
- [ ] `make smoke-immich` lists real assets from a running local Immich
- [ ] `make dev-worker` runs without errors and, after an iPhone upload, a
      new row appears in `photo_analysis` within ~10 minutes
- [ ] Stopping (Ctrl-C) and restarting the worker does not re-process the
      same asset (cursor advanced; `INSERT OR IGNORE`-equivalent path
      returns `ALREADY_PRESENT`)
- [ ] No secrets appear in any log line or `repr()` output

Once green, Plan 1 is complete. Move on to Plan 2 (LLM pipeline).
