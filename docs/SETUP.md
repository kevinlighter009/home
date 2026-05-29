# Complete Setup Guide — fresh Mac to working end-to-end

This guide takes a brand-new Mac from zero to a working `home_photo_repo`
deployment: Immich running locally, the worker classifying photos with
Claude, and family iPhones uploading on home WiFi.

**Estimated total time:** 60–90 minutes on first run (most of it waiting
for Docker image downloads). Subsequent installs on different Macs: 15–30
min once you know the steps.

---

## Table of contents

0. [What you're building](#0-what-youre-building)
1. [System prerequisites](#1-system-prerequisites)
2. [Clone the repo](#2-clone-the-repo)
3. [Install Python dependencies](#3-install-python-dependencies)
4. [Run Immich (Docker)](#4-run-immich-docker)
5. [Configure Immich via web UI](#5-configure-immich-via-web-ui)
6. [Configure home_photo_repo](#6-configure-home_photo_repo)
7. [Initialize the database](#7-initialize-the-database)
8. [Verify Immich connection](#8-verify-immich-connection)
9. [Test the LLM pipeline](#9-test-the-llm-pipeline)
10. [Start the worker](#10-start-the-worker)
11. [Set up the iPhone Immich app](#11-set-up-the-iphone-immich-app)
12. [End-to-end verification](#12-end-to-end-verification)
13. [Production: move to external SSD](#13-production-move-to-external-ssd)
14. [Daily operations](#14-daily-operations)
15. [Troubleshooting](#15-troubleshooting)

---

## 0. What you're building

Three independent processes on the host Mac, sharing one local data
directory (or an external SSD for production):

```
┌──────────────────── Host Mac ────────────────────┐
│                                                  │
│  Immich (Docker)  ◄──REST──  home_photo_repo     │
│    Postgres                  (Python worker)     │
│    library/                                      │
│       ▲                          │               │
│       │                          ▼               │
│  iOS Immich app          app.sqlite (derived)    │
│  (home WiFi)                                     │
│                                                  │
└──────────────────────────────────────────────────┘
                                  │
                                  ▼ external calls
                        Anthropic API (Claude)
```

- **Immich** owns photos, EXIF/GPS, user accounts (Docker)
- **Worker** polls Immich every 5 min, runs Stage A (is-food, Haiku) and
  Stage B (dish + cuisine, Sonnet) on new photos
- **iPhone app** auto-uploads on home WiFi

---

## 1. System prerequisites

### 1.1 macOS Command Line Tools (provides `make`, `git`, `clang`)

```bash
xcode-select --install
```

Click through the GUI dialog. Wait for it to finish (5–10 min). Verify:
```bash
xcode-select -p     # should print a path
git --version       # should print version
make --version      # should print version
```

### 1.2 Homebrew (recommended package manager)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

When done, **follow the post-install instructions it prints** — usually
two `echo` lines to add Homebrew to your PATH in `~/.zprofile`.

Verify:
```bash
brew --version
```

### 1.3 Docker Desktop

Download from https://www.docker.com/products/docker-desktop/ → install
the `.dmg` → launch Docker Desktop → wait for the whale icon in the menu
bar to settle (no animation = ready).

Verify:
```bash
docker --version
docker compose version
docker ps                # should print empty table, no error
```

### 1.4 Python 3.12

Check what you have:
```bash
python3 --version
```

If it's `3.12.x` or newer, you're done. If not:
```bash
brew install python@3.12
python3.12 --version
```

### 1.5 `uv` (recommended Python dep manager — fastest, also works for conda/pip below)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

The installer prints two lines to add to your shell config — follow them,
then restart your terminal (or `source ~/.zprofile`).

Verify:
```bash
uv --version
```

---

## 2. Clone the repo

```bash
mkdir -p ~/Documents/code/llm_project
cd ~/Documents/code/llm_project
git clone git@github.com:kevinlighter009/home.git
cd home
```

If `git@github.com` SSH isn't set up on this Mac, use HTTPS instead:
```bash
git clone https://github.com/kevinlighter009/home.git
```

(For SSH on a new Mac: `ssh-keygen -t ed25519 -C "your@email"`, then add
`~/.ssh/id_ed25519.pub` to GitHub → Settings → SSH and GPG keys.)

---

## 3. Install Python dependencies

Pick **one** of the three paths. **uv is recommended.**

### Path A: uv (recommended)

```bash
uv sync --all-extras
```
This creates `.venv/` and installs everything in ~10 seconds.

### Path B: conda

```bash
conda create -n home_photo_repo python=3.12 -y
conda activate home_photo_repo
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

### Path C: plain venv + pip

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

### Sanity check

For all three paths:
```bash
# uv path:
uv run pytest -v
# conda/venv path (env must be activated):
pytest -v
```

Expected: **90 tests passed in ~1 s.**

If you see import errors, your venv isn't installed correctly — re-run
the install step.

---

## 4. Run Immich (Docker)

### 4.1 Pick a data directory

For the first test, **use a local path** — switch to an external SSD only
after the full pipeline works (covered in §13).

```bash
export HPR_BASE=$HOME/home_photo_repo_dev
mkdir -p $HPR_BASE/immich/{library,pgdata,backups}
mkdir -p $HPR_BASE/app/{db,logs}
```

(`$HPR_BASE` is just a convenience for this guide — not used by the
project.)

### 4.2 Configure Immich's compose

```bash
cp docker/immich/.env.example docker/immich/.env
```

Edit `docker/immich/.env`:
```dotenv
UPLOAD_LOCATION=/Users/<your-username>/home_photo_repo_dev/immich/library
DB_DATA_LOCATION=/Users/<your-username>/home_photo_repo_dev/immich/pgdata
DB_PASSWORD=<paste output of: openssl rand -hex 32>
DB_USERNAME=postgres
DB_DATABASE_NAME=immich
IMMICH_VERSION=release
TZ=America/Los_Angeles      # or your timezone
```

**Get your username:** `whoami`

**Generate the password:** `openssl rand -hex 32`

### 4.3 Start Immich

```bash
cd docker/immich
docker compose up -d
```

First run downloads ~3–5 GB of Docker images. Watch progress:
```bash
docker compose logs -f immich-server
```
You'll see lots of startup log. **Wait for the line:**
```
Immich Server is listening on http://[::]:2283
```
Press **Ctrl-C** to stop following logs (containers keep running).

Return to repo root:
```bash
cd ../..
```

### 4.4 Verify Immich is up

```bash
curl -s http://localhost:2283/api/server/ping
```
Expected: `{"res":"pong"}`

If you don't get pong:
```bash
docker compose -f docker/immich/docker-compose.yml ps
# All 4 services should say "running" or "healthy"
```

---

## 5. Configure Immich via web UI

### 5.1 Create the admin account

Open http://localhost:2283 in a browser.

- Click **"Getting started"** → enter your email and a password → **Sign Up**.
- Skip through the onboarding wizard with defaults.

### 5.2 Generate an API key for `home_photo_repo`

- Top-right avatar → **Account Settings** → **API Keys** → **New API Key**
- Name: `home_photo_repo`
- Permissions: leave all checked (or minimum: `asset.read`, `search.read`)
- **Copy the key now** — you cannot see it again after closing the dialog.

### 5.3 (Optional) Create per-family-member accounts

Skip for now if you're just testing yourself. To add family members:

- **Administration** (gear icon, top-right) → **Users** → **Add User**
- Enter their email, name, password. They'll use this on their iPhone.

---

## 6. Configure home_photo_repo

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` — set at minimum:

```dotenv
IMMICH_BASE_URL=http://localhost:2283
IMMICH_API_KEY=<paste from §5.2>

ANTHROPIC_API_KEY=sk-ant-<your real Anthropic key>

SSD_DATA_DIR=/Users/<your-username>/home_photo_repo_dev/app
```

**Where to get an Anthropic API key:** https://console.anthropic.com →
Settings → API Keys → Create Key. Add credit to the account if needed
(this project costs ~$10/year at typical usage).

Leave `GOOGLE_PLACES_API_KEY=replace_me` — Plan 1 + Plan 2 don't use it
(Plan 3 will).

For now, also leave the LLM provider and threshold settings at defaults.

---

## 7. Initialize the database

### uv path:
```bash
make bootstrap
```

`make bootstrap` does:
1. Verifies `.env` exists and doesn't have placeholder secrets (will
   `exit 1` if either fails)
2. Re-installs deps via `uv sync --all-extras`
3. Creates the `db/` and `logs/` directories under `$SSD_DATA_DIR`
4. Applies database migrations to create `app.sqlite`

Expected last line: `Bootstrap complete.`

### conda/venv path:
```bash
mkdir -p $SSD_DATA_DIR/{db,logs}
python -m home_photo_repo.db migrate
```

### Verify the DB
```bash
ls $SSD_DATA_DIR/db/                        # should show app.sqlite
sqlite3 $SSD_DATA_DIR/db/app.sqlite ".tables"
```
Expected output:
```
_migrations  photo_analysis  places  worker_runs  worker_state
```

---

## 8. Verify Immich connection

```bash
# uv:
make smoke-immich
# conda/venv:
python scripts/smoke_immich.py
```

Expected:
```
Connected to http://localhost:2283/; got 0 most recent assets:
```

Zero is fine — Immich is empty. If you see `401` or a connection error,
re-check `IMMICH_API_KEY` and `IMMICH_BASE_URL` in `.env` (no trailing
whitespace).

---

## 9. Test the LLM pipeline

```bash
# uv:
make smoke-llm
# conda/venv:
python scripts/smoke_llm.py
```

Expected:
```
Using provider: anthropic (model=claude-haiku-4-5)
Stage A result on synthetic image:
  is_food   = False
  confidence= 0.05
  model     = anthropic:claude-haiku-4-5
  latency   = 800ms
  raw       = {"confidence": 0.05, "is_food": false}

Provider round-trip succeeded.
```

The synthetic image is a 16×16 magenta square — not food, so `is_food=False`
with low confidence is correct. What matters: the round-trip works.

If you see `ERROR: ANTHROPIC_API_KEY not set`, your `.env` still has the
placeholder. If you see a 401 from Anthropic, the key is wrong or the
account has no credit.

---

## 10. Start the worker

```bash
# uv:
make dev-worker
# conda/venv:
python -m home_photo_repo.worker.main
```

Expected first log lines:
```
2026-05-28 ... INFO worker starting: poll_interval=300s batch_size=100 db=... stage_a=anthropic stage_b=anthropic
2026-05-28 ... INFO run complete: seen=0 processed=0 errors=0
```

The worker polls every 5 min (default). Leave it running. **Open a second
terminal** for the rest of this guide.

If you want faster iteration during testing, Ctrl-C the worker, edit
`.env` to set `POLL_INTERVAL_SECONDS=30`, then restart `make dev-worker`.

---

## 11. Set up the iPhone Immich app

### 11.1 Find your Mac's LAN IP

On the Mac:
```bash
ipconfig getifaddr en0
# If empty, try: ipconfig getifaddr en1
```
Note the IP, e.g., `192.168.1.42`.

### 11.2 Verify the iPhone can reach the Mac

On the iPhone (on the **same WiFi** as the Mac, not cellular), open Safari:
```
http://192.168.1.42:2283
```

You should see the Immich login page. If it times out:
- iPhone on guest WiFi? Move to the main network.
- macOS firewall blocking? **System Settings → Network → Firewall → Options** → allow Docker.
- Router "AP/client isolation" enabled? Disable in router admin.

### 11.3 Install the iOS app

1. App Store → search **"Immich"** → install
2. Open app → **Server Endpoint URL** → `http://192.168.1.42:2283`
3. Sign in with the admin account email/password from §5.1 (or a
   per-user account from §5.3)
4. Grant permissions:
   - **Photos: Access all photos** ← required
   - **Background App Refresh** ← required for auto-upload
   - **Notifications** ← optional

### 11.4 Enable background WiFi-only backup

1. Profile/avatar icon (bottom-right) → **Backup**
2. Toggle **on**: Foreground backup AND Background backup
3. **Backup options**: turn **Use cellular data = OFF**
4. (Optional) **Albums** → pick which to back up; default "Recents"
   (full camera roll) is fine for testing
5. Tap **Start backup**

The first run uploads your entire camera roll — can take minutes to hours
depending on size. Subsequent runs only upload new photos.

### 11.5 Confirm uploads arriving on the Mac

```bash
make smoke-immich
```
Should now list real iPhone-originated photos with GPS coordinates.

You can also watch http://localhost:2283 on the Mac — the timeline
populates as photos upload.

---

## 12. End-to-end verification

With the worker running (`make dev-worker` from §10) and the iPhone app
backing up (§11.4):

### 12.1 Take a new food photo on the iPhone

Snap a photo of a meal (or open any food photo via the Photos app — but
a new shot is best because it has fresh metadata).

Wait ~30 seconds — the Immich app should push it. Watch the worker
terminal — within one poll interval you should see:

```
run complete: seen=1 processed=1 errors=0
```

### 12.2 Inspect the result

In your second terminal:

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT immich_asset_id, latitude, longitude, stage_a_is_food, \
          stage_a_confidence, dish_name, cuisine, review_status \
   FROM photo_analysis ORDER BY first_seen_at DESC LIMIT 1;"
```

For a food photo you should see something like:
```
asset-uuid-xxx|37.7749|-122.4194|1|0.95|margherita pizza|Italian|auto
```

- `stage_a_is_food=1` and `stage_a_confidence > 0.6` means Stage A
  flagged it as food
- `dish_name` and `cuisine` are populated by Stage B
- `review_status=auto` means Stage B was confident; `needs_review` would
  mean confidence dropped below 0.7

### 12.3 Test the non-food path

Take a photo of something non-food (your dog, a building). Wait for the
next poll. The row should have `stage_a_is_food=0` and `dish_name=NULL`
— Stage B didn't run, saving an API call.

### 12.4 Test crash safety

In the worker terminal, **Ctrl-C** the worker. Then re-run `make dev-worker`.
The first cycle should report `seen=0 processed=0`. Confirm no duplicate
rows:

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT COUNT(*), COUNT(DISTINCT immich_asset_id) FROM photo_analysis;"
```
Both numbers should match exactly.

### 12.5 Check the run log

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT id, started_at, finished_at, assets_seen, assets_processed, errors \
   FROM worker_runs ORDER BY id DESC LIMIT 5;"
```

You should see one row per poll cycle. `errors` should be 0.

### 12.6 Check the cursor

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite "SELECT * FROM worker_state;"
```
Should show `immich_cursor` with a JSON value containing the latest
`updated_at` + `last_id`.

---

## 13. Production: move to external SSD

Once everything works on the local-path setup, migrate to an external SSD
so the whole system is physically portable.

### 13.1 Format the SSD as APFS

Plug in the SSD → Disk Utility → select the drive → **Erase** → Format:
**APFS** → Name: e.g. `PhotoSSD`.

> APFS is required for Postgres (it needs proper POSIX semantics).
> exFAT/NTFS will not work for the `pgdata` directory.

### 13.2 Stop Immich

```bash
cd docker/immich && docker compose down && cd ../..
```

### 13.3 Move data to the SSD

```bash
mkdir -p /Volumes/PhotoSSD/immich/{library,pgdata,backups}
mkdir -p /Volumes/PhotoSSD/home_photo_repo/{db,logs}

# Copy Immich data:
rsync -aP $HOME/home_photo_repo_dev/immich/library/ /Volumes/PhotoSSD/immich/library/
rsync -aP $HOME/home_photo_repo_dev/immich/pgdata/  /Volumes/PhotoSSD/immich/pgdata/

# Copy your derived data:
cp $HOME/home_photo_repo_dev/app/db/app.sqlite /Volumes/PhotoSSD/home_photo_repo/db/
```

### 13.4 Update env files to point at the SSD

In `docker/immich/.env`:
```dotenv
UPLOAD_LOCATION=/Volumes/PhotoSSD/immich/library
DB_DATA_LOCATION=/Volumes/PhotoSSD/immich/pgdata
```

In `.env`:
```dotenv
SSD_DATA_DIR=/Volumes/PhotoSSD/home_photo_repo
```

### 13.5 Exclude SSD from Spotlight and Time Machine

```bash
sudo mdutil -i off /Volumes/PhotoSSD
```

System Settings → General → Time Machine → Options → **+** → add
`/Volumes/PhotoSSD` to the exclude list.

### 13.6 Bring everything back up

```bash
cd docker/immich && docker compose up -d && cd ../..
make dev-worker
```

Re-run §12 verification queries against the SSD-located DB to confirm
nothing broke.

### 13.7 Always unplug cleanly

**Before unplugging the SSD:**
```bash
cd docker/immich && docker compose down && cd ../..
```
Then unplug. Yanking the SSD while Postgres is running risks data
corruption.

---

## 14. Daily operations

### Start everything (after a reboot, for example)

```bash
cd ~/Documents/code/llm_project/home/docker/immich && docker compose up -d && cd ../..
make dev-worker      # foreground — for production you'd use launchd (Plan 5)
```

### Stop everything cleanly

In the worker terminal: **Ctrl-C**

```bash
cd ~/Documents/code/llm_project/home/docker/immich && docker compose down
```

### Update home_photo_repo to the latest code

```bash
cd ~/Documents/code/llm_project/home
git pull
make bootstrap       # re-installs deps + runs any new migrations
```

### Manual Postgres backup (recommended weekly)

```bash
docker exec -t immich_postgres pg_dumpall -U postgres > \
  /Volumes/PhotoSSD/immich/backups/immich-$(date +%Y-%m-%d).sql
```

(Plan 5 will automate this via launchd.)

### Reset everything (DESTRUCTIVE — for re-testing only)

```bash
cd docker/immich && docker compose down -v && cd ../..
rm -rf $SSD_DATA_DIR/db/app.sqlite
rm -rf $HOME/home_photo_repo_dev          # or /Volumes/PhotoSSD/immich
docker volume prune -f
# Then re-do §4–§7
```

---

## 15. Troubleshooting

### Tests

| Symptom | Fix |
|---|---|
| `pytest: command not found` | Activate the venv (`source .venv/bin/activate` for conda/venv path) or use `uv run pytest` |
| `ModuleNotFoundError: home_photo_repo` | conda/venv path: re-run `pip install -e .` from repo root |
| Tests pass locally but `make test` fails | `uv` not on PATH — restart terminal or `source ~/.zprofile` |

### Docker / Immich

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Start Docker Desktop, wait for whale icon to settle |
| `port is already allocated` on 2283 | Another Immich is running; `docker ps -a` → stop the conflicting container |
| Immich UI returns 502 | `docker compose logs immich-server` → look for postgres connect errors → check `DB_PASSWORD` in `.env` matches what's in `pgdata/` |
| `make smoke-immich` says 401 | Wrong/expired `IMMICH_API_KEY`. Regenerate in Immich UI → Account → API Keys |
| All Immich containers show `unhealthy` | `docker compose down && docker compose up -d` and wait 60s |

### LLM / Anthropic

| Symptom | Fix |
|---|---|
| `make smoke-llm` says `ANTHROPIC_API_KEY not set` | Edit `.env` — replace `replace_me` with real key |
| Anthropic 401 | Wrong key or account has no credit. Check https://console.anthropic.com |
| Anthropic 429 / 529 | Rate-limited or overloaded — worker retries automatically on next cycle |
| `ProviderError: anthropic returned no tool_use block` | Model declined to classify (rare). Photo will be retried next cycle |

### Worker

| Symptom | Fix |
|---|---|
| Worker starts but `seen=0` forever despite uploads | Cursor is past the latest asset. Check with `sqlite3 $SSD_DATA_DIR/db/app.sqlite "SELECT * FROM worker_state;"` — delete the row to reset: `sqlite3 ... "DELETE FROM worker_state WHERE key='immich_cursor';"` |
| `errors > 0` in worker_runs | Check `last_error` per asset: `sqlite3 ... "SELECT immich_asset_id, last_error FROM photo_analysis WHERE last_error IS NOT NULL;"` |
| Worker crashes immediately on startup | Check `.env` values; check that `app.sqlite` exists (`make bootstrap` if not); check Immich is reachable |
| `no_gps` errors on iPhone uploads | iOS stripped location. On iPhone: **Settings → Privacy & Security → Location Services → Camera = "While Using"** — affects only new photos |

### iPhone app

| Symptom | Fix |
|---|---|
| "Server unreachable" | First test in Safari on the iPhone — if Safari can't reach `http://<mac-ip>:2283`, neither can the app. Check WiFi, firewall, router AP-isolation |
| Mac's IP changed and app stops working | Reserve a static DHCP lease in your router for the Mac, or set static IP in macOS Network settings |
| Background uploads don't run when phone is locked | iOS limits this; expect a 6–24 h batch lag. For real-time, ask family to open the app once a day |
| Photos upload but no GPS | See `no_gps` row above |

---

## (Plan 3 only) Add curated places + Google Places key

### A. Add your curated places

```bash
uv run python -m home_photo_repo.places.cli add \
    --type home --name "Home" --lat <YOUR-LAT> --lng <YOUR-LNG>

uv run python -m home_photo_repo.places.cli add \
    --type office --name "Work" --lat <LAT> --lng <LNG>

# Add as many friend_place / restaurant entries as you like.
uv run python -m home_photo_repo.places.cli list
```

Finding your home's lat/lng: take a photo of your kitchen with your iPhone
(make sure Camera has Location Services on), upload via Immich, then check:

```bash
sqlite3 $SSD_DATA_DIR/db/app.sqlite \
  "SELECT latitude, longitude FROM photo_analysis ORDER BY first_seen_at DESC LIMIT 1;"
```

### B. (Optional) Enable Google Places fallback

1. Google Cloud Console → enable "Places API (New)"
2. Create an API key, restrict to Places API (New)
3. `.env` → `GOOGLE_PLACES_API_KEY=AIza...`
4. `make smoke-places` should print real venues near the default coords.

### C. Restart the worker

```bash
make dev-worker
```

Log line will show `google_places=enabled` (or `disabled (curated only)`).

## (Plan 4 only) Start the dashboard

In a second terminal (leave the worker running in the first):

```bash
cd ~/Documents/code/home
make dev-dashboard
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Open http://127.0.0.1:8000 in a browser:

- The map should show pins for every food photo with GPS.
- /feed lists recent food photos.
- /places lets you add home/office.
- /review queues low-confidence rows.
- /status shows pipeline counts and recent worker runs.

To leave running long-term: open the URL once a day, or wait for Plan 5
(launchd plists) to auto-start it at login.

## Verification checklist — All plans complete

- [ ] `make test` → 90 passed
- [ ] `make smoke-immich` lists assets with GPS
- [ ] `make smoke-llm` prints Stage A round-trip
- [ ] `make dev-worker` runs without errors
- [ ] Photo taken on iPhone appears in `photo_analysis` within ~10 min
- [ ] Food photo has populated `dish_name` + `cuisine`
- [ ] Non-food photo has `stage_a_is_food=0` and `dish_name=NULL`
- [ ] Worker restart doesn't duplicate rows
- [ ] `uv run python -m home_photo_repo.places.cli list` shows your curated places
- [ ] (If Google enabled) `make smoke-places` returns real venues
- [ ] Food photo at a curated location populates `venue_type` correctly (home/office/etc.)
- [ ] Food photo at an unknown location either matches via Google Places or shows `venue_type='unknown'`
- [ ] `make dev-dashboard` starts uvicorn on 127.0.0.1:8000
- [ ] `make smoke-dashboard` prints `OK: http://127.0.0.1:8000/healthz → {'status': 'ok'}`
- [ ] Map (`/`) shows pins for food photos
- [ ] Review queue (`/review`) lets you confirm a needs_review item
- [ ] Places editor (`/places`) shows curated places + can add/delete
- [ ] `make install-launchd` succeeds; `launchctl list | grep com.homephoto` shows 3 services
- [ ] `make logs` tails active worker + dashboard logs
- [ ] `make backup-now` produces a `.sql.gz` under `$BACKUP_DIR`
- [ ] After a reboot, the dashboard is reachable at http://127.0.0.1:8000 without manual start

When all check, you're production-ready for Plans 1 + 2. Future plans:

- **Plan 3** — Place matching (curated personal places + Google Places fallback)
- **Plan 4** — FastAPI + HTMX + Leaflet dashboard at `localhost:8000`
- **Plan 5** — launchd plists, nightly `pg_dumpall`, MLX setup, migration to new Mac

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
