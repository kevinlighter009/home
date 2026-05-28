# home_photo_repo — Design Spec

**Date:** 2026-05-28
**Status:** Approved (brainstorm) → ready for implementation planning
**Author:** Brainstormed collaboratively, recorded by Claude

---

## 1. Goal

A locally deployed personal service running on a single always-on Mac that:

1. Continuously ingests photos uploaded by family members' iPhones over home WiFi.
2. Reads each photo's EXIF/GPS metadata to know where it was taken.
3. Stores photos in a queryable object store, backed by an external SSD so the whole system is physically portable.
4. As the first analytical use case: detects food/dish photos and assigns each one to a specific venue — restaurants matched via GPS, but also "home", "office", and other curated personal places.
5. Uses an LLM for the food and venue analysis (Anthropic Claude by default; pluggable provider interface allows a local MLX-served model as an alternative).
6. Exposes a localhost-only web dashboard for browsing photos by restaurant / dish / map, with a review queue for low-confidence classifications.

Non-goals for v1: remote access from outside the home network; multi-user authentication on the dashboard; analytics beyond what is implicit in the browse views; mobile apps written by us.

---

## 2. Architecture overview

Three independent processes on the host Mac, all sharing one external SSD for data.

```
┌──────────────────── Host Mac ────────────────────┐
│                                                  │
│  ┌─────────────┐    REST    ┌─────────────────┐  │
│  │   Immich    │◄───────────│ home_photo_repo │  │
│  │  (Docker)   │ /api/...   │   (Python)      │  │
│  │             │            │                 │  │
│  │ Postgres ───┼──┐         │ ┌─ ingestor    │  │
│  │ library/ ───┼─┐│         │ ├─ classifier  │  │
│  └─────────────┘ ││         │ ├─ matcher     │  │
│                  ││         │ └─ dashboard   │  │
│  iOS Immich      ││         │   (FastAPI)    │  │
│  app (home WiFi) ││         │      ▲         │  │
│  ────uploads────►││         │      │ :8000   │  │
│                  ││         │      │         │  │
│                  ▼▼         │  app.sqlite ───┼──┐
│  ┌──────────────────────────┴────────────────┘  │
│  │           /Volumes/PhotoSSD/                 │
│  │   immich/library/   immich/pgdata/           │
│  │   immich/backups/   home_photo_repo/         │
│  └──────────────────────────────────────────────┘
│                                                  │
│  Browser → http://localhost:8000 (dashboard)     │
└──────────────────────────────────────────────────┘
        ▲
        │ external calls
        ▼
   Anthropic API (Haiku 4.5 + Sonnet 4.5)
   Google Places API (Nearby Search, fallback)
   (Optional) local MLX server on 127.0.0.1:8081
```

**Three processes:**

1. **Immich** — Docker compose (upstream image, unmodified). Owns photo bytes, EXIF/GPS, user accounts, thumbnails, Postgres. Source of truth for everything photo-related.
2. **`home_photo_repo` worker** — single long-running Python process managed by `launchd`. Polls Immich for new assets, runs Stage A → Stage B → place matcher, writes results to `app.sqlite`. Idempotent.
3. **`home_photo_repo` dashboard** — FastAPI + HTMX + Leaflet, same Python codebase, separate process on `127.0.0.1:8000`. Read paths over Immich + `app.sqlite`; write paths for the review queue and curated-places editor.

**Why three processes, not one:** the dashboard restarts often during development; the worker should not. Separating them means a dashboard crash never loses ingestion state.

**Data ownership:**

- Immich's Postgres = photos, EXIF, GPS, users, albums.
- `app.sqlite` = derived analysis only: classification, dish, venue/restaurant assignment, confidence, review status, curated personal places.
- External APFS-formatted SSD holds **both**, so migration = unplug + plug into a new Mac.

---

## 3. Ingestion

### 3.1 Source: Immich + iOS app

