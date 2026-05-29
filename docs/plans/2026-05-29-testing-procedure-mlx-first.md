# Testing procedure — Plans 6, 7, 8

Captured 2026-05-29. Order:
- **Plan 6** — Local MLX provider install + smoke
- **Plan 7** — Polish + venue disambiguator
- **Plan 8** — Overall test (MLX-default + Anthropic fallback + full acceptance)

**Skipped on purpose** (see `docs/plans/2026-05-29-skipped-tests-reminder.md`):
- Plan 3.2 — Google Places API key
- Plan 5 — launchd autostart + crash recovery + nightly backup

**Paths used throughout:**
- App working tree: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home`
- Runtime data root (APP_DIR): `/Users/kailiangchen/Documents/app`
- SQLite app DB: `/Users/kailiangchen/Documents/app/db/app.sqlite`
- Immich stack: `/Users/kailiangchen/Documents/immich`
- Home GPS (already seeded as `curated:Home`, radius 60 m):
  `37.3554521256761, -122.0331533193141`

---

## 0. Pre-flight (once per session)

```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home
git status -sb && git log --oneline -5

cd /Users/kailiangchen/Documents/immich && docker compose ps
# Expect: immich-server, immich-machine-learning, redis, database (all "Up")

ls /Users/kailiangchen/Documents/app/db/app.sqlite
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite "SELECT COUNT(*) FROM photo_analysis;"
```

`~/Documents/code/llm_project/home/.env` should have:
```
APP_DIR=/Users/kailiangchen/Documents/app
IMMICH_POSTGRES_DSN=postgres://...
ANTHROPIC_API_KEY=sk-ant-...
LLM_STAGE_A_PROVIDER=mlx
LLM_STAGE_B_PROVIDER=mlx
LLM_FALLBACK_PROVIDER=anthropic
MLX_BASE_URL=http://127.0.0.1:8081/v1
# GOOGLE_PLACES_API_KEY intentionally unset
```

---

## Plan 6 — Local MLX provider install + smoke

### 6.1 Install MLX runtime

```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home
make install-mlx
```
Expected: `mlx-vlm` installed; Qwen2.5-VL-7B-Instruct-4bit (~5 GB) downloaded to `~/.cache/huggingface`.

### 6.2 Smoke test

Terminal A:
```bash
make serve-mlx          # binds 127.0.0.1:8081
```
Terminal B:
```bash
make smoke-mlx
```
Expected: HTTP 200 from `/v1/chat/completions`; response describes the test image.

### 6.3 Stage A + Stage B via MLX only (strict)

```bash
LLM_FALLBACK_PROVIDER="" uv run python -m home_photo_repo.worker --once
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "SELECT is_food, dish_label, stage_a_provider, stage_b_provider, \
          stage_a_prompt_version, stage_b_prompt_version \
   FROM photo_analysis ORDER BY created_at DESC LIMIT 3;"
```
Expected: rows with `stage_a_provider=mlx`, `stage_b_provider=mlx`, non-null prompt versions.

### 6.4 Performance sanity

```bash
time uv run python -m home_photo_repo.worker --once --limit 5
```
Expected: < ~6 s per photo on M-series Mac for 7B-4bit. Note baseline.

---

## Plan 7 — Polish + venue disambiguator

### 7.1 Migration 003 indexes exist

```bash
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='photo_analysis';"
```
Expected: indexes on `(venue_resolved_at)`, `(place_id)`, `(stage_a_status)`.

### 7.2 Prompt versions persisted

Covered by 6.3 — confirm both `stage_a_prompt_version` and `stage_b_prompt_version` match `src/home_photo_repo/llm/prompts.py`.

### 7.3 Worker resilience — bad asset doesn't kill the batch

```bash
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "INSERT INTO photo_analysis (asset_id, status) VALUES ('does-not-exist', 'pending');"
uv run python -m home_photo_repo.worker --once
```
Expected: worker logs error for the bad row, continues, exits 0.

### 7.4 Review decision validation

Terminal A:
```bash
uv run uvicorn home_photo_repo.dashboard.main:app --host 127.0.0.1 --port 8000
```
Terminal B:
```bash
curl -X POST http://127.0.0.1:8000/api/review/test-id \
  -H "Content-Type: application/json" \
  -d '{"decision":"banana"}'
