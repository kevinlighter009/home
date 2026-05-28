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
