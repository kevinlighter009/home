# Plan 6 — Polish & Venue Disambiguator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Burn down the accumulated follow-up backlog from Plans 1–5 and implement Plan 3 follow-up #1 (the substantive Stage-B venue disambiguator — using the LLM to pick among ambiguous Google Places candidates).

**Architecture:** Most tasks are mechanical refactors / one-line fixes. The one architecturally meaningful change is the venue disambiguator: when the matcher's Google fallback returns multiple candidates within the ambiguity threshold, a separate small LLM call (using the Stage B provider) sees the image + candidate list and picks one. This refines the matcher's geometric guess with visual context (signage, decor) per spec §4.3.

**Tech Stack:** No new dependencies. Adds `src/home_photo_repo/llm/venue_disambiguator.py`. Adds `migrations/003_*.sql`. Touches ~12 existing files for polish.

**Spec reference:** Spec §4.3 mentions Stage-B-with-candidates explicitly; the current matcher just picks nearest. This plan implements the spec-intended behavior.

**Follow-up items addressed:**
- Plan 1 #8 (SQL splitter constraint doc) — Task 11
- Plan 2 #1 (catch-up loop on per-asset failure) — Task 1
- Plan 2 #2 (`stage_b_raw_json` column comment) — Task 11
- Plan 2 #3 (`STAGE_A_NOT_FOOD` semantic overload) — Task 5
- Plan 2 #6 (MLX code-fence stripping) — Task 4
- Plan 2 #7 (Makefile bootstrap order) — Task 11
- Plan 2 #8 (default-threshold duplication) — Task 3
- Plan 3 #1 (Stage B candidate prompting) — Tasks 9 + 10 (substantial)
- Plan 3 #4 (`_record_venue_match` overwriting `review_notes`) — Task 11 (comment only)
- Plan 3 #5 (matcher swallows cache errors) — Task 6
- Plan 3 #6 (`smoke_places --strict`) — Task 6
- Plan 3 #7 + #9 (place + version indexes) — Task 2
- Plan 3 #8 (cached gplaces radius comment) — Task 11
- Plan 4 #4 (inline styles → CSS) — SKIPPED (cosmetic; current personal-use scale doesn't justify the churn)
- Plan 4 #5 (feed dropdown from constant) — Task 7
- Plan 4 #6 (feed.py f-string SQL noqa) — Task 7
- Plan 4 #7 (map.html HTML escaping) — Task 7
- Plan 4 #8 (review.py decision validation) — Task 4
- Plan 4 #9 (map.html trailing #) — Task 7
- Plan 4 #10 (DASHBOARD_BIND validator) — Task 4
- Plan 5 #1 (launchd env note in operations.md) — Task 11
- Plan 5 #2 (backup-script eval) — Task 8
- Plan 5 #3 (`make logs` empty) — SKIPPED (cosmetic)
- Plan 5 #4 (restore runbook consistency) — Task 11
- Plan 5 #5 (MLX model note) — Task 11
- Plan 5 #7 (uninstall vs install _SERVICES asymmetry) — Task 11

**Out of scope (deferred):**
- Plan 1 #7 (worker_runs.notes aggregation) — single-error capture is adequate
- Plan 1 #9 (`run_forever` integration test) — smoke scripts cover this
- Plan 2 #5 (ProviderResult TypedDict) — runtime validation suffices
- Plan 4 #4 (inline styles)
- Plan 5 #3
- HTTP Basic auth on dashboard (spec §7 defer)

**Definition of done:**
- All 169 prior tests pass + ~10 new tests for disambiguator + polish.
- `ruff`, `mypy` clean.
- Plan 3 #1 disambiguator wired through pipeline: when 2+ Google candidates fall within `PLACE_MATCH_AMBIGUOUS_THRESHOLD_M` of each other, the LLM picks; an unambiguous LLM pick clears `review_status='needs_review'`.

---

## File map

| Path | Created in task | Purpose |
|---|---|---|
| `src/home_photo_repo/worker/main.py` (modify) | 1 | Change `break` → `continue` on per-asset exception |
| `tests/test_worker_main.py` (modify) | 1 | New test: per-asset error doesn't halt remaining batch |
| `migrations/003_indexes.sql` | 2 | Indexes for `places.google_place_id` + `photo_analysis(stage_a_prompt_version, stage_a_ran_at)` |
| `tests/test_migration_003.py` | 2 | Indexes exist after migration |
| `src/home_photo_repo/config.py` (modify) | 3 | Hoist threshold defaults to module-level constants |
| `src/home_photo_repo/worker/pipeline.py` (modify) | 3 | Import + use the constants |
| `src/home_photo_repo/llm/providers/mlx_provider.py` (modify) | 4 | Strip markdown code fences from JSON before parse |
| `src/home_photo_repo/dashboard/routes/review.py` (modify) | 4 | Validate `decision ∈ {"confirm","correct"}` |
| `src/home_photo_repo/dashboard/main.py` (modify) | 4 | Validate `DASHBOARD_BIND` format |
| `tests/test_mlx_provider.py` (modify) | 4 | Test code-fence stripping |
| `tests/test_dashboard_review.py` (modify) | 4 | Test invalid decision rejected |
| `src/home_photo_repo/worker/pipeline.py` (modify) | 5 | Add `STAGE_A_DONE_NO_STAGE_B` enum member |
| `tests/test_pipeline_llm.py` (modify) | 5 | Test the new outcome |
| `src/home_photo_repo/places/matcher.py` (modify) | 6 | `log.warning` before suppress |
| `scripts/smoke_places.py` (modify) | 6 | `--strict` flag |
| `src/home_photo_repo/dashboard/routes/feed.py` (modify) | 7 | SQL branching; pass `valid_venue_types` to template |
| `src/home_photo_repo/dashboard/templates/feed.html` (modify) | 7 | Iterate over context-supplied venue types |
| `src/home_photo_repo/dashboard/templates/map.html` (modify) | 7 | Switch to safe DOM construction; remove `/place/${m.id}#` trailing `#` |
| `tests/test_dashboard_feed.py` (modify) | 7 | Test for venue dropdown options derived from constant |
| `scripts/backup_postgres.sh` (modify) | 8 | Refactor `run()` to use bash arrays / explicit commands; eliminate `eval` |
| `tests/test_backup_script.py` (modify) | 8 | Updated dry-run assertions still pass |
| `src/home_photo_repo/llm/venue_disambiguator.py` | 9 | New: `disambiguate(provider, image_bytes, candidates) -> DisambiguatedVenue` |
| `tests/test_venue_disambiguator.py` | 9 | Fake provider returns canned picks; validates parsing + clamping |
| `src/home_photo_repo/places/types.py` (modify) | 10 | Add `ambiguous_candidates: tuple[NearbyPlace, ...] = ()` to `MatchResult` |
| `src/home_photo_repo/places/matcher.py` (modify) | 10 | Populate `ambiguous_candidates` on Google-side ambiguity |
| `src/home_photo_repo/worker/pipeline.py` (modify) | 10 | After matcher: if ambiguous + disambiguator + image bytes available, refine |
| `src/home_photo_repo/worker/main.py` (modify) | 10 | Build a `Callable` disambiguator closure that uses Stage B provider |
| `tests/test_places_matcher.py` (modify) | 10 | New test: ambiguous Google result carries `ambiguous_candidates` |
| `tests/test_pipeline_disambiguation.py` | 10 | End-to-end: ambiguous → disambiguator pick → match refined |
| `Makefile` (modify) | 11 | bootstrap: check `.env` before `uv sync` |
| `docs/operations.md` (modify) | 11 | launchd env note; restore via `make uninstall-launchd`; MLX model note; uninstall vs install services asymmetry |
| `migrations/README.md` | 11 | Document SQL splitter constraint |
| Various code comments (modify) | 11 | stage_b_raw_json, gplaces radius, review_notes overwrite |
| `README.md` (modify) | 12 | Plan 6 done; clean roadmap |
| `docs/plans/2026-05-29-plan-6-followups.md` | 12 | Capture anything that came up during execution |

---

## Conventions