```
Expected: 422 with validation error (`accept|reject|edit` only).

### 7.5 Curated venue resolution (home GPS)

Import or take a photo within 60 m of `37.3554521256761, -122.0331533193141`, then:
```bash
uv run python -m home_photo_repo.worker --once
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "SELECT place_match_source, place_id, place_name FROM photo_analysis \
   ORDER BY venue_resolved_at DESC LIMIT 1;"
```
Expected: `place_match_source=curated`, `place_id=curated:Home`, `place_name=Home`.

### 7.6 Venue disambiguator — **PARTIAL (Google-dependent)**

Single curated match covered by 7.5. The 2+ Google candidate case is **SKIPPED**; re-run after Plan 3.2 key is provisioned.

---

## Plan 8 — Overall test (MLX-default + Anthropic fallback + full acceptance)

### 8.1 Unit tests for fallback

```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home
uv run pytest tests/test_fallback_provider.py tests/test_factory.py -v
```
Expected: all green.

### 8.2 Default mode, MLX up — fallback configured but unused

Terminal A:
```bash
make serve-mlx
```
Terminal B:
```bash
uv run python -m home_photo_repo.worker --once
```
Expected:
- `MLX server reachable at http://127.0.0.1:8081/v1`
- Startup dump shows provider chain `mlx→anthropic`
- Per-asset rows show `provider=mlx`

### 8.3 Default mode, MLX DOWN — fallback fires

Stop MLX (Ctrl-C in Terminal A), then:
```bash
uv run python -m home_photo_repo.worker --once
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "SELECT asset_id, stage_a_provider, stage_b_provider FROM photo_analysis \
   ORDER BY created_at DESC LIMIT 3;"
```
Expected:
- Log: `MLX server at … unreachable (…) — fallback will be used per-call`
- Per-asset warning: `primary mlx failed (transient): …; falling back to anthropic`
- Rows show `stage_a_provider=anthropic`, `stage_b_provider=anthropic`

### 8.4 Auth-error does NOT trigger retry

Temporarily set `ANTHROPIC_API_KEY=sk-ant-BROKEN` in `.env` with MLX down:
```bash
uv run python -m home_photo_repo.worker --once
```
Expected: ProviderError surfaces immediately, asset failed/skipped, no loop. Restore the real key.

### 8.5 Recovery — restart MLX

```bash
make serve-mlx
uv run python -m home_photo_repo.worker --once
```
Expected: subsequent rows return to `provider=mlx` (per-call fallback, no sticky state).

### 8.6 Full test suite

```bash
uv run pytest -q
```
Expected: 198+ tests green.

### 8.7 Dashboard end-to-end

```bash
uv run uvicorn home_photo_repo.dashboard.main:app --host 127.0.0.1 --port 8000 &
curl -s http://127.0.0.1:8000/healthz
open http://127.0.0.1:8000
```
Expected: `{"status":"ok"}`; recent classifications render with provider column visible.

---

## Skipped (reminders)

| Item | Reason | Re-test steps |
|---|---|---|
| Plan 3.2 Google Places key + fallback | No GCP key | `docs/plans/2026-05-29-skipped-tests-reminder.md` §1 |
| Plan 5 launchd autostart, crash recovery, reboot, backup | Running foreground | `docs/plans/2026-05-29-skipped-tests-reminder.md` §2 |
| Plan 7.6 disambiguator (2+ Google candidates) | Depends on Plan 3.2 | Re-run after Plan 3.2 is enabled |

---

## Troubleshooting cheatsheet

| Symptom | Likely cause | Fix |
|---|---|---|
| `MLX server at … unreachable` at every startup | `make serve-mlx` not running | Start it, or switch providers to `anthropic` |
| Fallback never fires when MLX is down | `LLM_FALLBACK_PROVIDER=""` (strict mode) | Set to `anthropic` |
| Every call goes to Anthropic with MLX up | MLX returning 5xx | Check `make serve-mlx` logs; restart |
| `place_match_source=null` on Home photos | EXIF GPS missing or radius too tight | Verify EXIF; widen curated radius |
| `sqlite3 … database is locked` | Worker + dashboard + manual query racing | Close one — WAL serializes writers |
| `psycopg.OperationalError` from worker | Immich Postgres down | `cd /Users/kailiangchen/Documents/immich && docker compose up -d` |