- Family members install the **Immich** app from the App Store. One-time setup: enter server URL (`http://<mac-hostname>.local:2283`) and credentials.
- The app does **background auto-upload on WiFi** with full EXIF (including GPS) preserved. No custom iOS app is built.
- The host Mac runs Immich via Docker Compose with `UPLOAD_LOCATION` and `DB_DATA_LOCATION` pointed at directories on the external SSD.
- Scope for v1: uploads happen only on home WiFi. No VPN / Tailscale / port-forwarding. If the family ever needs away-from-home upload, that is a follow-up project.

### 3.2 What Immich does per upload

Upload triggers a chain of internal jobs on Immich's BullMQ/Redis queue, run by the `immich-microservices` and `immich-machine-learning` containers:

1. **Storage** — writes the original file under `UPLOAD_LOCATION/<user>/<yyyy>/...`, computes SHA-1, inserts row in `assets`. Returns 201 to the phone immediately.
2. **Metadata extraction** — runs ExifTool, populates the `exif` table (GPS lat/lng, `DateTimeOriginal`, camera make/model, orientation, dimensions). Reverse-geocodes lat/lng to city/country using Immich's bundled offline dataset (no external API).
3. **Thumbnail generation** — preview (1440px) and thumb (250px) JPEGs.
4. **Smart-search ML** — CLIP embedding stored in Postgres via pgvector (powers Immich's own natural-language search; we do not use it).
5. **Face detection/recognition** (default-on; we do not use it).
6. **Duplicate detection** — hash + perceptual hash.

Each job completion bumps the asset's `updatedAt`. EXIF/GPS becomes queryable after step 2 completes (usually within seconds).

### 3.3 How the worker detects new photos

Polling, not push:

- **Endpoint:** `POST /api/search/metadata` with body:
  ```json
  {
    "updatedAfter": "<cursor>",
    "withExif": true,
    "order": "asc",
    "size": 100
  }
  ```
- The response includes `id`, `updatedAt`, `fileCreatedAt`, `originalFileName`, `ownerId`, and an `exifInfo` block containing `latitude`, `longitude`, `dateTimeOriginal`, etc. **One call gives both discovery and metadata.**
- **Cursor:** max `updatedAt` we have successfully processed, stored in a one-row `worker_state` table keyed by `'immich_cursor'`. Advanced per-asset after successful processing (oldest-first ordering makes mid-batch crash recovery trivial).
- **Poll interval:** default `POLL_INTERVAL_SECONDS=300` (5 minutes), env-configurable.
- **Catch-up:** if a poll returns a full batch (`size=100`), loop immediately; otherwise sleep for the interval.
- **Readiness check:** if `exifInfo.latitude` is null and the asset is less than 10 minutes old, skip it for now — Immich's EXIF job has likely not finished. Next poll will pick it up.

Real wall-clock from phone upload to processed result: `Immich ingestion (~5–30s) + ≤1 poll interval (≤5 min) + our pipeline (~3s)` ≈ under 6 minutes worst case.

Webhooks are *not* used in v1. Polling is simpler, has no public listener, and 5-minute latency is acceptable. Webhook trigger can be added later without touching the pipeline.

---

## 4. LLM analysis pipeline

### 4.1 Two-stage classification

**Stage A — "is this a food photo?"**

- Provider: Anthropic Claude **Haiku 4.5**, ~256×256 thumbnail fetched from Immich.
- Returns structured `{is_food: bool, confidence: float}`.
- Runs on every new asset.
- Cost at scale of 10,000 photos/year: **~$5/year**.

**Stage B — "what dish, at what venue?"**

- Provider: Anthropic Claude **Sonnet 4.5**, ~1024px image + GPS context + a short list of nearby candidate places.
- Returns:
  ```json
  {
    "is_food": true,
    "dish_name": "...",
    "cuisine": "...",
    "venue": {
      "type": "restaurant" | "home" | "office" | "friend_place" | "outdoor" | "unknown",
      "place_id": "...",
      "place_name": "..."
    },
    "confidence": 0.0
  }
  ```
- Runs only on assets Stage A flagged as food (~5% of intake at expected family usage).
- Cost at scale: **~$5/year**. Prompt caching on the system prompt is expected to shave ~30%.

**Thresholds (env-tunable):**

- `STAGE_A_FOOD_THRESHOLD=0.6` — below this, treat as not-food; do not call Stage B.
- `STAGE_B_CONFIDENCE_REVIEW_THRESHOLD=0.7` — below this, flag for review.
- `PLACE_MATCH_AMBIGUOUS_THRESHOLD_M=50` — if two place candidates lie within 50m of each other, flag for review.

### 4.2 Pluggable provider interface

Both stages call a single `VisionLLMProvider` Protocol, chosen per-stage from config:

```python
class VisionLLMProvider(Protocol):
    name: str
    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict,
        max_tokens: int = 512,
    ) -> ProviderResult:  # {parsed: dict, raw: str, latency_ms, input_tokens, output_tokens}
        ...
```

Two implementations ship in v1:

- `anthropic_provider.py` — default for both stages.
- `mlx_provider.py` — **placeholder/optional**. Speaks **OpenAI-compatible Chat Completions** to a locally-running **MLX** server (e.g., `mlx-vlm`'s `mlx_vlm.server` or `mlx-omni-server` on `127.0.0.1:8081`). Not wired in by default; activated by changing `LLM_STAGE_*_PROVIDER=mlx`. Same wire protocol means the provider also works against vLLM, llama.cpp's server, LM Studio, etc.

The MLX server is **launched independently** (manual or its own `launchd` plist) so model load time stays off our worker's critical path and models can be swapped without restarting the worker. `mlx-vlm` is an optional user install; the worker's hard dependency is just `httpx`.

Switching providers later requires changing only env vars; no code changes outside `llm/providers/`.

### 4.3 Venue/place matching

Order of resolution for a Stage-B food photo's GPS:

1. **Local lookup in `places`** — find any row whose haversine distance from the photo's GPS is within its `radius_m`. This single step covers both user-curated personal places (home/office/friend_place/restaurant) and previously-cached Google Places restaurants. If exactly one match: use it. If multiple matches within `PLACE_MATCH_AMBIGUOUS_THRESHOLD_M` of each other: flag for review.
2. **Google Places API (New) — Nearby Search**. Called only when step 1 returned no hit. Candidates are included in Stage B's prompt so the LLM can pick using visual context (signage, decor, dish style). The chosen match is inserted into `places` keyed `gplaces:<place_id>` so subsequent photos at the same venue resolve via step 1 with no API call.
3. If neither step yields a confident match, `venue_type = 'unknown'` and the asset goes to the review queue.

Google Maps Platform offers a **$200/month** recurring credit (Nearby Search ~$32/1000 calls). At expected volume (≤ a few dozen calls/month) the API stays comfortably free. Key is restricted in GCP Console to *Places API (New)* only and IP-restricted to the host Mac.

---

## 5. Storage & data model

### 5.1 Physical layout (external APFS-formatted SSD)

```
/Volumes/PhotoSSD/
├── immich/
│   ├── library/              ← UPLOAD_LOCATION (originals + thumbs)
│   ├── pgdata/               ← Postgres data volume
│   └── backups/              ← nightly pg_dumpall lands here
├── home_photo_repo/
│   ├── db/app.sqlite         ← derived data only
│   └── logs/                 ← (symlinked from ~/Library/Logs)
└── docker-compose.yml + .env ← Immich config travels with the data
```

SSD requirements:

- **Format: APFS** (Mac-only). Required for proper Postgres semantics (fsync, hardlinks, POSIX permissions). exFAT/NTFS/FAT32 are not supported for `pgdata`.
- **Interface: USB 3.2 Gen 2 (10 Gbps) or Thunderbolt; NVMe-class SSD.** Older USB or spinning HDDs will make Postgres painful.
- Spotlight indexing and Time Machine excluded from the SSD's `pgdata` and `library` directories.
- Hot-unplug is unsafe — always `docker compose down` first. Wrapper aliases `immich-stop` / `immich-start` shipped.

### 5.2 `app.sqlite` schema

```sql
-- One row per Immich asset we've processed (or are about to).
CREATE TABLE photo_analysis (
    immich_asset_id     TEXT PRIMARY KEY,
    first_seen_at       DATETIME NOT NULL,
    taken_at            DATETIME,
    latitude            REAL,
    longitude           REAL,
    uploader_user_id    TEXT,

    -- Stage A (Haiku) results
    stage_a_is_food     BOOLEAN,
    stage_a_confidence  REAL,
    stage_a_model       TEXT,                   -- '<provider>:<model>'
    stage_a_ran_at      DATETIME,

    -- Stage B (Sonnet) results — only populated if Stage A said food
    dish_name           TEXT,
    cuisine             TEXT,
    stage_b_confidence  REAL,
    stage_b_model       TEXT,
    stage_b_ran_at      DATETIME,
    stage_b_raw_json    TEXT,

    -- Venue resolution
    venue_type          TEXT,                   -- restaurant|home|office|friend_place|outdoor|unknown
    place_id            TEXT,                   -- FK to places.id, nullable
    place_match_source  TEXT,                   -- curated|google_places|manual|null
    place_match_distance_m  REAL,

    -- Review workflow
    review_status       TEXT NOT NULL DEFAULT 'auto',  -- auto|needs_review|confirmed|corrected
    reviewed_at         DATETIME,
    review_notes        TEXT,

    -- Soft error capture for per-asset permanent failures
    last_error          TEXT,
    error_attempts      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_photo_taken_at ON photo_analysis(taken_at);
CREATE INDEX idx_photo_place    ON photo_analysis(place_id);
CREATE INDEX idx_photo_review   ON photo_analysis(review_status);

-- Curated personal places + cached Google Places restaurants.
CREATE TABLE places (
    id              TEXT PRIMARY KEY,           -- 'curated:<uuid>' | 'gplaces:<place_id>'
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,              -- home|office|friend_place|restaurant|other
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

-- Append-only run log for /status page and debugging silent failures.
CREATE TABLE worker_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      DATETIME NOT NULL,
    finished_at     DATETIME,
    assets_seen     INTEGER DEFAULT 0,
    assets_processed INTEGER DEFAULT 0,
    errors          INTEGER DEFAULT 0,
    notes           TEXT
);

-- Single-row key/value store for cursors and similar.
CREATE TABLE worker_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Forward-only schema migration tracking.
CREATE TABLE _migrations (
    id          INTEGER PRIMARY KEY,
    applied_at  DATETIME NOT NULL,
    description TEXT NOT NULL
);
```

Design notes:

- **No photo bytes in our DB.** Reads go through Immich `/api/assets/{id}/thumbnail` and `/original`.
- **`stage_b_raw_json`** preserves the full LLM response so future re-derivation does not require re-paying.
- **`places`** unifies user-curated and Google-sourced entries so the dashboard treats them uniformly.
- **Idempotency** is guaranteed by `INSERT OR IGNORE` on `immich_asset_id` and per-stage null-checks in the pipeline.

---

## 6. Runtime behavior

### 6.1 Worker main loop

```
loop forever:
    run = begin_worker_run()
    try:
        new_assets = immich.search_metadata(updated_after=cursor, size=100, order='asc')
        for asset in new_assets:
            process_asset(asset)
            advance_cursor(asset.updated_at)
    except Exception as e:
        log_and_continue(run, e)
    finish_worker_run(run)
    if returned_full_batch:
        continue                         # catch up immediately
    sleep(POLL_INTERVAL_SECONDS)
```

Single process, single event loop, sequential per-asset processing. At expected volume (≤30 photos/day average, occasional bursts of a few hundred) parallelism is unnecessary and would only add failure modes.

### 6.2 Per-asset state machine

```
         ┌──────────────┐
         │  discovered  │  row inserted with EXIF/GPS copied from Immich response
         └──────┬───────┘
                ▼
         ┌──────────────┐
         │  stage_a_run │  Haiku → is_food + confidence
         └──────┬───────┘
                │
        ┌───────┴───────┐
        ▼ is_food=false ▼ is_food=true
   ┌─────────┐     ┌──────────────┐
   │  done   │     │ stage_b_run  │  Sonnet → dish + venue + confidence
   └─────────┘     └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │ place_match  │  curated → cached Google → live Google → unknown
                   └──────┬───────┘
                          ▼
                   ┌──────────────────────────┐
                   │ done OR needs_review     │  flagged on low confidence,
                   └──────────────────────────┘  unknown venue, or ambiguity
```

Each stage is a separate DB write. Re-entering an asset in any state resumes from the first null column — crash-safe and re-runnable for free.

### 6.3 Error handling

| Class | Examples | Response |
|---|---|---|
| **Transient** | Immich 5xx, Anthropic 429/529, network blip | Exponential backoff (2s, 8s, 30s), max 3 retries; if still failing, leave stage column null — next poll cycle retries |
| **Per-asset permanent** | Photo has no GPS; LLM returns un-parseable JSON; corrupt image | Write into `last_error`, increment `error_attempts`, set `review_status='needs_review'`, do not advance further |
| **Systemic** | Anthropic key invalid; Immich down; DB locked | Worker exits non-zero; launchd restarts after `ThrottleInterval=60`; surfaces as red banner on `/status` |

No silent failures: any asset not reaching `done` is visible in the review queue.

### 6.4 Initial backfill

First worker start detects empty `worker_state` and enters **backfill mode**: pages all existing assets oldest-first in batches of `BACKFILL_BATCH_SIZE=100`, rate-limited to `ANTHROPIC_RATE_LIMIT_PER_MINUTE=30` Stage-B calls. Resumable (cursor advances per batch). A `--backfill-since=YYYY-MM-DD` flag re-runs from any date — useful after prompt or model upgrades.

Expected backfill time for an existing 5,000-photo library: ~20 min Stage A + ~10 min Stage B = ~30 min wall-clock.

### 6.5 Scheduling (launchd)

Plist files in `launchd/`, installed by `make install-launchd`:

- **`com.homephoto.worker.plist`** — `RunAtLoad`, `KeepAlive`, `ThrottleInterval=60`, logs to `~/Library/Logs/home_photo_repo/worker.log`.
- **`com.homephoto.dashboard.plist`** — runs `uvicorn home_photo_repo.dashboard.app:app --host 127.0.0.1 --port 8000`.
- **`com.homephoto.backup.plist`** — `StartCalendarInterval` at 03:00 daily, runs `scripts/backup_postgres.sh` (logical `pg_dumpall` to `SSD/immich/backups/immich-YYYY-MM-DD.sql`, retain 14 days).
- **`com.homephoto.mlx.plist`** — optional; only installed if the user opts into MLX.

`make uninstall-launchd` reverses; `make logs` tails all log files.

### 6.6 Observability (minimal)

- Plain `logging` with JSON-lines format; one file per process under `~/Library/Logs/home_photo_repo/`. Rotation handled by macOS `newsyslog` config (one-time setup).
- Dashboard `/status` page: last 20 `worker_runs`, count of `needs_review`, last error, current cursor age. One SQL query, no metrics stack.

---

## 7. Dashboard

Read paths over Immich + `app.sqlite`; write paths only for review and curated-places editing. Bound to `127.0.0.1` only — no auth in v1. Stack: **FastAPI + Jinja2 + HTMX + Leaflet**.

### 7.1 Views (MVP scope)

1. **Map view** (`/`) — Leaflet map with pins for every food photo, clustered by place. Click → popup with dish name + thumbnail; click-through to restaurant detail.
2. **Restaurant / place detail** (`/place/{place_id}`) — name, address, all dishes eaten there (image grid + dish name + date + uploader).
3. **Feed** (`/feed`) — chronological grid of recent food photos, filterable by venue type or uploader.
4. **Review queue** (`/review`) — paginated list of assets with `review_status='needs_review'`. Inline form to confirm/correct dish name + venue. Submitting promotes to `confirmed` or `corrected` and (if a new place is selected) updates the curated `places` row.
5. **Places editor** (`/places`) — CRUD for curated places (home, office, friend_place, restaurant), each with name/lat/lng/radius/type/notes.
6. **Status** (`/status`) — worker_runs feed + cursor age + key health indicators.

### 7.2 Image delivery

`/proxy/thumbnail/{asset_id}` route streams from Immich's `/api/assets/{id}/thumbnail` with HTTP caching headers so Leaflet popups and grids do not hammer Immich repeatedly. The thumbnail proxy is the *only* binary-streaming route in the dashboard.

### 7.3 Why HTMX, not React

The dashboard's dynamic surface (review-queue submit, place editor, filter changes) is small. HTMX keeps the entire stack in Python/Jinja and removes the React build pipeline. Switching later is possible if real interactivity becomes needed.

---

## 8. Repository layout

```
home_photo_repo/
├── README.md
├── pyproject.toml              # uv-managed, Python 3.12
├── .env.example                # all keys present with placeholders + comments
├── docker/
│   └── immich/                 # docker-compose.yml + .env for Immich
│
├── src/home_photo_repo/
│   ├── config.py               # pydantic-settings, loads .env, masks secrets in repr
│   ├── db.py                   # sqlite connection + forward-only migration runner
│   ├── immich_client.py        # thin httpx wrapper for Immich REST API
│   ├── llm/
│   │   ├── providers/
│   │   │   ├── base.py             # VisionLLMProvider Protocol + ProviderResult
│   │   │   ├── anthropic_provider.py
│   │   │   └── mlx_provider.py     # OpenAI-compatible client → localhost MLX server
│   │   ├── stage_a.py
│   │   ├── stage_b.py
│   │   └── prompts.py
│   ├── places/
│   │   ├── matcher.py          # curated-first; Google Places fallback
│   │   └── google_places.py    # Nearby Search client
│   ├── worker/
│   │   ├── main.py             # entrypoint, run loop
│   │   └── pipeline.py         # per-asset state machine
│   └── dashboard/
│       ├── app.py              # FastAPI app
│       ├── routes/             # map, place, feed, review, places, status, proxy
│       ├── templates/          # Jinja2 + HTMX
│       └── static/             # Leaflet, minimal CSS
│
├── migrations/
│   └── 001_initial.sql
│
├── scripts/
│   ├── backup_postgres.sh
│   └── seed_places.py          # interactive: add home/office on first run
│
├── launchd/
│   ├── com.homephoto.worker.plist
│   ├── com.homephoto.dashboard.plist
│   ├── com.homephoto.backup.plist
│   └── com.homephoto.mlx.plist          # optional
│
└── tests/
    ├── test_pipeline.py        # fake provider + fake Immich
    ├── test_matcher.py
    ├── test_db_migrations.py
    ├── test_anthropic_provider.py       # respx-backed
    ├── test_mlx_provider.py             # respx-backed
    └── test_dashboard.py                # FastAPI TestClient
```

### Module boundaries (isolation check)

| Module | Single purpose | Depends on | Testable in isolation? |
|---|---|---|---|
| `immich_client` | HTTP calls to Immich | `httpx` | yes (respx) |
| `llm/providers/anthropic_provider` | one classify() call | `anthropic` SDK | yes (mock SDK) |
| `llm/providers/mlx_provider` | one classify() call | `httpx` | yes (respx) |
| `llm/stage_a`, `stage_b` | format prompt, call injected provider, parse | provider Protocol | yes (fake provider) |
| `places/matcher` | lat/lng → place_id | `db`, `google_places` | yes (in-memory sqlite) |
| `worker/pipeline` | orchestrate one asset through stages | all the above via DI | yes (fakes for all) |
| `dashboard/*` | read app.sqlite + Immich, render | `db`, `immich_client` | yes (TestClient) |

The worker pipeline has no knowledge of HTTP or SDK internals — it takes injected clients, which keeps tests cheap and the LLM provider swappable.

---

## 9. Testing strategy

| Layer | Tooling | What gets tested |
|---|---|---|
| **Unit** | pytest, in-memory SQLite | DB migrations; cursor advance/rollback; haversine + ambiguity math; prompt formatters; JSON-schema validators |
| **Provider contract** | pytest + respx | Each provider against recorded HTTP fixtures — handles real response shapes including 429, 529, malformed JSON |
| **Pipeline** | pytest with fake provider + fake ImmichClient | Full state machine: discovered → stage_a → stage_b → place_match → done, plus each failure branch (no GPS, low confidence, ambiguous, transient retry) |
| **Dashboard** | pytest + FastAPI TestClient | All routes render with seeded fixture; review-queue POST updates DB; HTMX partials return valid HTML fragments |
| **Smoke (manual, not CI)** | `scripts/smoke_real.py` | One-shot script against real local Immich + real Anthropic with the cheapest model, on 1 asset. Run by hand before deploying. |

- **Coverage target:** 80% on `src/home_photo_repo/`, excluding `dashboard/templates/`.
- **No network in tests:** `pytest-socket` blocks all sockets; HTTP tests use `respx` mocks.
- **TDD discipline:** matchers, prompt formatters, state-machine transitions are pure logic → tests-first. HTTP clients and FastAPI routes get tests written alongside.

---

## 10. Configuration & secrets

Three-tier loading via `pydantic-settings`:

1. `.env.example` — checked in with placeholders + inline comments.
2. `.env` — gitignored, real secrets, repo root, permission `600`.
3. Environment variables — override anything; used by launchd plists.

**Secret keys:**

```
IMMICH_API_KEY            # generated in Immich UI: Account → API Keys
ANTHROPIC_API_KEY
GOOGLE_PLACES_API_KEY     # restricted in GCP to Places API (New) + host Mac IP
```

**Tunable knobs (`.env.example` defaults):**

```
POLL_INTERVAL_SECONDS=300
BACKFILL_BATCH_SIZE=100
STAGE_A_FOOD_THRESHOLD=0.6
STAGE_B_CONFIDENCE_REVIEW_THRESHOLD=0.7
PLACE_MATCH_AMBIGUOUS_THRESHOLD_M=50
CURATED_PLACE_DEFAULT_RADIUS_M=50
GOOGLE_PLACES_SEARCH_RADIUS_M=150
ANTHROPIC_RATE_LIMIT_PER_MINUTE=30
SSD_DATA_DIR=/Volumes/PhotoSSD/home_photo_repo
DASHBOARD_BIND=127.0.0.1:8000

LLM_STAGE_A_PROVIDER=anthropic            # 'anthropic' | 'mlx'
LLM_STAGE_A_MODEL=claude-haiku-4-5
LLM_STAGE_B_PROVIDER=anthropic
LLM_STAGE_B_MODEL=claude-sonnet-4-5

MLX_BASE_URL=http://localhost:8081/v1
MLX_STAGE_A_MODEL=mlx-community/Qwen2-VL-2B-Instruct-4bit
MLX_STAGE_B_MODEL=mlx-community/Qwen2-VL-7B-Instruct-4bit
```

**Hardening:**

- `Settings.__repr__` masks secret fields so accidental log/print of the config object cannot leak keys.
- No secrets in `worker_runs` or any DB column. LLM responses go into `stage_b_raw_json`; the request body is never logged.
- Google API key is restricted in GCP Console to Places API (New) only and IP-restricted to the host Mac.

---

## 11. Developer workflow

**Bootstrap (`make bootstrap`)** — first install on a fresh machine, no existing SSD data:

1. `uv venv && uv sync`.
2. `cp .env.example .env`, prompt user to fill keys.
3. `chmod 600 .env`.
4. `mkdir -p $SSD_DATA_DIR/{db,logs}`.
5. Apply migrations (creates `app.sqlite`).
6. Run `scripts/seed_places.py` (interactive prompts for home/office GPS).

**Bootstrap-existing (`make bootstrap-existing`)** — used when migrating to a new Mac with an already-populated SSD: runs steps 1–3 only, then verifies `app.sqlite` exists on the SSD and prints any pending migrations to apply (forward-only, safe).

**Daily loop:**

```
make dev-dashboard      # uvicorn --reload, no launchd
make dev-worker         # foreground, verbose logging
make test               # pytest
make lint               # ruff + mypy
```

**Deploy:**

```
make install-launchd    # copies plists, launchctl bootstrap each
make uninstall-launchd
make logs               # tail all log files
```

**Migrations:** forward-only SQL files in `migrations/NNN_*.sql` applied by a small custom runner in `db.py`. History in the `_migrations` table. No Alembic (overkill for one SQLite DB).

---

## 12. Migration & disaster recovery

### 12.1 Move to a new Mac

1. On old Mac: `docker compose down` (clean Postgres shutdown).
2. Unplug SSD; plug into new Mac.
3. On new Mac: install Docker; copy `docker/immich/docker-compose.yml` + `.env` (or read them from the SSD if kept there); `docker compose up -d`.
4. `git clone` `home_photo_repo` on the new Mac and run `make bootstrap-existing` (variant of bootstrap that skips DB creation and `seed_places` because both already exist on the SSD; only sets up venv + `.env` + launchd-readiness).
5. In each family member's Immich app: update server URL only. Accounts and upload history are preserved (live in the restored Postgres).

Wall-clock: half a day, mostly waiting on disk I/O if you also re-rsync to internal storage. Pure unplug/plug = minutes.

### 12.2 Backups

- **Nightly `pg_dumpall`** of Immich's DB to `SSD/immich/backups/immich-YYYY-MM-DD.sql`, retained 14 days. This is the *portable* backup — survives Postgres major-version upgrades, unlike the raw `pgdata` volume.
- The SSD itself is a single point of failure. Recommended (not enforced in v1): weekly `rsync` of `SSD/immich/library/` and the latest `pg_dumpall` to a second drive or cloud (e.g., `rclone` → Backblaze B2).
- `app.sqlite` is included in the SSD; for paranoia, add it to the rsync target.

---

## 13. Cost estimate (steady state)

Assumptions: 10,000 photos/year ingested; 5% are food; family stays mostly within a curated places set.

| Item | Annual cost |
|---|---|
| Anthropic Stage A (Haiku 4.5, ~10,000 calls) | ~$5 |
| Anthropic Stage B (Sonnet 4.5, ~500 calls) | ~$5 |
| Google Places (~tens of calls/month) | $0 (under $200/mo recurring credit) |
| Hardware (external SSD amortized) | n/a (one-time) |
| **Total** | **~$10/year** |

Cost is not the driver. Convenience and accuracy dominate.

---

## 14. Open items / explicitly deferred

The following are deliberately out of scope for v1, captured so they are not forgotten:

- Webhook-driven ingestion instead of polling.
- Away-from-home upload (Tailscale or similar).
- Dashboard auth and LAN exposure.
- Analytics views (cuisines over time, top restaurants, per-uploader breakdown).
- Re-enrichment when prompts or models change beyond the manual `--backfill-since` flag.
- Local CLIP/embedding-based pre-filter for Stage A.
- Browser-friendly mobile dashboard.
- Cloud backup of the SSD as a project-managed concern.

---

## 15. Approval

Brainstorm approved by the user 2026-05-28. Next step: invoke the `writing-plans` skill to produce an implementation plan from this spec.
