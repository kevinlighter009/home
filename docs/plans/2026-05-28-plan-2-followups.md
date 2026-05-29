# Plan 2 Follow-ups (from final review)

Plan 2 shipped. Final reviewer identified items that don't block Plan 2 but
should inform Plan 3 (place matching) or be addressed as standalone cleanups.

## Important

### 1. Catch-up loop terminates on a single asset failure
`worker/main.py:109-124` — the for/else pattern means one per-asset error
breaks out of the entire `while True`, ending the cycle. Next poll retries
the failed asset (cursor wasn't advanced, good), but the rest of the current
batch waits 5 minutes. For home use this is fine; the comment "per-asset
isolation" oversells it.

**Fix shape:** either continue through siblings in the batch (skip the failed
asset for this pass), or update the comment to "first-failure terminates
cycle".

### 2. `AnthropicProvider.raw` is reconstructed JSON, not the model's bytes
`anthropic_provider.py:92-97` — the SDK gives us a parsed `tool_use.input`,
not the raw string. We `json.dumps` it back. The DB column name
`stage_b_raw_json` implies "what the model emitted" but it's actually "what
we serialized from what we parsed."

**Fix shape:** rename the column in a follow-up migration, or document in
the column comment that it's a normalized re-serialization.

## Minor

### 3. `STAGE_A_NOT_FOOD` is overloaded when Stage B provider is None
`pipeline.py:145-147` — if user only wires Stage A and the photo IS food,
returns `STAGE_A_NOT_FOOD`. Misleading. Cosmetic; no correctness impact
(DB is written correctly).

### 4. Prompt versions are defined but never persisted
`prompts.py:12-13` defines `STAGE_A_VERSION`, `STAGE_B_VERSION`, but no
schema column records them. When prompts change, results accumulate in one
column with no version filter. Worth a Plan 3 schema follow-up.

### 5. `ProviderResult.parsed: dict[str, Any]` could be tighter
Per-stage `TypedDict` would catch shape drift at the type level. Stage A/B
runtime validators already provide safety.

### 6. MLX provider's "JSON in prompt" approach is brittle
`mlx_provider.py` — if a local model emits a code fence, `json.loads` fails.
Acceptable for the "optional" MLX path. respx tests don't cover this real
failure mode.

### 7. `bootstrap` runs `uv sync` BEFORE the `.env` check
`Makefile:7-15` — on a fresh checkout `uv sync` runs to completion, then we
exit 1 on missing `.env`. Slower first-error path. Cosmetic.

### 8. Default thresholds duplicated in pipeline + Settings
`pipeline.py:59-60` defaults `stage_a_food_threshold=0.6` and
`stage_b_review_threshold=0.7`, also in `config.py`. A direct caller would
see stale defaults if spec changes only Settings. Minor coupling.

### 9. Missing `venue_resolved_at` column for Plan 3
There's no schema signal for "needs venue re-match." Plan 3 may want a
`002_add_venue_timestamps.sql` migration.

## Plan 3 readiness (positive notes)

All venue columns (`venue_type`, `place_id`, `place_match_source`,
`place_match_distance_m`) already exist in `001_initial.sql`. The pipeline
has natural seams (`pipeline.py:91` after has_gps, or `:149` after Stage B)
for plugging in place matching. `GOOGLE_PLACES_API_KEY` is already a
`SecretStr` in Settings. Stage B can grow a `nearby_places` kwarg with one
edit at the only call site.

---

## Recommendation for Plan 3

Bundle items #1 (catch-up loop semantics — at minimum doc fix), #4 (prompt
version column), and #9 (`venue_resolved_at`) into Plan 3's first hardening
task. Items #2, #3, #5–8 are at-leisure polish.