- Repo root: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home`.
- TDD: tests first, fail, implement, pass, commit. Per-task commit.
- `from __future__ import annotations` in new `.py`.

---

## Task 1: Worker continues past per-asset failures

Plan 2 #1: `run_once` currently `break`s the entire batch on a single per-asset exception. Switch to `continue` (advance cursor, mark error, move on); Immich-level errors still break the cycle as before.

### Step 1: Failing test — append to `tests/test_worker_main.py`

```python
def test_run_once_per_asset_failure_does_not_halt_other_assets(tmp_path: Path) -> None:
    """If process_asset raises on asset N, the worker still processes N+1, N+2..."""
    from unittest.mock import patch

    conn = _conn(tmp_path)
    assets = [_asset(f"a{i}", i + 1) for i in range(3)]
    fake = FakeImmich(batches=[assets, []])
    fixed_now = datetime(2026, 5, 28, 13, 0, 0, tzinfo=UTC)

    real_process = None
    seen_ids: list[str] = []

    def flaky_process_asset(conn_, asset_, **kw):  # noqa: ANN
        seen_ids.append(asset_.id)
        if asset_.id == "a1":
            raise RuntimeError("simulated per-asset failure")
        # Defer to real implementation for the others
        from home_photo_repo.worker.pipeline import process_asset
        return process_asset(conn_, asset_, **kw)

    with patch("home_photo_repo.worker.main.process_asset", side_effect=flaky_process_asset):
        summary = run_once(conn, fake, batch_size=10, now=fixed_now)

    # All 3 assets attempted (not just up to the failure)
    assert seen_ids == ["a0", "a1", "a2"]
    assert summary.assets_seen == 3
    assert summary.errors == 1
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_worker_main.py::test_run_once_per_asset_failure_does_not_halt_other_assets -v
```

### Step 3: Modify `src/home_photo_repo/worker/main.py`

Find the per-asset exception handler inside `run_once`:

```python
                except Exception as e:  # noqa: BLE001 - per-asset isolation
                    summary.errors += 1
                    summary.last_error = f"{asset.id}: {e!r}"
                    log.exception("pipeline failed on asset %s", asset.id)
                    # Do NOT advance the cursor past a failed asset.
                    break
```

Replace with:

```python
                except Exception as e:  # noqa: BLE001 - per-asset isolation
                    summary.errors += 1
                    summary.last_error = f"{asset.id}: {e!r}"
                    log.exception("pipeline failed on asset %s", asset.id)
                    # Advance cursor past the failed asset so the rest of
                    # the batch still gets processed. The asset's row (if
                    # inserted) carries last_error / review_status='needs_review'
                    # from the pipeline's error helpers, so the user can
                    # re-process it from the dashboard.
                    write_cursor(conn, asset.updated_at, last_id=asset.id)
                    continue
```

Find the trailing `break  # broke out of for-loop due to per-asset failure` after the for-loop's `else`. Since the inner `except` now `continue`s, the for-loop always completes its `else`. The trailing `break` is now dead code — delete it.

Result: the inner loop looks like:

```python
            for asset in assets:
                summary.assets_seen += 1
                try:
                    result = process_asset(...)
                except Exception as e:  # noqa: BLE001
                    summary.errors += 1
                    summary.last_error = f"{asset.id}: {e!r}"
                    log.exception("pipeline failed on asset %s", asset.id)
                    write_cursor(conn, asset.updated_at, last_id=asset.id)
                    continue
                if result is not ProcessResult.DEFERRED_NOT_READY:
                    summary.assets_processed += 1
                write_cursor(conn, asset.updated_at, last_id=asset.id)
            # whole batch processed (with or without per-asset failures)
            if len(assets) < batch_size:
                break
```

### Step 4: Run + commit

```bash
uv run pytest tests/test_worker_main.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/worker/main.py tests/test_worker_main.py
git commit -m "fix: worker continues past per-asset failures within a batch (Plan 2 #1)"
```

---

## Task 2: Migration 003 — indexes

Adds two indexes per Plan 3 #7 + #9.

### Step 1: Failing test — `tests/test_migration_003.py`

```python
"""Migration 003 adds indexes on places.google_place_id +
photo_analysis(stage_a_prompt_version, stage_a_ran_at)."""

from __future__ import annotations

from pathlib import Path

from home_photo_repo.db import apply_migrations, get_connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def test_migration_003_creates_indexes(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    idx_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_places_google_id" in idx_names
    assert "idx_photo_stage_a_version_ran_at" in idx_names
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_migration_003.py -v
```

### Step 3: Create `migrations/003_indexes.sql`

```sql
-- 003_indexes.sql
-- Plan 3 follow-up #7: index on places.google_place_id for fast lookups
-- when re-caching or migrating Google results.
-- Plan 3 follow-up #9: index for filtering photo_analysis rows by
-- prompt version (used by future re-classification tooling).

CREATE INDEX IF NOT EXISTS idx_places_google_id
    ON places(google_place_id);

CREATE INDEX IF NOT EXISTS idx_photo_stage_a_version_ran_at
    ON photo_analysis(stage_a_prompt_version, stage_a_ran_at);
```

### Step 4: Run + commit

```bash
uv run pytest tests/test_migration_003.py -v
uv run pytest -v

git add migrations/003_indexes.sql tests/test_migration_003.py
git commit -m "feat: migration 003 — indexes on places.google_place_id + stage_a prompt-version (Plan 3 #7/#9)"
```

---

## Task 3: Centralize default thresholds

Plan 2 #8: the defaults `0.6` (Stage A food threshold) and `0.7` (Stage B review threshold) appear in both `config.py` and `worker/pipeline.py`. Hoist to module-level constants in `config.py`.

### Step 1: Modify `src/home_photo_repo/config.py`

At the top of the file, after `from __future__ import annotations` and other imports, add constants block before the `class Settings`:

```python
# Single source of truth for pipeline thresholds. Settings and pipeline both
# read from these so defaults stay in lockstep.
DEFAULT_STAGE_A_FOOD_THRESHOLD: float = 0.6
DEFAULT_STAGE_B_REVIEW_THRESHOLD: float = 0.7
```

Update the `Settings` class to reference these (find the existing field declarations):

```python
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD
    stage_b_confidence_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD
```

Update `__all__` if present:

```python
__all__ = [
    "DEFAULT_STAGE_A_FOOD_THRESHOLD",
    "DEFAULT_STAGE_B_REVIEW_THRESHOLD",
    "Settings",
]
```

### Step 2: Modify `src/home_photo_repo/worker/pipeline.py`

Add to imports:

```python
from home_photo_repo.config import (
    DEFAULT_STAGE_A_FOOD_THRESHOLD,
    DEFAULT_STAGE_B_REVIEW_THRESHOLD,
)
```

Update `process_asset` signature defaults:

```python
def process_asset(
    conn: sqlite3.Connection,
    asset: ImmichAsset,
    *,
    now: datetime | None = None,
    immich: _ThumbnailFetcher | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
) -> ProcessResult:
```

Do the same for `run_once` in `src/home_photo_repo/worker/main.py`:

```python
def run_once(
    conn: sqlite3.Connection,
    immich: _ImmichLike,
    *,
    batch_size: int,
    now: datetime | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
) -> RunSummary:
```

Add the same import in main.py.

