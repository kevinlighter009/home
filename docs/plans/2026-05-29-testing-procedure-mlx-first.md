# Testing procedure — Plans 6, 7, 8 (MLX-first order)

Captured 2026-05-29. Re-runs the post-Plan-5 acceptance suite in the order that
matches the new default: **MLX is primary, Anthropic is the auto-fallback.**

**Skipped on purpose** (see `docs/plans/2026-05-29-skipped-tests-reminder.md`):
- Plan 3.2 — Google Places API key
- Plan 5 — launchd autostart + crash recovery + nightly backup

**Paths used throughout:**
- App working tree: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home`
- Runtime data root (APP_DIR): `/Users/kailiangchen/Documents/app`
- SQLite app DB: `/Users/kailiangchen/Documents/app/db/app.sqlite`
- Immich stack (Postgres + Immich): `/Users/kailiangchen/Documents/immich`
- Home GPS (already seeded as `curated:Home`, radius 60 m):
  `37.3554521256761, -122.0331533193141`

---

## 0. Pre-flight (do once per testing session)

```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home

# Confirm clean working tree on the right branch
git status -sb
git log --oneline -5

# Ensure Immich + its Postgres are up (worker reads asset metadata from there)
cd /Users/kailiangchen/Documents/immich && docker compose ps
# Expect: immich-server, immich-machine-learning, redis, database (all "Up")

# Confirm app data dir + sqlite are in place
ls /Users/kailiangchen/Documents/app/db/app.sqlite
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite "SELECT COUNT(*) FROM photo_analysis;"
```

Make sure your `~/Documents/code/llm_project/home/.env` has:

```
APP_DIR=/Users/kailiangchen/Documents/app
IMMICH_POSTGRES_DSN=postgres://...   # the one Immich uses
ANTHROPIC_API_KEY=sk-ant-...         # needed so the fallback can actually fire
LLM_STAGE_A_PROVIDER=mlx             # default now, but verify
LLM_STAGE_B_PROVIDER=mlx             # default now, but verify
LLM_FALLBACK_PROVIDER=anthropic      # default now, but verify
MLX_BASE_URL=http://127.0.0.1:8081/v1
# GOOGLE_PLACES_API_KEY intentionally unset — see skipped-tests reminder
```

---

## 1. Plan 8 — MLX default + Anthropic fallback (test FIRST)

### 1.1 Unit tests still green

```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home
uv run pytest tests/test_fallback_provider.py tests/test_factory.py -v
```
Expected: all green (8 + ~6 tests).

### 1.2 Strict-MLX mode (fallback disabled) — happy path

In a separate terminal, start MLX:
```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home
make serve-mlx   # binds 127.0.0.1:8081
```

Then:
```bash
LLM_FALLBACK_PROVIDER="" uv run python -m home_photo_repo.worker --once
```
Expected log lines:
- `MLX server reachable at http://127.0.0.1:8081/v1`
- `provider=mlx` on Stage A / Stage B logs
- No mention of `anthropic` anywhere

### 1.3 Default mode (MLX up) — fallback configured but not used

```bash
uv run python -m home_photo_repo.worker --once
```
Expected:
- `MLX server reachable …`
- Stage A/B logs show `provider=mlx→anthropic` chain in startup config dump
- Per-asset logs still show `provider=mlx` (fallback never fires)

### 1.4 Default mode (MLX DOWN) — fallback fires

Stop MLX (`Ctrl-C` in the `make serve-mlx` terminal), then:
```bash
uv run python -m home_photo_repo.worker --once
```
Expected log lines:
- `MLX server at http://127.0.0.1:8081/v1 unreachable (...) — fallback will be used per-call`
- For each asset: warning `primary mlx failed (transient): ...; falling back to anthropic`
- Classification succeeds via Anthropic
- Row in SQLite:
  ```bash
  sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
    "SELECT asset_id, stage_a_provider, stage_b_provider FROM photo_analysis \
     ORDER BY created_at DESC LIMIT 3;"
  ```
  Expected: `stage_a_provider=anthropic`, `stage_b_provider=anthropic`

### 1.5 Auth error is NOT retried

Temporarily corrupt the key (`ANTHROPIC_API_KEY=sk-ant-BROKEN`) with MLX down,
re-run worker. Expected: ProviderError surfaces immediately, no infinite loop,
asset marked failed (or skipped). Restore the real key afterwards.

### 1.6 Restart MLX and verify recovery

Restart `make serve-mlx`, run `--once` again. Expected: subsequent assets log
`provider=mlx` again (per-call fallback means no sticky state).

---

## 2. Plan 7 — Local MLX provider install

### 2.1 Fresh install of the MLX runtime

```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home
make install-mlx
```
Expected:
- `mlx-vlm` installed in the project venv
- Qwen2.5-VL-7B-Instruct-4bit downloaded (≈5 GB) to `~/.cache/huggingface`
- No errors

### 2.2 Smoke test

```bash
make serve-mlx   # terminal A
make smoke-mlx   # terminal B
```
Expected from `smoke-mlx`:
- POST to `/v1/chat/completions` returns 200
- JSON body contains a `choices[0].message.content` that mentions food /
  describes the test image

### 2.3 Stage A + Stage B via MLX end-to-end

