# home_photo_repo

Local home-photo ingestion + analysis service. Sits on top of a self-hosted
[Immich](https://immich.app/) instance and (in later plans) adds food/dish
recognition and venue tagging (restaurant via GPS / home / office / etc.),
plus a localhost dashboard.

This is **Plan 2 (LLM Pipeline)**. The worker now classifies each ingested
photo: Stage A (Claude Haiku 4.5) decides whether the photo is food, and
food photos additionally get Stage B (Claude Sonnet 4.5) which fills in
`dish_name` and `cuisine`. Venue / restaurant assignment is Plan 3.

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

## LLM provider selection

By default, both stages use Anthropic Claude (`claude-haiku-4-5` for Stage A,
`claude-sonnet-4-5` for Stage B). To switch a stage to a local MLX-served
model, set in `.env`:

```dotenv
LLM_STAGE_A_PROVIDER=mlx
MLX_STAGE_A_MODEL=mlx-community/Qwen2-VL-2B-Instruct-4bit
```

You also need an MLX server running locally on `http://localhost:8081/v1` —
the easiest path is:

```bash
pip install mlx-vlm
mlx_vlm.server --model mlx-community/Qwen2-VL-2B-Instruct-4bit --port 8081
```

The MLX server is **optional** and not installed by `make bootstrap`.

### Verifying the LLM pipeline

After bootstrap and with `ANTHROPIC_API_KEY` set in `.env`:

```bash
make smoke-llm
```

Should print a Stage A result on a synthetic tiny image — proves the API
key, model name, and JSON parsing all work end-to-end.

When the worker is running (`make dev-worker`), check the populated rows:

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT immich_asset_id, stage_a_is_food, dish_name, cuisine, review_status \
   FROM photo_analysis WHERE stage_a_ran_at IS NOT NULL \
   ORDER BY stage_a_ran_at DESC LIMIT 10;"
```

## Project layout

```
src/home_photo_repo/
├── config.py
├── settings_factory.py     # load_settings()
├── db.py
├── immich_client.py        # search_metadata + get_thumbnail + get_original
├── immich_types.py
├── llm/
│   ├── factory.py          # build_provider(role, settings)
│   ├── prompts.py          # versioned Stage A/B prompts + schemas
│   ├── rate_limiter.py     # token bucket
│   ├── stage_a.py          # run_stage_a(provider, image_bytes)
│   ├── stage_b.py          # run_stage_b(provider, image_bytes)
│   └── providers/
│       ├── base.py         # VisionLLMProvider Protocol
│       ├── anthropic_provider.py
│       └── mlx_provider.py
└── worker/
    ├── cursor.py           # composite (updated_at, id) cursor
    ├── main.py             # poll loop, build providers, run_once
    └── pipeline.py         # discovered → Stage A → maybe Stage B

migrations/              # forward-only .sql files
docker/immich/           # Immich docker compose config
scripts/                 # smoke tests, one-shot tools
tests/                   # pytest suite, no network
```

## Roadmap (subsequent plans)

- **Plan 2** ✅ Done — Stage A (Haiku) + Stage B (Sonnet) with pluggable
  provider interface (Anthropic default, MLX optional).
- **Plan 3** — Place matching: curated personal places + Google Places
  fallback for restaurant resolution.
- **Plan 4** — FastAPI + HTMX + Leaflet dashboard at `localhost:8000`.
- **Plan 5** — Operations: launchd plists, nightly pg_dumpall, MLX
  setup, migration to a new Mac.