### Step 3: Run + commit

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/config.py src/home_photo_repo/worker/pipeline.py src/home_photo_repo/worker/main.py
git commit -m "refactor: single-source default thresholds via config constants (Plan 2 #8)"
```

---

## Task 4: MLX code-fence stripping + review decision validation + DASHBOARD_BIND validator

Three independent small fixes in one commit (each touches a different file).

### Step 1: Failing test additions

**`tests/test_mlx_provider.py`** — append:

```python
@respx.mock
def test_classify_strips_markdown_code_fences_from_json() -> None:
    """Local models sometimes wrap JSON in ```json ... ``` fences. Strip them."""
    fixture = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant",
                     "content": "```json\n{\"is_food\": true, \"confidence\": 0.9}\n```"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    result = _provider().classify(
        image_bytes=b"x", prompt="p",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    assert result.parsed == {"is_food": True, "confidence": 0.9}


@respx.mock
def test_classify_strips_plain_code_fences_too() -> None:
    """Some models use ``` without 'json' marker."""
    fixture = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant",
                     "content": "```\n{\"x\": 1}\n```"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    result = _provider().classify(
        image_bytes=b"x", prompt="p",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    assert result.parsed == {"x": 1}
```

**`tests/test_dashboard_review.py`** — append:

```python
def test_review_post_rejects_invalid_decision(client: tuple[TestClient, Path]) -> None:
    c, _ = client
    response = c.post(
        "/review/asset-needs",
        data={"dish_name": "x", "cuisine": "y", "place_id": "", "decision": "frobnicate"},
    )
    assert response.status_code == 400
```

### Step 2: Run, verify fails

```bash
uv run pytest tests/test_mlx_provider.py tests/test_dashboard_review.py -v
```

### Step 3: Modify `src/home_photo_repo/llm/providers/mlx_provider.py`

Find the `classify` method's content-parsing block (search for `content = data["choices"][0]["message"]["content"]`). Just before the `json.loads(content)` call, add a fence-stripping helper. Inside the file, add near the top after imports:

```python
def _strip_code_fences(text: str) -> str:
    """Strip leading/trailing ```json...``` or ``` fences if present."""
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence and any 'json' marker
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
    if s.endswith("```"):
        s = s[: -3].rstrip()
    return s
```

In `classify`, change:

```python
        try:
            parsed = json.loads(content)
        except ValueError as e:
            raise ProviderError(
                f"mlx model did not emit valid JSON: {content[:200]!r}"
            ) from e
```

to:

```python
        try:
            parsed = json.loads(_strip_code_fences(content))
        except ValueError as e:
            raise ProviderError(
                f"mlx model did not emit valid JSON: {content[:200]!r}"
            ) from e
```

### Step 4: Modify `src/home_photo_repo/dashboard/routes/review.py`

In `review_submit`, after the function header (before any DB work), add:

```python
    if decision not in {"confirm", "correct"}:
        raise HTTPException(
            status_code=400,
            detail=f"decision must be 'confirm' or 'correct', got {decision!r}",
        )
```

### Step 5: Modify `src/home_photo_repo/dashboard/main.py`

Find the `main()` function (or the `host`/`port` parsing section):

```python
    host, _, port_str = settings.dashboard_bind.partition(":")
    port = int(port_str) if port_str else 8000
```

Replace with:

```python
    host, sep, port_str = settings.dashboard_bind.partition(":")
    if not sep or not port_str:
        raise RuntimeError(
            f"DASHBOARD_BIND must be in the form 'host:port', got "
            f"{settings.dashboard_bind!r}. Example: '127.0.0.1:8000'."
        )
    try:
        port = int(port_str)
    except ValueError as e:
        raise RuntimeError(
            f"DASHBOARD_BIND port must be an integer, got {port_str!r}"
        ) from e
```

### Step 6: Run + commit

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/llm/providers/mlx_provider.py \
        src/home_photo_repo/dashboard/routes/review.py \
        src/home_photo_repo/dashboard/main.py \
        tests/test_mlx_provider.py tests/test_dashboard_review.py
git commit -m "fix: MLX strips JSON code fences; review validates decision; dashboard validates DASHBOARD_BIND

Plan 2 #6, Plan 4 #8, Plan 4 #10."
```

---

## Task 5: Add `STAGE_A_DONE_NO_STAGE_B` enum member

Plan 2 #3: `STAGE_A_NOT_FOOD` is returned in two semantically different cases — actually not food, AND food-but-no-stage-B-configured. Add a distinct enum member for the latter.

### Step 1: Failing test — append to `tests/test_pipeline_llm.py`

```python
def test_pipeline_returns_no_stage_b_when_food_but_b_unwired(tmp_path: Path) -> None:
    """When Stage A says food but no Stage B provider is configured, return
    STAGE_A_DONE_NO_STAGE_B (not STAGE_A_NOT_FOOD which is semantically wrong)."""
    from home_photo_repo.worker.pipeline import ProcessResult, process_asset

    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    immich = FakeImmich()

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=None,
    )

    assert result is ProcessResult.STAGE_A_DONE_NO_STAGE_B
    row = conn.execute(
        "SELECT stage_a_is_food, dish_name FROM photo_analysis"
    ).fetchone()
    assert row["stage_a_is_food"] == 1
    assert row["dish_name"] is None
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_pipeline_llm.py::test_pipeline_returns_no_stage_b_when_food_but_b_unwired -v
```

### Step 3: Modify `src/home_photo_repo/worker/pipeline.py`

Add to the `ProcessResult` enum:

```python
class ProcessResult(enum.Enum):
    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"
    DEFERRED_NOT_READY = "deferred_not_ready"
    STAGE_A_NOT_FOOD = "stage_a_not_food"
    STAGE_A_DONE_NO_STAGE_B = "stage_a_done_no_stage_b"
    STAGE_A_AND_B_DONE = "stage_a_and_b_done"
    STAGE_A_ONLY_ERROR = "stage_a_only_error"
    STAGE_B_ERROR = "stage_b_error"
```

Find the section in `process_asset` after Stage A succeeds where it currently does:

```python
    if not stage_a.is_food or stage_a.confidence < stage_a_food_threshold:
        return ProcessResult.STAGE_A_NOT_FOOD

    if stage_b_provider is None:
        # Configured Stage A only.
        return ProcessResult.STAGE_A_NOT_FOOD
```

Change the second `return` to use the new enum member:

```python
    if not stage_a.is_food or stage_a.confidence < stage_a_food_threshold:
        return ProcessResult.STAGE_A_NOT_FOOD

    if stage_b_provider is None:
        # Food per Stage A, but Stage B not configured — distinct from
        # NOT_FOOD so dashboards/queries can tell the two cases apart.
        return ProcessResult.STAGE_A_DONE_NO_STAGE_B
```

### Step 4: Run + commit

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/worker/pipeline.py tests/test_pipeline_llm.py
git commit -m "fix: add STAGE_A_DONE_NO_STAGE_B enum member (Plan 2 #3)"
```

---

## Task 6: Matcher logging + smoke_places --strict

### Step 1: Modify `src/home_photo_repo/places/matcher.py`

Find:

```python
        try:
            self._repo.insert(cached)
        except Exception:  # noqa: BLE001
            pass
```

Replace with:

```python
        try:
            self._repo.insert(cached)
        except Exception:  # noqa: BLE001
            # Cache write failure must not fail the match (likely a unique
            # constraint race between two concurrent matchers). Log and move on.
            import logging
            logging.getLogger(__name__).warning(
                "failed to cache gplaces row id=%s name=%s",
                cached.id, cached.name, exc_info=True,
            )
```

(Or hoist the `import logging` to the top of the file if not already present.)

### Step 2: Modify `scripts/smoke_places.py`

Find the argparse block:

```python
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=_DEFAULT_LAT)
    parser.add_argument("--lng", type=float, default=_DEFAULT_LNG)
    parser.add_argument("--radius", type=int, default=150)
    args = parser.parse_args()
```

Add a `--strict` flag:

```python
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=_DEFAULT_LAT)
    parser.add_argument("--lng", type=float, default=_DEFAULT_LNG)
    parser.add_argument("--radius", type=int, default=150)
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero if zero candidates are returned.")
    args = parser.parse_args()
```

At the bottom of `main()`, find:

```python
    if results:
        print("\nGoogle Places round-trip succeeded.")
        return 0
    print("\nNo results returned. (Try a denser urban area to verify the key.)")
    return 0
```

Replace with:

```python
    if results:
        print("\nGoogle Places round-trip succeeded.")
        return 0
    print("\nNo results returned. (Try a denser urban area to verify the key.)")
    return 2 if args.strict else 0