With MLX running and `LLM_FALLBACK_PROVIDER=""`:
```bash
uv run python -m home_photo_repo.worker --once
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "SELECT is_food, dish_label, stage_a_provider, stage_b_provider, \
          stage_a_prompt_version, stage_b_prompt_version \
   FROM photo_analysis ORDER BY created_at DESC LIMIT 3;"
```
Expected: rows with `stage_a_provider=mlx`, `stage_b_provider=mlx`, non-null
prompt versions, sensible `is_food` + `dish_label`.

### 2.4 Performance sanity

```bash
time uv run python -m home_photo_repo.worker --once --limit 5
```
Expected: < ~6 s per photo on M-series Mac for the 7B-4bit model. Note the
number; large regressions later are easier to spot.

---

## 3. Plan 6 — Polish + venue disambiguator

### 3.1 Migration 003 indexes exist

```bash
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  ".schema photo_analysis" | grep -i index
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='photo_analysis';"
```
Expected: indexes on `(venue_resolved_at)`, `(place_id)`, `(stage_a_status)`.

### 3.2 Prompt versions persisted

Already verified in 2.3 — confirm both `stage_a_prompt_version` and
`stage_b_prompt_version` are non-null and match `src/home_photo_repo/llm/prompts.py`.

### 3.3 Worker resilience — bad asset doesn't kill the batch

Insert a deliberately broken row:
```bash
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "INSERT INTO photo_analysis (asset_id, status) VALUES ('does-not-exist', 'pending');"
uv run python -m home_photo_repo.worker --once
```
Expected: worker logs an error for `does-not-exist`, continues with the rest,
exits 0. (Known doc-tightening follow-up in Plan 5 followups — for now just
confirm the batch doesn't abort mid-loop.)

### 3.4 Review decision validation

Open the dashboard:
```bash
uv run uvicorn home_photo_repo.dashboard.main:app --host 127.0.0.1 --port 8000
```
Visit `http://127.0.0.1:8000` and POST a malformed review (e.g., via curl):
```bash
curl -X POST http://127.0.0.1:8000/api/review/test-id \
  -H "Content-Type: application/json" \
  -d '{"decision":"banana"}'
```
Expected: 422 with a validation error (only `accept|reject|edit` allowed).

### 3.5 Curated venue resolution (home GPS)

Take or import a photo whose EXIF GPS is within 60 m of
`37.3554521256761, -122.0331533193141`, then:
```bash
uv run python -m home_photo_repo.worker --once
sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
  "SELECT place_match_source, place_id, place_name FROM photo_analysis \
   ORDER BY venue_resolved_at DESC LIMIT 1;"
```
Expected: `place_match_source=curated`, `place_id=curated:Home`,
`place_name=Home`.

### 3.6 Venue disambiguator — **PARTIAL (Google-dependent)**

The local-only branch of the disambiguator (single curated match) is covered by
3.5. The 2+ Google candidate case is **SKIPPED** — re-run after the Plan 3.2
Google Places API key is set up. See `docs/plans/2026-05-29-skipped-tests-reminder.md`.

---

## 4. End-to-end acceptance

With MLX running, fallback configured, Immich Postgres up:

```bash
cd /Users/kailiang-mac-deeproute/Documents/code/llm_project/home
uv run pytest -q                       # full suite, should be 198+ green
uv run python -m home_photo_repo.worker --once
uv run uvicorn home_photo_repo.dashboard.main:app --host 127.0.0.1 --port 8000 &
curl -s http://127.0.0.1:8000/healthz  # {"status":"ok"}
open http://127.0.0.1:8000             # eyeball recent rows
```

Pass criteria:
- All tests green
- Worker completes a full pass with MLX as primary
- Dashboard renders recent classifications with provider=mlx
- Kill MLX, re-run worker, see provider switch to anthropic mid-stream,
  no errors surfaced to the dashboard

---

## 5. Skipped (reminders)

| Item | Reason | Where to find re-test steps |
|---|---|---|
| Plan 3.2 Google Places key + fallback | No GCP key yet | `docs/plans/2026-05-29-skipped-tests-reminder.md` §1 |
| Plan 5 launchd autostart, crash recovery, reboot survival, nightly backup | User runs services in foreground for now | `docs/plans/2026-05-29-skipped-tests-reminder.md` §2 |
| Plan 6.6 disambiguator (2+ Google candidates) | Depends on Plan 3.2 | Re-run once Plan 3.2 is enabled |

---

## 6. Troubleshooting cheatsheet

| Symptom | Likely cause | Fix |
|---|---|---|
| `MLX server at … unreachable` at every startup | `make serve-mlx` not running | Start it, or set `LLM_STAGE_*_PROVIDER=anthropic` |
| Fallback never fires when MLX is down | `LLM_FALLBACK_PROVIDER=""` (strict mode) | Unset or set to `anthropic` |
| Every call goes to Anthropic even with MLX up | MLX returning 5xx — check `make serve-mlx` logs | Restart MLX; inspect model load |
| `place_match_source=null` on Home photos | EXIF GPS missing or radius too tight | Verify EXIF, widen curated radius if needed |
| `sqlite3 … database is locked` | Worker + dashboard + manual query racing | Close one; SQLite is WAL but writers serialize |
| `psycopg.OperationalError` from worker | Immich Postgres container down | `cd /Users/kailiangchen/Documents/immich && docker compose up -d` |
