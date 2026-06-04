# home_photo_repo

Local home-photo ingestion + analysis service. Sits on top of a self-hosted
[Immich](https://immich.app/) instance and (in later plans) adds food/dish
recognition and venue tagging (restaurant via GPS / home / office / etc.),
plus a localhost dashboard.

This is **Plan 6 (Polish & Disambiguator)** — the final pass. The follow-up
backlog from Plans 1–5 has been burned down, and the spec's intended Stage B
venue disambiguation is now wired up: ambiguous Google Places matches are
refined by an LLM that sees the photo alongside the candidate list and
picks the venue with the best visual evidence.

See [`docs/operations.md`](docs/operations.md) for day-2 ops and
[`docs/SETUP.md`](docs/SETUP.md) for the fresh-Mac install walkthrough.

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

## LLM provider options

The default configuration uses **MLX (local) as primary with Anthropic
(API) as automatic fallback**. If the MLX server is up and reachable,
classification is fully local at zero per-call cost. If MLX is down or
not yet installed, individual classification calls transparently fall
back to Anthropic — no manual intervention, no data loss.

### Quick paths

**Local-first (recommended, default):** Install MLX and you're done.

```bash
make install-mlx        # mlx-vlm + launchd service
```

Set `ANTHROPIC_API_KEY` in `.env` even if you only want local — it's the
fallback when MLX is briefly unreachable. ~$0/yr at typical usage if MLX
is always up.

**Anthropic-only:** Don't install MLX. Edit `.env`:

```dotenv
LLM_STAGE_A_PROVIDER=anthropic
LLM_STAGE_B_PROVIDER=anthropic
LLM_FALLBACK_PROVIDER=
```

~$10/yr at typical family use.

**MLX-only (strict, no fallback):** Install MLX. Edit `.env`:

```dotenv
LLM_FALLBACK_PROVIDER=
```

If MLX is down, classification errors and the asset goes to `needs_review`.

### Verifying

- `make smoke-llm` — verifies `ANTHROPIC_API_KEY` round-trip
- `make smoke-mlx` — verifies local MLX server
- Worker startup log shows the active chain, e.g.
  `stage_a=mlx→anthropic stage_b=mlx→anthropic`

See [`docs/operations.md` § Provider option B](docs/operations.md#provider-option-b-local-mlx-apple-silicon)
for model choices, multi-port setups, troubleshooting.

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

## Dashboard

A read-mostly web UI for browsing what the worker has classified.

### Run it

In a separate terminal from the worker:

```bash
make dev-dashboard
```

Open http://127.0.0.1:8000. The dashboard binds to localhost only — to
expose it on the LAN, add HTTP Basic auth first (out of scope here).

### Pages

- **/** — Leaflet map. Pins for every food photo with GPS, popup shows
  dish + thumbnail + venue link.
- **/place/{id}** — Every dish recorded at this venue, with thumbnails.
- **/feed** — Chronological grid of food photos. Filter by venue type;
  paginated.
- **/review** — Photos the worker flagged as low-confidence or ambiguous.
  Inline form to confirm / correct dish + cuisine + venue (HTMX, no page
  reload).
- **/places** — CRUD for curated places (home / office / etc.). Cached
  Google Places rows are listed but read-only.
- **/status** — Last 20 worker runs + pipeline counts (total, classified,
  food, with-venue, needs-review).

### Verify it's running

```bash
make smoke-dashboard      # hits /healthz, prints OK
```

## Running on a new Mac (first-time setup)

Everything — code, database, and MLX model weights — lives on the external SSD at
`/Volumes/PhotoSSD/`. Plug it in, then run **two commands** on the new machine.

### Step 1 — Install Homebrew (only prerequisite)

Homebrew is the only thing that can't be auto-installed. Check first:

```bash
brew --version   # if this works, skip the install below
```

If missing:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Step 2 — Run bootstrap (installs everything else automatically)

```bash
cd /Volumes/PhotoSSD/repo
make bootstrap-existing
```

This single command automatically:
1. **uv** — Python package manager (`brew install uv`)
2. **Docker Desktop** — installs via brew cask + waits for daemon to start
3. **nginx** — installs, configures reverse proxy, starts on port 80 (sudo required)
4. **Bonjour hostname** — sets `home-food.local` via `sudo scutil` (sudo required)
5. **Tailscale** — installs + checks connection; prompts `tailscale login` if needed
6. **Python deps** — `uv venv && uv sync --all-extras`
7. **DB migrations** — applies any pending schema changes

> **Note on sudo steps:** nginx and the Bonjour hostname require `sudo`. If running
> non-interactively the script prints the manual commands to run once in a terminal.

### Step 3 — Connect Tailscale (remote access only)

If Tailscale wasn't already logged in, run:
```bash
tailscale login          # opens browser; log in with your Tailscale account
make configure-tailscale # updates .env and prints your access URLs
```

### Every time you restart

Open **four terminals**, all from `/Volumes/PhotoSSD/repo`:

```bash
# Terminal 1 — Immich (photo library backend)
cd docker/immich && docker compose up -d

# Terminal 2 — MLX vision model server (runs on Apple Silicon)
make start-mlx

# Terminal 3 — Worker (classifies photos + resolves venues)
make dev-worker

# Terminal 4 — Dashboard
make dev-dashboard
```

**Access the dashboard:**

| Network | URL |
|---------|-----|
| Home WiFi (no Tailscale needed) | http://home-food.local |
| Away from home (Tailscale required) | http://\<device\>.tail-xyz.ts.net |

```bash
# Optional — live processing progress monitor
make monitor
```

### Shut everything down

```bash
# Worker / dashboard / MLX: Ctrl-C in their terminals

# Immich:
cd /Volumes/PhotoSSD/repo/docker/immich && docker compose down
```

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

## Project layout

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

```
src/home_photo_repo/
├── config.py
├── settings_factory.py
├── db.py
├── immich_client.py
├── immich_types.py
├── llm/
│   └── … (unchanged)
├── places/
│   └── … (unchanged)
├── dashboard/                ← Plan 4
│   ├── app.py                # FastAPI factory
│   ├── deps.py               # request-scoped DB / Immich
│   ├── main.py               # uvicorn entrypoint
│   ├── routes/
│   │   ├── proxy.py          # /proxy/thumbnail/{id}
│   │   ├── map_view.py       # /
│   │   ├── place.py          # /place/{id}
│   │   ├── feed.py           # /feed
│   │   ├── review.py         # /review
│   │   ├── places_editor.py  # /places
│   │   └── status.py         # /status
│   ├── templates/            # Jinja2 + HTMX
│   └── static/               # vendored Leaflet + HTMX + CSS
└── worker/
    └── … (unchanged)
```

## Roadmap (subsequent plans)

- **Plan 2** ✅ Done — Stage A (Haiku) + Stage B (Sonnet) with pluggable
  provider interface (Anthropic default, MLX optional).
- **Plan 3** ✅ Done — Curated personal places + Google Places fallback
  for venue resolution.
- **Plan 4** ✅ Done — FastAPI + HTMX + Leaflet dashboard at
  `localhost:8000`.
- **Plan 5** ✅ Done — launchd plists (auto-start at login), nightly
  `pg_dumpall` backup, `bootstrap-existing` for new-Mac migration,
  optional MLX server.
- **Plan 6** ✅ Done — Follow-up burn-down (worker per-asset isolation,
  centralized thresholds, MLX code-fence stripping, dashboard polish,
  backup script refactor, venue disambiguator).
- **Plan 7** ✅ Done — Local MLX vision pipeline as a first-class
  alternative to the Anthropic API. One-command install
  (`make install-mlx`), default model `Qwen2.5-VL-7B-Instruct-4bit`.
- **Plan 8** ✅ Done — MLX-default with Anthropic auto-fallback.
  Local-first classification when MLX is reachable; transparent fallback
  per-call when not.
