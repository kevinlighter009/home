# home_photo_repo

Local home-photo ingestion + analysis service. Sits on top of a self-hosted
[Immich](https://immich.app/) instance and (in later plans) adds food/dish
recognition and venue tagging (restaurant via GPS / home / office / etc.),
plus a localhost dashboard.

This is **Plan 3 (Place Matching)**. After Stage B identifies dish + cuisine,
the worker resolves the photo's GPS to a venue: either a user-curated
place (home / office / friend's place / a favorite restaurant) or a
restaurant looked up via Google Places. Results land in
`photo_analysis.venue_type` + `place_id`. Plan 4 will surface this in a
dashboard.

**👉 New to this project? See [`docs/SETUP.md`](docs/SETUP.md) for the
complete fresh-Mac setup guide (Docker, Python, Immich, Anthropic key,
iPhone app — everything).**

See `docs/specs/2026-05-28-home-photo-repo-design.md` for the full design
and `docs/plans/` for per-phase implementation plans.

## Prerequisites

- macOS with Apple Silicon recommended (Intel works for Plan 1)
- Python 3.12+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Either [`uv`](https://github.com/astral-sh/uv) (recommended) **or** conda/pip
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

### 3. Install dependencies

**Option A — `uv` (recommended, fastest):**
```bash
make bootstrap
```
Creates `.venv`, installs deps via `uv sync --all-extras`, creates data
directories, applies database migrations.

**Option B — conda + pip:**
```bash
conda create -n home_photo_repo python=3.12
conda activate home_photo_repo
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .                          # install the project itself
mkdir -p $SSD_DATA_DIR/{db,logs}          # or default ~/home_photo_repo_data/{db,logs}
python -m home_photo_repo.db migrate      # apply DB migrations
```

**Option C — plain pip + venv:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
mkdir -p $SSD_DATA_DIR/{db,logs}
python -m home_photo_repo.db migrate
```

For options B and C the Makefile targets that begin with `uv run …` won't
work; substitute plain `python` / `pytest` / `ruff` / `mypy` instead (the
venv must be activated).

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

## Curated places & Google Places

The pipeline resolves each food photo to a venue. Curated places (the
ones you care about — home, office, friends' places, favorite
restaurants) are looked up first from the local `places` table; anything
unmatched falls back to a Google Places Nearby Search.

### Setting up Google Places (optional)

The worker runs fine without a Google Places key — photos at unrecognized
locations just get `venue_type='unknown'` and `review_status='needs_review'`.
To enable the fallback:

1. Open https://console.cloud.google.com → create a new project or pick an
   existing one.
2. Enable the **Places API (New)** under APIs & Services → Library.
3. Create an API key under Credentials. Restrict it to "Places API (New)"
   and, for safety, your home's IP.
4. Put the key in `.env`:
   ```dotenv
   GOOGLE_PLACES_API_KEY=AIza...
   ```
5. Restart the worker (`Ctrl-C` then `make dev-worker`). The log line
   should now say `google_places=enabled`.
6. Verify with `make smoke-places` — it should print real restaurants near
   the default San Francisco Ferry Building coords.

The Google Maps Platform free tier is **$200/month**; at our scale
(~tens of calls/month) this stays comfortably free forever.

### Adding curated places

```bash
# Home, with 60-meter match radius:
uv run python -m home_photo_repo.places.cli add \
    --type home --name "Home" --lat 37.7749 --lng -122.4194 --radius 60

# Your office:
uv run python -m home_photo_repo.places.cli add \
    --type office --name "Work" --lat 37.78 --lng -122.40

# A friend's place:
uv run python -m home_photo_repo.places.cli add \
    --type friend_place --name "Sarah's apartment" \
    --lat 37.765 --lng -122.42 --notes "downstairs neighbor"

# A favorite restaurant (curated entry; bypasses Google Places lookup):
uv run python -m home_photo_repo.places.cli add \
    --type restaurant --name "Mimi's Trattoria" \
    --lat 37.7619 --lng -122.4341 --radius 30

# Review:
uv run python -m home_photo_repo.places.cli list

# Remove:
uv run python -m home_photo_repo.places.cli remove --id curated:<uuid>
```

### Verifying the venue pipeline

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT dish_name, venue_type, place_id, place_match_source, place_match_distance_m \
   FROM photo_analysis \
   WHERE venue_resolved_at IS NOT NULL \
   ORDER BY venue_resolved_at DESC LIMIT 10;"
```

## Project layout

```
src/home_photo_repo/
├── config.py
├── settings_factory.py
├── db.py
├── immich_client.py
├── immich_types.py
├── llm/
│   ├── factory.py
│   ├── prompts.py
│   ├── rate_limiter.py
│   ├── stage_a.py
│   ├── stage_b.py
│   └── providers/
│       ├── base.py
│       ├── anthropic_provider.py
│       └── mlx_provider.py
├── places/                  ← Plan 3
│   ├── haversine.py         # great-circle distance
│   ├── types.py             # CuratedPlace, NearbyPlace, MatchResult
│   ├── repository.py        # SQL CRUD + nearby() over places table
│   ├── google_places.py     # Google Places (New) API client
│   ├── matcher.py           # curated → google → unknown orchestrator
│   └── cli.py               # python -m home_photo_repo.places.cli ...
└── worker/
    ├── cursor.py
    ├── main.py              # also builds PlaceMatcher
    └── pipeline.py          # discovered → Stage A → Stage B → venue resolution

migrations/              # forward-only .sql files
docker/immich/           # Immich docker compose config
scripts/                 # smoke tests, one-shot tools
tests/                   # pytest suite, no network
```

## Roadmap (subsequent plans)

- **Plan 2** ✅ Done — Stage A (Haiku) + Stage B (Sonnet) with pluggable
  provider interface (Anthropic default, MLX optional).
- **Plan 3** ✅ Done — Curated personal places + Google Places fallback
  for venue resolution.
- **Plan 4** — FastAPI + HTMX + Leaflet dashboard at `localhost:8000`.
- **Plan 5** — Operations: launchd plists, nightly pg_dumpall, MLX
  setup, migration to a new Mac.
