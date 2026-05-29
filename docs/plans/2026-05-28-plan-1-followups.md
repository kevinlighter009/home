# Plan 1 Follow-ups (from final review)

Plan 1 shipped successfully. The final code reviewer identified items that don't block Plan 1 but should be addressed in Plan 2 (or as standalone cleanups).

## Important — address in Plan 2

### 1. Tied-timestamp pagination in `run_once`

`worker/main.py:61-95` uses `updatedAfter=cursor` with strict comparison. If N assets share the exact same `updated_at` (rare but possible: bulk import / migration), the loop can re-fetch the same batch indefinitely. The pipeline's idempotency prevents duplicate rows, but `assets_seen` inflates and catch-up termination is wrong.

Plan 2 adds slow per-asset LLM work that will amplify any pagination bug. Fix before adding LLM calls.

**Fix shape:** paginate by `(updated_at, id)` tuple instead of `updated_at` alone. Cursor becomes a composite key.

### 2. Bootstrap with placeholder secrets is misleading

`make bootstrap` on a fresh checkout copies `.env.example` → `.env`, prints a "fill in keys" line, then *still* runs migrations and exits 0. Looks fully successful. A user could miss the message and only discover the issue at `make smoke-immich`.

**Fix shape:** when `.env` is freshly created, exit non-zero after the message (or skip migrations and require a second `make bootstrap` after the user fills the keys).

### 3. `make dev-worker` is not a guarded `bootstrap`-then-run

`make dev-worker` runs the worker directly; if `.env` is missing or `app.sqlite` doesn't exist, the failure is at runtime rather than at make-target validation. Consider making `dev-worker` depend on `bootstrap` (or a smaller `ensure-db` target).

## Minor — address at leisure

### 4. `smoke_immich.py` says "5 most recently updated" but returns oldest 5

`scripts/smoke_immich.py:23` uses `order="asc"` with a 30-day `updated_after` window. Returns oldest matching, not newest. Either:
- Change to `order="desc"` to actually return newest, or
- Drop the docstring claim and say "5 assets from the last 30 days".

### 5. `Settings()  # type: ignore[call-arg]` repeated 3x

`db.py:109`, `smoke_immich.py:16`, `main.py:166` all carry the same comment. Centralize behind a `load_settings() -> Settings` factory to keep the ignore in one place.

### 6. `types-requests` stale dev dependency

`pyproject.toml` lists `types-requests` but the project uses `httpx`, not `requests`. Drop.

### 7. `worker_runs.notes` only captures the last error

If multiple per-asset failures happen in one run, only the last is recorded in `notes`. Acceptable for Plan 1 telemetry; revisit if error volume grows. Plan 2's LLM failures will exercise this path more.

### 8. `_split_sql_statements` is documented-fragile

`db.py:33-56` doesn't handle `;` inside string literals or compound statements (triggers). Plan 2/3 migrations must respect that constraint or the splitter needs upgrading.

### 9. `run_forever` has no integration-style test

Marked `# pragma: no cover`. The KeyboardInterrupt + cleanup path is worth one test with a fake `time.sleep` and a single iteration. Optional.

### 10. ~~README references `docker/immich/.env.example`~~ — INVALID

Verified: `docker/immich/.env.example` is present in the repo and tracked by git. The reviewer used plain `ls` which hides dotfiles; this issue is invalid.

---

## Doing the work

These belong in Plan 2 as a "pre-LLM cleanup" block of tasks, or as a small standalone Plan 1.5 commit. Recommend: bundle items 1–3 into Plan 2's first task (foundation hardening before adding LLM pipeline); leave 4–10 for whenever convenient.