```

### Step 3: Verify smoke_places imports cleanly

```bash
uv run python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('s', 'scripts/smoke_places.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('ok')
"
```

### Step 4: Run full suite (no new tests for these tiny fixes — manual verification only)

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

### Step 5: Commit

```bash
git add src/home_photo_repo/places/matcher.py scripts/smoke_places.py
git commit -m "fix: matcher logs cache failures; smoke_places gets --strict (Plan 3 #5/#6)"
```

---

## Task 7: Dashboard template polish

Bundles Plan 4 #5 (feed dropdown), #6 (feed SQL branching), #7 (map.html escaping), #9 (map.html trailing #).

### Step 1: Modify `src/home_photo_repo/dashboard/routes/feed.py`

In the imports, add:

```python
from home_photo_repo.places.types import VALID_VENUE_TYPES
```

Find the SQL section:

```python
    where = ["stage_a_is_food = 1"]
    params: list[object] = []
    if venue_type:
        where.append("venue_type = ?")
        params.append(venue_type)
    where_sql = " AND ".join(where)
```

Replace with explicit branches (eliminates the f-string SQL noqa):

```python
    has_filter = bool(venue_type)
    params: list[object] = []
    if has_filter:
        params.append(venue_type)
```

Then replace the two `f"... WHERE {where_sql} ..."` queries with explicit branched versions:

```python
        if has_filter:
            total = conn.execute(
                "SELECT COUNT(*) FROM photo_analysis "
                "WHERE stage_a_is_food = 1 AND venue_type = ?",
                tuple(params),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT immich_asset_id, dish_name, cuisine, taken_at,
                       venue_type, place_id, review_status
                  FROM photo_analysis
                 WHERE stage_a_is_food = 1 AND venue_type = ?
              ORDER BY taken_at DESC NULLS LAST
                 LIMIT ? OFFSET ?
                """,
                (*params, _PAGE_SIZE, offset),
            ).fetchall()
        else:
            total = conn.execute(
                "SELECT COUNT(*) FROM photo_analysis WHERE stage_a_is_food = 1"
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT immich_asset_id, dish_name, cuisine, taken_at,
                       venue_type, place_id, review_status
                  FROM photo_analysis
                 WHERE stage_a_is_food = 1
              ORDER BY taken_at DESC NULLS LAST
                 LIMIT ? OFFSET ?
                """,
                (_PAGE_SIZE, offset),
            ).fetchall()
```

Remove any `# noqa: S608` directives that are no longer needed.

Add `valid_venue_types` to the template context (find the existing `TemplateResponse` call):

```python
    return cast(HTMLResponse, templates.TemplateResponse(
        request, "feed.html",
        {
            "active": "feed",
            "photos": [dict(r) for r in rows],
            "page": page,
            "total": total,
            "has_prev": page > 1,
            "has_next": page * _PAGE_SIZE < total,
            "venue_filter": venue_type or "",
            "valid_venue_types": list(VALID_VENUE_TYPES) + ["unknown"],
        },
    ))
```

### Step 2: Modify `src/home_photo_repo/dashboard/templates/feed.html`

Find the hardcoded select:

```html
    <select name="venue_type" onchange="this.form.submit()">
      <option value="" {% if not venue_filter %}selected{% endif %}>All venues</option>
      <option value="home" {% if venue_filter == 'home' %}selected{% endif %}>Home</option>
      <!-- ... etc ... -->
    </select>
```

Replace with:

```html
    <select name="venue_type" onchange="this.form.submit()">
      <option value="" {% if not venue_filter %}selected{% endif %}>All venues</option>
      {% for vt in valid_venue_types %}
        <option value="{{ vt }}" {% if venue_filter == vt %}selected{% endif %}>{{ vt }}</option>
      {% endfor %}
    </select>
```

### Step 3: Modify `src/home_photo_repo/dashboard/templates/map.html`

Find the popup HTML construction (the `marker.bindPopup` call). Replace string concatenation with safe DOM building.

Locate:

```javascript
      marker.bindPopup(`
        <strong>${m.dish}</strong>${cuisineStr}<br>
        ${placeStr}<br>
        <img src="/proxy/thumbnail/${encodeURIComponent(m.id)}" style="width: 160px; margin-top: 6px;" loading="lazy">
      `);
```

Replace with:

```javascript
      const popup = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = m.dish;            // safe — textContent does not parse HTML
      popup.appendChild(strong);
      if (m.cuisine) {
        popup.appendChild(document.createTextNode(" (" + m.cuisine + ")"));
      }
      popup.appendChild(document.createElement("br"));
      if (m.place_name) {
        popup.appendChild(document.createTextNode("at "));
        const a = document.createElement("a");
        a.href = "/place/" + encodeURIComponent(m.id);
        a.textContent = m.place_name;
        popup.appendChild(a);
      } else {
        popup.appendChild(document.createTextNode("(" + (m.venue_type || "unknown venue") + ")"));
      }
      popup.appendChild(document.createElement("br"));
      const img = document.createElement("img");
      img.src = "/proxy/thumbnail/" + encodeURIComponent(m.id);
      img.style.width = "160px";
      img.style.marginTop = "6px";
      img.loading = "lazy";
      popup.appendChild(img);
      marker.bindPopup(popup);
```

Also fix the trailing-`#` issue: the previous code had `/place/${encodeURIComponent(m.id)}#`. The new code (above) uses `"/place/" + encodeURIComponent(m.id)` with no trailing `#`. (Note: this targets the *photo asset id* in the URL, not the *place id*. Leave that semantic as the existing code had it; the only fix here is the spurious `#`.)

The `placeStr` const above the popup may now be unused — delete it if so.

### Step 4: Failing test — append to `tests/test_dashboard_feed.py`

```python
def test_feed_venue_dropdown_includes_all_valid_types(client: TestClient) -> None:
    response = client.get("/feed")
    body = response.text
    for vt in ("home", "office", "friend_place", "restaurant", "outdoor", "other"):
        # The select option appears with value="<type>"
        assert f'value="{vt}"' in body
```

### Step 5: Run + commit

```bash
uv run pytest tests/test_dashboard_feed.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/dashboard/routes/feed.py \
        src/home_photo_repo/dashboard/templates/feed.html \
        src/home_photo_repo/dashboard/templates/map.html \
        tests/test_dashboard_feed.py
git commit -m "fix: feed dropdown from VALID_VENUE_TYPES; SQL branching; map.html safe DOM (Plan 4 #5/#6/#7/#9)"
```

---

## Task 8: Refactor backup script — remove `eval`

Plan 5 #2: replace `eval` with safer constructs. The single pipe (`pg_dumpall | gzip > FILE`) can't easily be done via arrays alone; we use `bash -c` with explicit string for that one line + arrays for the others.

### Step 1: Modify `scripts/backup_postgres.sh`

Replace the entire file content with:

```bash
#!/usr/bin/env bash
# Nightly Postgres backup for Immich.
#
# Runs `pg_dumpall` inside the immich_postgres container, gzips the output,
# and stores under $BACKUP_DIR (default: $HOME/home_photo_repo_dev/immich/backups).
# Prunes dumps older than $RETENTION_DAYS (default: 14).
#
# Env:
#   BACKUP_DIR        target directory for .sql.gz files
#   RETENTION_DAYS    keep dumps newer than this many days (default 14)
#   BACKUP_DRY_RUN    if set to 1, print commands instead of running them
#   POSTGRES_USER     defaults to 'postgres'
#   CONTAINER_NAME    defaults to 'immich_postgres'

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/home_photo_repo_dev/immich/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
CONTAINER_NAME="${CONTAINER_NAME:-immich_postgres}"
DRY_RUN="${BACKUP_DRY_RUN:-0}"

TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/immich_${TIMESTAMP}.sql.gz"

# Run an array-form command, or print it in dry-run mode.
run_cmd() {
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY-RUN: $*"
    else
        "$@"
    fi
}

# Run a shell pipeline (used only where the pipe is structural — pg_dumpall | gzip).
# Inputs are operator-controlled env vars only; no user-supplied strings.
run_pipeline() {
    local cmd="$1"
    if [[ "$DRY_RUN" == "1" ]]; then
        echo "DRY-RUN: $cmd"
    else
        bash -c "$cmd"
    fi
}

# Ensure target dir exists.
run_cmd mkdir -p "$BACKUP_DIR"

# Run pg_dumpall and gzip in one stream. Pipe is the reason we need bash -c here;
# the arguments are env-var-only so this is safe.
run_pipeline "docker exec -t '$CONTAINER_NAME' pg_dumpall -U '$POSTGRES_USER' | gzip > '$OUT_FILE'"

# Rotate: delete .sql.gz files older than RETENTION_DAYS.
echo "retention: keeping dumps newer than ${RETENTION_DAYS} days in $BACKUP_DIR"
run_cmd find "$BACKUP_DIR" -maxdepth 1 -type f -name "immich_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

echo "backup complete: $OUT_FILE"
```

### Step 2: Run existing tests (no signature change to the dry-run output strings — should still pass)

```bash
uv run pytest tests/test_backup_script.py -v
```

The existing tests check for `pg_dumpall` and `RETENTION_DAYS` value in the dry-run output; both still appear. If the assertion about `BACKUP_DIR` mention fails because the path is now in quotes inside the printed string, that's fine — the path is still present substring-wise.

### Step 3: Commit

```bash
git add scripts/backup_postgres.sh
git commit -m "fix: backup script uses bash arrays + bash -c only for the structural pipe (Plan 5 #2)

eval is gone. Operator-controlled env vars still feed into the pipeline
command, but the surface for shell-injection is now confined to a single
bash -c invocation that's clearly marked as trusted-input-only."
```

---

## Task 9: Venue disambiguator module

The disambiguator: given an image and a list of candidate venues, ask the LLM to pick one. Pure function — no DB, no Immich, no Google.

### Step 1: Failing test — `tests/test_venue_disambiguator.py`

```python
"""Tests for the venue disambiguator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.venue_disambiguator import (
    DisambiguatedVenue,
    disambiguate,
)
from home_photo_repo.places.types import NearbyPlace


def _candidates() -> list[NearbyPlace]:
    return [
        NearbyPlace(
            google_place_id="gp-1", name="Mimi's", latitude=37.0, longitude=-122.0,
            address="123 A St", types=("restaurant",),
        ),
        NearbyPlace(
            google_place_id="gp-2", name="Joe's Diner", latitude=37.0001, longitude=-122.0001,
            address="456 B St", types=("restaurant",),
        ),
    ]


@dataclass
class FakeProvider:
    parsed: dict[str, Any]

    def classify(self, image_bytes: bytes, prompt: str, response_schema: dict, max_tokens: int = 512) -> ProviderResult:
        return ProviderResult(
            parsed=self.parsed, raw=str(self.parsed),
            latency_ms=10, input_tokens=10, output_tokens=10, model="fake:disambig",
        )


def test_disambiguate_returns_pick_when_confident() -> None:
    out = disambiguate(
        FakeProvider({"google_place_id": "gp-1", "confidence": 0.92}),
        image_bytes=b"img", candidates=_candidates(),
    )
    assert isinstance(out, DisambiguatedVenue)
    assert out.google_place_id == "gp-1"
    assert out.confidence == 0.92


def test_disambiguate_returns_none_pick_when_model_declines() -> None:
    """The model can return google_place_id=null meaning 'none of these'."""
    out = disambiguate(
        FakeProvider({"google_place_id": None, "confidence": 0.7}),
        image_bytes=b"img", candidates=_candidates(),
    )
    assert out.google_place_id is None


def test_disambiguate_clamps_confidence_to_unit_interval() -> None:
    out = disambiguate(
        FakeProvider({"google_place_id": "gp-1", "confidence": 1.5}),
        image_bytes=b"img", candidates=_candidates(),
    )
    assert out.confidence == 1.0


def test_disambiguate_rejects_unknown_place_id() -> None:
    """If the model returns an id not in the candidates list, raise."""
    with pytest.raises(ProviderError):
        disambiguate(
            FakeProvider({"google_place_id": "gp-bogus", "confidence": 0.9}),
            image_bytes=b"img", candidates=_candidates(),
        )


def test_disambiguate_raises_on_missing_fields() -> None:
    with pytest.raises(ProviderError):
        disambiguate(
            FakeProvider({"confidence": 0.9}),  # missing google_place_id
            image_bytes=b"img", candidates=_candidates(),
        )


def test_disambiguate_with_empty_candidates_returns_no_pick() -> None:
    out = disambiguate(
        FakeProvider({"google_place_id": None, "confidence": 0.0}),
        image_bytes=b"img", candidates=[],
    )
    assert out.google_place_id is None
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_venue_disambiguator.py -v
```

### Step 3: Create `src/home_photo_repo/llm/venue_disambiguator.py`

```python
"""Venue disambiguator: pick among ambiguous Google Places candidates by LLM.

Used when the matcher's Google Nearby Search returns multiple candidates
within the ambiguity threshold of each other. We hand the image and the
candidate list to a vision LLM; it picks one (or declines with None).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from home_photo_repo.llm.providers.base import (
    ProviderError,
    VisionLLMProvider,
)
from home_photo_repo.places.types import NearbyPlace

DISAMBIGUATE_PROMPT_VERSION: str = "disambiguator/v1"

_BASE_PROMPT = (
    "You are looking at a photograph taken near several possible venues. "
    "Based on visible context — signage, decor, plating style, menu items, "
    "wall art, language on labels — pick which of the candidates is most "
    "likely where this photo was taken. If you can't tell, return "
    "google_place_id=null.\n\n"
    "Candidates:\n"
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "google_place_id": {
            "type": ["string", "null"],
            "description": "The id of the picked candidate, or null if uncertain.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
    "required": ["google_place_id", "confidence"],
}


@dataclass(frozen=True)
class DisambiguatedVenue:
    google_place_id: str | None  # None = "none of these"
    confidence: float            # clamped to [0.0, 1.0]
    model: str
    raw_json: str


def _format_candidate(idx: int, p: NearbyPlace) -> str:
    type_str = ", ".join(p.types[:3]) if p.types else "(no types)"
    addr = f"\n   {p.address}" if p.address else ""
    return (
        f"{idx + 1}. id={p.google_place_id}  name={p.name}  types={type_str}"
        f"{addr}"
    )


def _build_prompt(candidates: list[NearbyPlace]) -> str:
    body = _BASE_PROMPT
    for i, c in enumerate(candidates):
        body += _format_candidate(i, c) + "\n"
    body += (
        "\nReturn the picked candidate's google_place_id (or null), and a "
        "confidence between 0.0 and 1.0."
    )
    return body


def disambiguate(
    provider: VisionLLMProvider,
    *,
    image_bytes: bytes,
    candidates: list[NearbyPlace],
) -> DisambiguatedVenue:
    result = provider.classify(
        image_bytes=image_bytes,
        prompt=_build_prompt(candidates),
        response_schema=_RESPONSE_SCHEMA,
        max_tokens=200,
    )
    parsed = result.parsed
    if "google_place_id" not in parsed or "confidence" not in parsed:
        raise ProviderError(
            f"disambiguator response missing required fields: {parsed!r}"
        )
    picked = parsed["google_place_id"]
    if picked is not None and not isinstance(picked, str):
        raise ProviderError(
            f"disambiguator google_place_id must be string or null: {picked!r}"
        )
    if picked is not None:
        # Reject hallucinated ids — must be one of the candidates we supplied.
        valid_ids = {c.google_place_id for c in candidates}
        if picked not in valid_ids:
            raise ProviderError(
                f"disambiguator returned unknown google_place_id {picked!r}; "
                f"candidates were {sorted(valid_ids)}"
            )
    try:
        conf = float(parsed["confidence"])
    except (TypeError, ValueError) as e:
        raise ProviderError(
            f"disambiguator confidence not numeric: {parsed['confidence']!r}"
        ) from e
    conf = max(0.0, min(1.0, conf))
    return DisambiguatedVenue(
        google_place_id=picked,
        confidence=conf,
        model=result.model,
        raw_json=result.raw,
    )


__all__ = [
    "DISAMBIGUATE_PROMPT_VERSION",
    "DisambiguatedVenue",
    "disambiguate",
]
```

### Step 4: Run + commit

```bash
uv run pytest tests/test_venue_disambiguator.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/llm/venue_disambiguator.py tests/test_venue_disambiguator.py
git commit -m "feat: venue disambiguator picks among ambiguous Google candidates via LLM (Plan 3 #1)"
```

---

## Task 10: Wire disambiguator into matcher + pipeline

Now the integration: matcher carries `ambiguous_candidates` in `MatchResult`; pipeline uses the disambiguator to refine.

### Step 1: Extend `MatchResult` in `src/home_photo_repo/places/types.py`

Find the existing `MatchResult` dataclass and add a field:

```python
@dataclass(frozen=True)
class MatchResult:
    """The outcome of `PlaceMatcher.match()`."""

    place_id: str | None
    venue_type: str
    distance_m: float | None
    source: str
    needs_review: bool
    notes: str | None = None
    # Populated only when Google fallback returned multiple candidates within
    # the ambiguity threshold. The pipeline can pass these to the venue
    # disambiguator for an LLM tiebreaker.
    ambiguous_candidates: tuple[NearbyPlace, ...] = ()
```

### Step 2: Modify `src/home_photo_repo/places/matcher.py`

In the Google-fallback branch, after `ranked = sorted(...)` and after computing `ambiguous`, find the `return MatchResult(...)`. Update:

```python
        return MatchResult(
            place_id=cached.id,
            venue_type=venue_bucket,
            distance_m=chosen_dist,
            source="google_places",
            needs_review=ambiguous,
            notes=notes,
            ambiguous_candidates=tuple(ranked) if ambiguous else (),
        )
```

### Step 3: Failing test — append to `tests/test_places_matcher.py`

```python
def test_match_carries_ambiguous_candidates_on_google_ambiguity(tmp_path: Path) -> None:
    """When Google returns multiple candidates within the ambiguity
    threshold, MatchResult.ambiguous_candidates lists them."""
    conn = _conn(tmp_path)
    a = NearbyPlace(
        google_place_id="gp-a", name="A", latitude=37.762, longitude=-122.434,
        address=None, types=("restaurant",),
    )
    b = NearbyPlace(
        google_place_id="gp-b", name="B", latitude=37.76201, longitude=-122.43401,
        address=None, types=("restaurant",),
    )
    google = FakeGoogleClient(results=[a, b])
    m = _matcher(conn, google=google, ambiguous_threshold_m=50)

    result = m.match(latitude=37.762, longitude=-122.434)

    assert result.needs_review is True
    assert len(result.ambiguous_candidates) == 2
    candidate_ids = {c.google_place_id for c in result.ambiguous_candidates}
    assert candidate_ids == {"gp-a", "gp-b"}


def test_match_returns_empty_ambiguous_candidates_when_unambiguous(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    a = NearbyPlace(
        google_place_id="gp-a", name="A", latitude=37.762, longitude=-122.434,
        address=None, types=("restaurant",),
    )
    google = FakeGoogleClient(results=[a])
    m = _matcher(conn, google=google, ambiguous_threshold_m=50)

    result = m.match(latitude=37.762, longitude=-122.434)
    assert result.ambiguous_candidates == ()
```

### Step 4: Run, verify pass (after step 2)

```bash
uv run pytest tests/test_places_matcher.py -v
```

### Step 5: Modify `src/home_photo_repo/worker/pipeline.py` — wire the disambiguator

Add to imports:

```python
from collections.abc import Callable
from home_photo_repo.llm.venue_disambiguator import (
    DisambiguatedVenue,
    disambiguate,
)
```

Define a type alias near the top after imports:

```python
DisambiguatorFn = Callable[[bytes, list["NearbyPlace"]], DisambiguatedVenue]
```

(Forward-reference `NearbyPlace` to avoid an import cycle — or import it directly with `from home_photo_repo.places.types import NearbyPlace`.)

Add a new optional parameter to `process_asset`:

```python
def process_asset(
    conn: sqlite3.Connection,
    asset: ImmichAsset,
    *,
    now: datetime | None = None,
    immich: _ThumbnailFetcher | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
    venue_disambiguator: DisambiguatorFn | None = None,
) -> ProcessResult:
```

After the existing venue-resolution block, refine if the matcher returned ambiguous + we have a disambiguator + we already have preview bytes (we fetched them earlier for Stage B):

Find:

```python
    if (
        place_matcher is not None
        and asset.latitude is not None
        and asset.longitude is not None
    ):
        match = place_matcher.match(latitude=asset.latitude, longitude=asset.longitude)
        _record_venue_match(conn, asset.id, match, current_time)
```

Replace with:

```python
    if (
        place_matcher is not None
        and asset.latitude is not None
        and asset.longitude is not None
    ):
        match = place_matcher.match(latitude=asset.latitude, longitude=asset.longitude)
        # If matcher returned ambiguous Google candidates AND we have a
        # disambiguator AND we have preview bytes (already fetched for Stage B),
        # let the LLM pick among the candidates.
        if (
            match.needs_review
            and match.ambiguous_candidates
            and venue_disambiguator is not None
            and preview_bytes is not None
        ):
            try:
                pick = venue_disambiguator(preview_bytes, list(match.ambiguous_candidates))
            except Exception:  # noqa: BLE001
                log.exception("disambiguator failed for asset %s", asset.id)
                pick = None  # fall through to original match
            if pick is not None and pick.google_place_id is not None and pick.confidence >= 0.6:
                # Promote the LLM's pick to the final match.
                match = _refine_match_from_disambiguation(match, pick)
        _record_venue_match(conn, asset.id, match, current_time)
```

Add a helper at the bottom of the file:

```python
def _refine_match_from_disambiguation(
    original: "MatchResult",
    pick: "DisambiguatedVenue",
) -> "MatchResult":
    """Replace the matcher's nearest-by-haversine pick with the LLM's
    candidate of choice. The picked place_id must be one of the candidates."""
    from home_photo_repo.places.types import MatchResult

    matching = next(
        (
            c for c in original.ambiguous_candidates
            if c.google_place_id == pick.google_place_id
        ),
        None,
    )
    if matching is None:
        # Disambiguator returned an unknown id — keep original.
        return original
    return MatchResult(
        place_id=f"gplaces:{matching.google_place_id}",
        venue_type="restaurant",
        distance_m=original.distance_m,  # keep original distance for now
        source="llm_disambiguated",
        needs_review=False,
        notes=(
            f"disambiguated from {len(original.ambiguous_candidates)} candidates "
            f"(conf={pick.confidence:.2f})"
        ),
        ambiguous_candidates=original.ambiguous_candidates,
    )
```

In the existing Stage B section, when we fetch `preview_bytes`, save it for the disambiguator to use later. Currently:

```python
        preview_bytes = immich.get_thumbnail(asset.id, size="preview")
        stage_b = run_stage_b(stage_b_provider, image_bytes=preview_bytes)
```

This already names the bytes `preview_bytes` — good. Ensure that variable is still in scope by the time venue resolution runs. If the structure is straight-line within `process_asset`, it will be. Verify by reading the function.

### Step 6: Modify `src/home_photo_repo/worker/main.py` — build the disambiguator from Stage B provider

Add to imports:

```python
from home_photo_repo.llm.venue_disambiguator import disambiguate
from home_photo_repo.places.types import NearbyPlace as _NearbyPlaceType  # noqa: F401
```

Update `run_forever` — after `stage_b_provider = build_provider("stage_b", settings)`, create a disambiguator closure that uses the Stage B provider:

```python
    def _disambiguator_fn(image_bytes: bytes, candidates: list[_NearbyPlaceType]) -> DisambiguatedVenue:
        return disambiguate(
            stage_b_provider, image_bytes=image_bytes, candidates=candidates,
        )
```

(`from home_photo_repo.llm.venue_disambiguator import DisambiguatedVenue` import needed.)

Pass `venue_disambiguator=_disambiguator_fn` to `run_once`:

Find:

```python
            summary = run_once(
                conn, immich,
                batch_size=settings.backfill_batch_size,
                stage_a_provider=stage_a_provider,
                stage_b_provider=stage_b_provider,
                rate_limiter=rate_limiter,
                stage_a_food_threshold=settings.stage_a_food_threshold,
                stage_b_review_threshold=settings.stage_b_confidence_review_threshold,
                place_matcher=place_matcher,
            )
```

Add `venue_disambiguator=_disambiguator_fn,`:

```python
            summary = run_once(
                conn, immich,
                batch_size=settings.backfill_batch_size,
                stage_a_provider=stage_a_provider,
                stage_b_provider=stage_b_provider,
                rate_limiter=rate_limiter,
                stage_a_food_threshold=settings.stage_a_food_threshold,
                stage_b_review_threshold=settings.stage_b_confidence_review_threshold,
                place_matcher=place_matcher,
                venue_disambiguator=_disambiguator_fn,
            )
```

Update `run_once` signature to accept `venue_disambiguator`:

```python
def run_once(
    conn: sqlite3.Connection,
    immich: _ImmichLike,
    *,
    batch_size: int,
    now: datetime | None = None,
    stage_a_provider: VisionLLMProvider | None = None,
    stage_b_provider: VisionLLMProvider | None = None,
    rate_limiter: TokenBucket | None = None,
    stage_a_food_threshold: float = DEFAULT_STAGE_A_FOOD_THRESHOLD,
    stage_b_review_threshold: float = DEFAULT_STAGE_B_REVIEW_THRESHOLD,
    place_matcher: PlaceMatcher | None = None,
    venue_disambiguator: Callable[[bytes, list[Any]], Any] | None = None,
) -> RunSummary:
```

And inside, pass through to `process_asset`:

```python
                result = process_asset(
                    conn,
                    asset,
                    now=current_time,
                    immich=immich,
                    stage_a_provider=stage_a_provider,
                    stage_b_provider=stage_b_provider,
                    rate_limiter=rate_limiter,
                    stage_a_food_threshold=stage_a_food_threshold,
                    stage_b_review_threshold=stage_b_review_threshold,
                    place_matcher=place_matcher,
                    venue_disambiguator=venue_disambiguator,
                )
```

### Step 7: End-to-end test — `tests/test_pipeline_disambiguation.py`

```python
"""End-to-end pipeline test for venue disambiguation."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.providers.base import ProviderResult
from home_photo_repo.llm.venue_disambiguator import DisambiguatedVenue
from home_photo_repo.places.matcher import PlaceMatcher
from home_photo_repo.places.repository import PlacesRepository
from home_photo_repo.places.types import NearbyPlace
from home_photo_repo.worker.pipeline import process_asset

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@dataclass
class FakeImmich:
    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        return b"img"


@dataclass
class FakeProvider:
    parsed: dict[str, Any]

    def classify(self, image_bytes, prompt, response_schema, max_tokens=512):
        return ProviderResult(
            parsed=self.parsed, raw=str(self.parsed),
            latency_ms=1, input_tokens=1, output_tokens=1, model="fake:x",
        )


class FakeGoogle:
    """Returns 2 candidates close together (ambiguous)."""

    def search_nearby(self, *, latitude, longitude, radius_m):
        return [
            NearbyPlace(google_place_id="gp-a", name="Cafe A",
                        latitude=37.762, longitude=-122.434, address=None,
                        types=("restaurant",)),
            NearbyPlace(google_place_id="gp-b", name="Cafe B",
                        latitude=37.7621, longitude=-122.4341, address=None,
                        types=("restaurant",)),
        ]


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset() -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id="a-1", owner_id="o", original_file_name="x.HEIC",
        updated_at=base, taken_at=base - timedelta(hours=1),
        latitude=37.762, longitude=-122.434, file_created_at=base,
    )


def test_disambiguator_refines_ambiguous_match(tmp_path: Path) -> None:
    """Pipeline runs an ambiguous Google fallback through the disambiguator,
    which picks gp-b. Result row should have place_id='gplaces:gp-b',
    review_status='auto' (no longer needs_review), and source='llm_disambiguated'."""
    conn = _conn(tmp_path)
    stage_a = FakeProvider({"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider({"dish_name": "ramen", "cuisine": "Japanese", "confidence": 0.9})
    matcher = PlaceMatcher(
        repo=PlacesRepository(conn), google=FakeGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    def disambiguator(image_bytes: bytes, candidates: list[NearbyPlace]) -> DisambiguatedVenue:
        return DisambiguatedVenue(
            google_place_id="gp-b", confidence=0.85,
            model="fake:dis", raw_json="{}",
        )

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=stage_a, stage_b_provider=stage_b,
        place_matcher=matcher, venue_disambiguator=disambiguator,
    )

    row = conn.execute(
        "SELECT place_id, place_match_source, review_status, review_notes "
        "FROM photo_analysis"
    ).fetchone()
    assert row["place_id"] == "gplaces:gp-b"
    assert row["place_match_source"] == "llm_disambiguated"
    assert row["review_status"] == "auto"
    assert "disambiguat" in (row["review_notes"] or "").lower()


def test_disambiguator_low_confidence_falls_back_to_original(tmp_path: Path) -> None:
    """If disambiguator picks but with confidence < 0.6, keep the matcher's
    nearest pick (the existing ambiguous result)."""
    conn = _conn(tmp_path)
    stage_a = FakeProvider({"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider({"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    matcher = PlaceMatcher(
        repo=PlacesRepository(conn), google=FakeGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    def disambiguator(image_bytes, candidates):
        return DisambiguatedVenue(
            google_place_id="gp-b", confidence=0.3,  # below threshold
            model="fake:dis", raw_json="{}",
        )

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=stage_a, stage_b_provider=stage_b,
        place_matcher=matcher, venue_disambiguator=disambiguator,
    )

    row = conn.execute(
        "SELECT place_match_source, review_status FROM photo_analysis"
    ).fetchone()
    # Low confidence — matcher's original Google fallback remains, with needs_review.
    assert row["place_match_source"] == "google_places"
    assert row["review_status"] == "needs_review"


def test_disambiguator_returning_none_falls_back(tmp_path: Path) -> None:
    """Disambiguator returning google_place_id=None means 'none of these' —
    keep the matcher's original pick (still needs_review)."""
    conn = _conn(tmp_path)
    stage_a = FakeProvider({"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider({"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    matcher = PlaceMatcher(
        repo=PlacesRepository(conn), google=FakeGoogle(),
        ambiguous_threshold_m=50, search_radius_m=150,
    )

    def disambiguator(image_bytes, candidates):
        return DisambiguatedVenue(
            google_place_id=None, confidence=0.5,
            model="fake:dis", raw_json="{}",
        )

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=FakeImmich(),
        stage_a_provider=stage_a, stage_b_provider=stage_b,
        place_matcher=matcher, venue_disambiguator=disambiguator,
    )

    row = conn.execute("SELECT review_status FROM photo_analysis").fetchone()
    assert row["review_status"] == "needs_review"
```

### Step 8: Run + commit

```bash
uv run pytest tests/test_pipeline_disambiguation.py tests/test_places_matcher.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/places/types.py \
        src/home_photo_repo/places/matcher.py \
        src/home_photo_repo/worker/pipeline.py \
        src/home_photo_repo/worker/main.py \
        tests/test_places_matcher.py \
        tests/test_pipeline_disambiguation.py
git commit -m "feat: wire venue disambiguator through matcher + pipeline + worker main (Plan 3 #1)

Matcher now reports ambiguous Google candidates via MatchResult.
Pipeline runs the disambiguator when 2+ candidates are within the
ambiguity threshold AND the preview image is already in hand from
Stage B. High-confidence LLM picks (>=0.6) promote the match to
source='llm_disambiguated' and clear needs_review. Lower-confidence or
'none of these' picks leave the matcher's original (needs_review)
result intact."
```

---

## Task 11: Polish bundle — Makefile + docs + comments

### Step 1: Modify `Makefile` (Plan 2 #7 — `.env` check before uv sync)

Find the `bootstrap:` target. The current order is `uv venv` → `uv sync` → `.env` check. Reorder:

```makefile
bootstrap:
	@if [ -f .env ]; then \
		if grep -qE '^(IMMICH_API_KEY|ANTHROPIC_API_KEY)=replace_me' .env; then \
			echo ""; \
			echo "ERROR: .env contains 'replace_me' placeholder secrets. Fill them in and re-run."; \
			exit 1; \
		fi; \
		chmod 600 .env; \
	else \
		cp .env.example .env; \
		chmod 600 .env; \
		echo ""; \
		echo "ERROR: Created .env from template. Edit it (IMMICH_API_KEY etc.) and re-run 'make bootstrap'."; \
		exit 1; \
	fi
	uv venv
	uv sync --all-extras
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/logs
	$(PYTHON) -m home_photo_repo.db migrate
	@echo "Bootstrap complete."
```

### Step 2: Update `docs/operations.md`

**2a.** Find the "Worker / dashboard exits with code 1 on startup" subsection in Troubleshooting. Add a new bullet:

```markdown
- **`SSD_DATA_DIR` mismatch between interactive shell and launchd.** launchd
  does NOT inherit your shell's environment — only what's in `.env` and what
  the plist's `EnvironmentVariables` block defines. If you set
  `SSD_DATA_DIR` only in `~/.zshrc`, the launchd-spawned worker silently
  falls back to `$HOME/home_photo_repo_data`. Always set it in `.env`.
```

**2b.** Find the "Restore from a backup" section. Change the top of the runbook from:

```bash
# Stop the dashboard + worker first so nothing's writing.
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootout gui/$UID/com.homephoto.dashboard
```

to:

```bash
# Stop services cleanly (preferred — single command):
make uninstall-launchd
# (If you want to keep the plists around so re-install is one make target,
# instead use:  launchctl bootout gui/$UID/com.homephoto.worker  and the same
# for dashboard. The plist files in ~/Library/LaunchAgents stay on disk.)
```

And later in that runbook (where it re-loads services):

```bash
# Re-load launchd services.
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.dashboard.plist
```

Change to:

```bash
# Re-load launchd services (re-renders plists from templates):
make install-launchd
```

**2c.** Find the MLX section. After the "Install the MLX launchd service" subsection, add:

```markdown
> **Note:** the MLX plist template hardcodes the model name
> `mlx-community/Qwen2-VL-2B-Instruct-4bit`. To switch models, edit
> `launchd/com.homephoto.mlx.plist.template`, then re-run
> `uv run python -m launchd.install_launchd mlx`.
```

### Step 3: Add comments per Plan 3 #4, #8 and Plan 5 #7

**3a.** `src/home_photo_repo/worker/pipeline.py` — find `_record_venue_match`. At the top of the `if match.needs_review:` branch, add:

```python
    # NB: this `review_notes = match.notes` may overwrite a `review_notes`
    # previously set by Stage B (low confidence). That's intentional —
    # venue ambiguity is more actionable than Stage B confidence, so we
    # surface it on the dashboard's review row. If Stage B's note matters
    # for a particular asset, the user can correct it manually.
```

**3b.** `src/home_photo_repo/places/matcher.py` — find the cached Google place construction. Just before `radius_m=self._ambiguous_threshold_m,`, add a comment:

```python
            # Use the tight ambiguity threshold as the cache row's radius —
            # a future photo within ~50m of this cached venue will resolve
            # locally. A larger radius would over-match: distinct restaurants
            # on the same block would collapse into the first one cached.
            radius_m=self._ambiguous_threshold_m,
```

**3c.** `launchd/install_launchd.py` and `launchd/uninstall_launchd.py` — note the asymmetry:

In `install_launchd.py`, find `_SERVICES` and add a comment:

```python
# The three core services. MLX is optional and installed separately if desired.
# Install side keeps this list short — installing MLX requires explicit opt-in.
_SERVICES: tuple[str, ...] = ("worker", "dashboard", "backup")
```

In `uninstall_launchd.py`, find `_SERVICES` and add:

```python
# Uninstall side includes 'mlx' even though the default install doesn't —
# `make uninstall-launchd` should clean up MLX if it was previously installed.
_SERVICES: tuple[str, ...] = ("worker", "dashboard", "backup", "mlx")
```

### Step 4: Add migration README (Plan 1 #8 doc-only)

Create `migrations/README.md`:

```markdown
# Migrations

Forward-only SQL migrations, applied in lexical filename order by
`home_photo_repo.db.apply_migrations`.

## Naming convention

`NNN_short_description.sql` — leading zero-padded number, snake_case
description.

## SQL constraint

The runner uses a naive statement splitter (`_split_sql_statements` in
`src/home_photo_repo/db.py`). It splits on `;` at the top level and does
**not** handle:

- Semicolons inside string literals (e.g., `DEFAULT 'a;b'`)
- Multi-statement triggers (`CREATE TRIGGER ... BEGIN ... END;`)
- Embedded comments containing `;`

If a future migration needs any of these, upgrade the splitter to a real
SQL parser. For all current and foreseeable migrations (simple
`CREATE TABLE` / `CREATE INDEX` / `ALTER TABLE ADD COLUMN`), the
splitter is fine.
```

### Step 5: Add column comment in migration 003 (Plan 2 #2)

Migration 003 already exists from Task 2. Edit it to add a note as a SQL comment about `stage_b_raw_json` reality vs schema name:

Append to `migrations/003_indexes.sql`:

```sql

-- Documentation note (no schema change):
-- `photo_analysis.stage_b_raw_json` is a NORMALIZED re-serialization of the
-- LLM's parsed output (via `json.dumps(parsed, sort_keys=True)`), not the
-- model's literal output bytes. The Anthropic SDK returns parsed tool-use
-- input, not a raw text payload, so there is no "original" string to record.
-- This comment serves as the canonical documentation; renaming the column
-- would force a destructive migration on existing rows.
```

### Step 6: Run + commit

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add Makefile docs/operations.md \
        src/home_photo_repo/worker/pipeline.py \
        src/home_photo_repo/places/matcher.py \
        launchd/install_launchd.py launchd/uninstall_launchd.py \
        migrations/README.md migrations/003_indexes.sql
git commit -m "chore: polish bundle — Makefile order, ops docs, comments

Plan 2 #2 #7, Plan 3 #4 #8, Plan 5 #1 #4 #5 #7, Plan 1 #8."
```

---

## Task 12: README + Plan 6 followups + final sweep

### Step 1: Final sweep

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

Expected: all green; test total ~180 (169 prior + ~10 new). If anything fails, fix before committing the README.

### Step 2: Update `README.md`

Find the existing Roadmap. Add a Plan 6 line:

```markdown
- **Plan 6** ✅ Done — Follow-up burn-down (worker per-asset isolation,
  centralized thresholds, MLX code-fence stripping, dashboard polish,
  backup script refactor, venue disambiguator).
```

Update the intro paragraph (currently mentions "Plan 5 (Operations) — and the project is feature-complete") to:

```markdown
This is **Plan 6 (Polish & Disambiguator)** — the final pass. The follow-up
backlog from Plans 1–5 has been burned down, and the spec's intended Stage B
venue disambiguation is now wired up: ambiguous Google Places matches are
refined by an LLM that sees the photo alongside the candidate list and
picks the venue with the best visual evidence.

See [`docs/operations.md`](docs/operations.md) for day-2 ops and
[`docs/SETUP.md`](docs/SETUP.md) for the fresh-Mac install walkthrough.
```

### Step 3: Create `docs/plans/2026-05-29-plan-6-followups.md` (capture anything that came up)

```markdown
# Plan 6 Follow-ups

Plan 6 closed the backlog. Items NOT addressed (and why):

## Deliberately skipped

- **Plan 1 #7** — `worker_runs.notes` only captures the last error.
  Single-error capture is adequate for a personal-scale system; a list
  table for multi-error capture is over-engineering today.
- **Plan 1 #9** — `run_forever` integration test. Smoke scripts cover
  the happy path; a real integration test would need a running Immich,
  which the test suite explicitly avoids.
- **Plan 2 #5** — `ProviderResult.parsed: dict[str, Any]` as a TypedDict.
  Runtime validators in `stage_a.py`, `stage_b.py`, and
  `venue_disambiguator.py` already catch bad shapes; a TypedDict would
  shift the check to static-time without runtime safety.
- **Plan 4 #4** — Inline `style="…"` attributes in templates. Real
  product polish — but the dashboard is single-user and the CSS surface
  is small.
- **Plan 5 #3** — `make logs` shows "no files to tail" on fresh install.
  Cosmetic; users see this once.
- **HTTP Basic auth on dashboard.** Spec §7 explicitly defers; localhost
  binding is the security model today.

## Open follow-ups from Plan 6 itself

None at time of writing — if execution surfaces anything, add it here.
```

### Step 4: Commit + push

```bash
git add README.md docs/plans/2026-05-29-plan-6-followups.md
git commit -m "docs: README + Plan 6 follow-ups — backlog burndown complete"

git push origin main
```

---

## Plan 6 acceptance checklist

- [ ] `make test` — all tests pass (~180)
- [ ] `make lint` + `make typecheck` clean
- [ ] Worker continues past per-asset failures (`test_run_once_per_asset_failure_does_not_halt_other_assets`)
- [ ] Migration 003 applies cleanly; both indexes present
- [ ] `STAGE_A_DONE_NO_STAGE_B` enum member exists and is returned in the food-but-no-stage-b case
- [ ] MLX provider strips markdown code fences before JSON parse
- [ ] `/review` returns 400 for `decision` outside `{"confirm","correct"}`
- [ ] `dashboard.main.main()` raises `RuntimeError` for malformed `DASHBOARD_BIND`
- [ ] `/feed` dropdown lists all `VALID_VENUE_TYPES`
- [ ] `map.html` uses safe DOM construction (no string concatenation with user-content)
- [ ] `smoke_places --strict` exits non-zero on zero results
- [ ] Backup script has no `eval`; single `bash -c` for the pipeline only
- [ ] Venue disambiguator module + 6 unit tests pass
- [ ] Pipeline integration: 3 disambiguation outcomes covered (refined, low-conf fallback, none-of-these fallback)
- [ ] Worker main builds a disambiguator closure from Stage B provider
- [ ] README, operations.md, migrations README all updated

Once green, the project's backlog is empty. Future work moves to feature
ideas, not follow-up cleanup.
