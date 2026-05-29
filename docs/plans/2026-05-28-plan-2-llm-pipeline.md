# Plan 2 — LLM Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Plan 1 ingestion worker with two-stage LLM classification: every new asset gets a fast "is this food?" check (Stage A, Claude Haiku 4.5), and food photos get a richer "what dish?" classification (Stage B, Claude Sonnet 4.5). Results land in `photo_analysis`. A pluggable `VisionLLMProvider` interface allows swapping in a local MLX-served model as an alternative.

**Architecture:** A single `VisionLLMProvider` Protocol (`classify(image_bytes, prompt, response_schema) -> ProviderResult`) implemented twice: `AnthropicProvider` (real Claude SDK) and `MLXProvider` (OpenAI-compatible HTTP to a local MLX server). Two pure functions (`run_stage_a`, `run_stage_b`) format prompts, call providers, parse JSON responses, return typed results. The pipeline's per-asset state machine extends to run Stage A after the discovered insert, then Stage B only if Stage A flagged food. A token-bucket rate limiter shared between the two stages enforces `ANTHROPIC_RATE_LIMIT_PER_MINUTE`. All HTTP is mocked in tests via `respx`; the Anthropic SDK is dependency-injected so its constructor is mockable.

**Tech Stack:** Adds `anthropic>=0.40` (Claude SDK). MLX provider uses existing `httpx`. New module tree under `src/home_photo_repo/llm/`. No new infrastructure.

**Spec reference:** `docs/specs/2026-05-28-home-photo-repo-design.md`, sections 4 (LLM analysis pipeline), 4.1 (two-stage), 4.2 (pluggable provider), 5.2 (DB columns: `stage_a_*`, `stage_b_*`, `dish_name`, `cuisine`), 6.2 (per-asset state machine), 6.3 (error classes), 10 (thresholds, rate limit).

**Plan 1 follow-ups bundled in:** `docs/plans/2026-05-28-plan-1-followups.md` items 1 (composite cursor), 2 (bootstrap UX), 3 (Makefile dev-worker dependency), 4 (smoke script order), 5 (Settings factory), 6 (drop types-requests). Items 7-9 deferred.

**Out of scope (Plan 3/4/5):**
- Place / venue resolution (Plan 3 fills `venue_type`, `place_id`)
- Curated places + Google Places matching (Plan 3)
- Dashboard (Plan 4)
- launchd plists, real MLX server install (Plan 5)

**Definition of done:**
- With a real `ANTHROPIC_API_KEY` set, `make smoke-llm` classifies one synthetic test image end-to-end.
- After running the worker against a real Immich with food photos, `photo_analysis` rows show populated `stage_a_is_food`, `stage_a_confidence`; food photos additionally show `dish_name`, `cuisine`, `stage_b_confidence`.
- All pytest tests pass with `pytest-socket` blocking real network; `ruff` and `mypy` clean.
- `LLM_STAGE_A_PROVIDER=mlx` flips Stage A to the MLX provider without any code change.

---

## File map

| Path | Created in task | Responsibility |
|---|---|---|
| `src/home_photo_repo/settings_factory.py` | 1 | `load_settings()` factory that centralizes the `# type: ignore[call-arg]` |
| `src/home_photo_repo/worker/cursor.py` (modify) | 1 | Composite `(updated_at, last_id)` cursor stored as JSON |
| `src/home_photo_repo/immich_client.py` (modify) | 1 | `search_metadata` accepts `last_id` filter parameter |
| `src/home_photo_repo/worker/main.py` (modify) | 1 | Pass `(updated_at, id)` tuple through cursor + filter |
| `Makefile` (modify) | 1 | `dev-worker` depends on `ensure-db`; bootstrap fails on placeholder secrets |
| `pyproject.toml` (modify) | 1 | Drop `types-requests`; add `anthropic` dep |
| `scripts/smoke_immich.py` (modify) | 1 | Fix `order="desc"` to actually return newest |
| `src/home_photo_repo/immich_client.py` (modify) | 2 | Add `get_thumbnail(asset_id, size)` and `get_original(asset_id)` |
| `src/home_photo_repo/llm/__init__.py` | 3 | Package marker |
| `src/home_photo_repo/llm/providers/__init__.py` | 3 | Package marker |
| `src/home_photo_repo/llm/providers/base.py` | 3 | `VisionLLMProvider` Protocol, `ProviderResult` dataclass, `ProviderError` |
| `src/home_photo_repo/llm/providers/anthropic_provider.py` | 4 | Wraps `anthropic.Anthropic` for structured-output vision calls |
| `src/home_photo_repo/llm/providers/mlx_provider.py` | 5 | OpenAI-compatible Chat Completions over httpx |
| `src/home_photo_repo/llm/rate_limiter.py` | 6 | Token-bucket rate limiter, time-injectable |
| `src/home_photo_repo/llm/prompts.py` | 7 | Versioned `STAGE_A_*` / `STAGE_B_*` prompts + JSON schemas |
| `src/home_photo_repo/llm/stage_a.py` | 8 | `run_stage_a(provider, image_bytes) -> StageAResult` |
| `src/home_photo_repo/llm/stage_b.py` | 9 | `run_stage_b(provider, image_bytes, asset_context) -> StageBResult` |
| `src/home_photo_repo/llm/factory.py` | 11 | `build_provider(role, settings) -> VisionLLMProvider` |
| `src/home_photo_repo/worker/pipeline.py` (modify) | 10 | Extend state machine: discovered → stage_a → maybe stage_b → done |
| `src/home_photo_repo/worker/main.py` (modify) | 11 | Build providers from Settings; pass to pipeline |
| `scripts/smoke_llm.py` | 12 | Real-API smoke test: classify a small synthetic image |
| `Makefile` (modify) | 12 | Add `smoke-llm` target |
| `README.md` (modify) | 13 | Plan 2 setup steps + verification |
| `tests/test_cursor.py` (modify) | 1 | Composite cursor tests |
| `tests/test_immich_client.py` (modify) | 1, 2 | `last_id` filter; thumbnail/original tests |
| `tests/test_makefile_guards.py` | 1 | Asserts bootstrap exits non-zero on placeholder secrets |
| `tests/test_settings_factory.py` | 1 | `load_settings()` returns a `Settings` instance |
| `tests/test_provider_base.py` | 3 | `ProviderResult` shape; `ProviderError` |
| `tests/test_anthropic_provider.py` | 4 | Anthropic provider with mocked SDK client |
| `tests/test_mlx_provider.py` | 5 | MLX provider with respx-mocked HTTP |
| `tests/test_rate_limiter.py` | 6 | Token-bucket behavior with fake clock |
| `tests/test_prompts.py` | 7 | Prompts non-empty; JSON schemas valid |
| `tests/test_stage_a.py` | 8 | `run_stage_a` with fake provider |
| `tests/test_stage_b.py` | 9 | `run_stage_b` with fake provider |
| `tests/test_pipeline_llm.py` | 10 | Pipeline state machine with fake providers |
| `tests/test_factory.py` | 11 | `build_provider` returns right type for each setting |
| `tests/fixtures/anthropic_stage_a_response.json` | 4 | Recorded Anthropic SDK response shape |
| `tests/fixtures/openai_compat_stage_a_response.json` | 5 | Recorded OpenAI-compatible response from mlx-vlm |

---

## Conventions used in this plan

- Repo root: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home_photo_repo`. All commands run there.
- TDD order: tests first, run them failing, implement, run them passing, commit.
- All new commits in the existing `main` branch (this is a personal project; no PR workflow).
- Datetime constant is `UTC` (from `datetime import UTC`), Python 3.12+ idiom.
- `from __future__ import annotations` at the top of every new `.py` file.
- Image sizes: Stage A uses ~256×256 (load from Immich `/api/assets/{id}/thumbnail?size=thumbnail`); Stage B uses ~1024×1024 (load from `/api/assets/{id}/thumbnail?size=preview` — that's Immich's 1440px preview, close enough for our purposes; the original is too large and re-encoding adds cost without quality gain).

---

## Task 1: Plan 1 hardening (composite cursor, bootstrap UX, Makefile, settings factory, smoke script fix, drop types-requests)

This task collapses 6 Plan 1 follow-ups into one focused commit-cluster. Each sub-step is its own commit so review can be granular.

**Files:**
- Create: `src/home_photo_repo/settings_factory.py`
- Modify: `src/home_photo_repo/worker/cursor.py`
- Modify: `src/home_photo_repo/immich_client.py`
- Modify: `src/home_photo_repo/worker/main.py`
- Modify: `Makefile`
- Modify: `pyproject.toml`
- Modify: `scripts/smoke_immich.py`
- Modify: `tests/test_cursor.py`
- Modify: `tests/test_immich_client.py`
- Modify: `src/home_photo_repo/db.py` (drop the `# type: ignore[call-arg]` once `load_settings` exists)
- Create: `tests/test_settings_factory.py`
- Create: `tests/test_makefile_guards.py`

### Sub-task 1.1 — Settings factory

- [ ] **Step 1: Write the failing test — `tests/test_settings_factory.py`**

```python
"""Tests for load_settings() — centralizes the pydantic-settings call-arg ignore."""

from __future__ import annotations

import pytest


def test_load_settings_returns_settings_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_test")

    from home_photo_repo.config import Settings
    from home_photo_repo.settings_factory import load_settings

    s = load_settings()
    assert isinstance(s, Settings)
    assert s.immich_api_key.get_secret_value() == "k"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/test_settings_factory.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/home_photo_repo/settings_factory.py`**

```python
"""Centralized Settings constructor.

Wraps the `Settings()` call once so the `# type: ignore[call-arg]` (required
because pydantic-settings populates required fields from env, but mypy sees
them as missing kwargs) lives in one place.
"""

from __future__ import annotations

from home_photo_repo.config import Settings


def load_settings() -> Settings:
    """Construct a Settings instance from env / .env. Centralizes the mypy ignore."""
    return Settings()  # type: ignore[call-arg]


__all__ = ["load_settings"]
```

- [ ] **Step 4: Replace the 3 existing `Settings() # type: ignore[call-arg]` call sites**

In `src/home_photo_repo/db.py`, find:
```python
from home_photo_repo.config import Settings

settings = Settings()  # type: ignore[call-arg]
```
Change to:
```python
from home_photo_repo.settings_factory import load_settings

settings = load_settings()
```

In `src/home_photo_repo/worker/main.py`, find:
```python
def main() -> None:  # pragma: no cover - process entrypoint
    settings = Settings()  # type: ignore[call-arg]
    run_forever(settings)
```
Change to:
```python
def main() -> None:  # pragma: no cover - process entrypoint
    settings = load_settings()
    run_forever(settings)
```
And update the import at the top of `main.py`:
```python
from home_photo_repo.settings_factory import load_settings
```
(Keep `from home_photo_repo.config import Settings` for the type annotation on `run_forever`.)

In `scripts/smoke_immich.py`, same swap: import `load_settings`, call it.

- [ ] **Step 5: Run tests, verify all pass**

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
Expected: 35 tests pass (34 + 1 new); mypy + ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/home_photo_repo/settings_factory.py tests/test_settings_factory.py src/home_photo_repo/db.py src/home_photo_repo/worker/main.py scripts/smoke_immich.py
git commit -m "refactor: centralize Settings() construction in load_settings factory"
```

### Sub-task 1.2 — Composite cursor (tied-timestamp fix)

- [ ] **Step 1: Write the new test cases — append to `tests/test_cursor.py`**

```python
def test_cursor_composite_round_trip(tmp_path: Path) -> None:
    """Cursor stores a (timestamp, last_asset_id) tuple."""
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    write_cursor(conn, ts, last_id="asset-uuid-zzz")
    assert read_cursor(conn) == (ts, "asset-uuid-zzz")


def test_cursor_default_returns_epoch_and_empty_id(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assert read_cursor(conn) == (EPOCH_CURSOR, "")


def test_cursor_monotonic_by_timestamp_then_id(tmp_path: Path) -> None:
    """If timestamps are equal, the larger id wins. If timestamp is earlier, no-op."""
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    write_cursor(conn, ts, last_id="asset-005")
    write_cursor(conn, ts, last_id="asset-003")  # smaller id, no-op
    assert read_cursor(conn) == (ts, "asset-005")
    write_cursor(conn, ts, last_id="asset-009")  # larger id, advances
    assert read_cursor(conn) == (ts, "asset-009")
    earlier = ts - timedelta(seconds=1)
    write_cursor(conn, earlier, last_id="asset-zzz")  # earlier timestamp, no-op
    assert read_cursor(conn) == (ts, "asset-009")
```

Update the existing tests to use the new tuple-returning signature:

```python
def test_read_cursor_defaults_to_epoch(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assert read_cursor(conn) == (EPOCH_CURSOR, "")


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    write_cursor(conn, ts, last_id="some-id")
    assert read_cursor(conn) == (ts, "some-id")


def test_write_cursor_is_monotonic(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    later = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    earlier = datetime(2025, 1, 1, tzinfo=UTC)
    write_cursor(conn, later, last_id="a")
    write_cursor(conn, earlier, last_id="z")  # must not regress
    assert read_cursor(conn) == (later, "a")
```

Add `timedelta` to the imports if not already present.

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_cursor.py -v
```
Expected: 6 failures (3 existing + 3 new) — `read_cursor` returns a `datetime`, not a tuple; `write_cursor` doesn't accept `last_id`.

- [ ] **Step 3: Modify `src/home_photo_repo/worker/cursor.py`**

```python
"""Persistent ingestion cursor stored in worker_state.

The cursor is a (timestamp, last_asset_id) pair: among assets with the same
`updated_at`, we need a secondary key to know which we've already seen.
Otherwise a bulk import with N identically-stamped assets would re-loop
forever.

Stored serialized as JSON in a single worker_state row keyed `immich_cursor`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

CURSOR_KEY = "immich_cursor"
EPOCH_CURSOR: datetime = datetime(1970, 1, 1, tzinfo=UTC)


def read_cursor(conn: sqlite3.Connection) -> tuple[datetime, str]:
    """Return (timestamp, last_asset_id). Both empty defaults if no cursor yet."""
    row = conn.execute(
        "SELECT value FROM worker_state WHERE key = ?", (CURSOR_KEY,)
    ).fetchone()
    if row is None:
        return (EPOCH_CURSOR, "")
    data = json.loads(row["value"])
    return (datetime.fromisoformat(data["updated_at"]), data["last_id"])


def write_cursor(conn: sqlite3.Connection, ts: datetime, *, last_id: str) -> None:
    """Write the cursor if it strictly advances; otherwise no-op.

    Advances if: ts > current_ts, OR ts == current_ts AND last_id > current_last_id.
    """
    current_ts, current_id = read_cursor(conn)
    if (ts, last_id) <= (current_ts, current_id):
        return
    payload = json.dumps({"updated_at": ts.isoformat(), "last_id": last_id})
    conn.execute(
        """
        INSERT INTO worker_state (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (CURSOR_KEY, payload),
    )


__all__ = ["CURSOR_KEY", "EPOCH_CURSOR", "read_cursor", "write_cursor"]
```

- [ ] **Step 4: Run cursor tests, verify they pass**

```bash
uv run pytest tests/test_cursor.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Update `worker/main.py` to use the new cursor signature**

In `run_once`, change:
```python
cursor = read_cursor(conn)
...
assets = immich.search_metadata(updated_after=cursor, size=batch_size, order="asc")
...
write_cursor(conn, asset.updated_at)
```
to:
```python
cursor_ts, cursor_last_id = read_cursor(conn)
...
assets = immich.search_metadata(
    updated_after=cursor_ts, last_id=cursor_last_id, size=batch_size, order="asc"
)
...
write_cursor(conn, asset.updated_at, last_id=asset.id)
```

Also update the `_ImmichLike` Protocol in main.py to include `last_id`:
```python
class _ImmichLike(Protocol):
    def search_metadata(
        self,
        *,
        updated_after: datetime,
        last_id: str = ...,
        size: int = ...,
        order: str = ...,
    ) -> list[ImmichAsset]: ...
```

- [ ] **Step 6: Update `worker/main.py` tests in `tests/test_worker_main.py`**

The `FakeImmich.search_metadata` mock signature must accept `last_id`:
```python
def search_metadata(self, *, updated_after, last_id="", size=100, order="asc"):
    self.calls.append({
        "updated_after": updated_after, "last_id": last_id, "size": size, "order": order,
    })
    if not self._batches:
        return []
    return self._batches.pop(0)
```

The `BrokenImmich.search_metadata` similarly:
```python
def search_metadata(self, *, updated_after, last_id="", size=100, order="asc"):
    BrokenImmich.calls += 1
    raise ImmichClientError("simulated outage")
```

Update existing assertion `assert fake.calls[0]["updated_after"] == EPOCH_CURSOR` to also check the empty last_id:
```python
assert fake.calls[0]["updated_after"] == EPOCH_CURSOR
assert fake.calls[0]["last_id"] == ""
```

Update existing assertion `assert read_cursor(conn) == assets[-1].updated_at` to:
```python
assert read_cursor(conn) == (assets[-1].updated_at, assets[-1].id)
```

Update the `does_not_advance` test:
```python
assert read_cursor(conn) == (EPOCH_CURSOR, "")
```

- [ ] **Step 7: Modify `src/home_photo_repo/immich_client.py` to accept `last_id` filter**

Change `search_metadata` to:

```python
def search_metadata(
    self,
    *,
    updated_after: datetime,
    last_id: str = "",
    size: int = 100,
    order: str = "asc",
) -> list[ImmichAsset]:
    """Fetch assets updated after `updated_after`, oldest-first by default.

    Tied-timestamp handling: Immich's `updatedAfter` filter is strict, but
    when multiple assets share `updated_at`, the filter alone can't tell
    Immich which of them we've already seen. So we request `updated_after=ts`
    and post-filter on the client to drop any item whose
    `(updated_at, id) <= (ts, last_id)`.
    """
    body = {
        "updatedAfter": updated_after.isoformat(),
        "withExif": True,
        "order": order,
        "size": size,
    }
    resp = self._post("/api/search/metadata", json=body)
    try:
        items = resp["assets"]["items"]
    except (KeyError, TypeError) as e:
        raise ImmichClientError(f"unexpected response shape: {e!r}") from e
    parsed = [self._parse_asset(item) for item in items]
    # Drop items the cursor has already passed.
    return [a for a in parsed if (a.updated_at, a.id) > (updated_after, last_id)]
```

- [ ] **Step 8: Add a tied-timestamp test to `tests/test_immich_client.py`**

```python
@respx.mock
def test_search_metadata_filters_already_seen_with_last_id() -> None:
    """When last_id is set, items at or before that (timestamp, id) are dropped."""
    fixture = _load_fixture("immich_search_metadata.json")
    # Both assets have distinct updated_at; choose last_id == first asset id and
    # updated_after == first asset's updated_at. First asset should be filtered out.
    respx.post("http://immich.local:2283/api/search/metadata").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    # asset-uuid-1 updated_at: 2026-05-27T18:42:15.000Z
    cursor_ts = datetime(2026, 5, 27, 18, 42, 15, tzinfo=UTC)
    assets = _client().search_metadata(
        updated_after=cursor_ts, last_id="asset-uuid-1", size=100
    )
    # Only asset-uuid-2 should remain.
    assert len(assets) == 1
    assert assets[0].id == "asset-uuid-2"
```

- [ ] **Step 9: Run all tests, verify they pass**

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
Expected: 39 tests pass (35 + 3 cursor + 1 immich client + 0 from main loop sig change since the existing tests still pass after updates); mypy + ruff clean.

- [ ] **Step 10: Commit**

```bash
git add src/home_photo_repo/worker/cursor.py src/home_photo_repo/worker/main.py src/home_photo_repo/immich_client.py tests/test_cursor.py tests/test_worker_main.py tests/test_immich_client.py
git commit -m "fix: composite (updated_at, id) cursor to handle tied timestamps

Plan 1 follow-up #1. Immich's updatedAfter filter alone can't disambiguate
N assets sharing the same updated_at — bulk imports would loop. Cursor
now stores both timestamp and last-seen-id; ImmichClient post-filters
items already covered by the cursor."
```

### Sub-task 1.3 — Makefile guards + bootstrap UX + drop types-requests + smoke order fix

- [ ] **Step 1: Update `Makefile`**

Replace the file with:

```makefile
.PHONY: bootstrap ensure-db dev-worker test lint typecheck format smoke-immich

PYTHON := uv run python
PYTEST := uv run pytest

bootstrap:
	uv venv
	uv sync --all-extras
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		chmod 600 .env; \
		echo ""; \
		echo "ERROR: Created .env from template. Edit it (IMMICH_API_KEY etc.) and re-run 'make bootstrap'."; \
		exit 1; \
	fi
	@chmod 600 .env
	@if grep -qE '^(IMMICH_API_KEY|ANTHROPIC_API_KEY)=replace_me' .env; then \
		echo ""; \
		echo "ERROR: .env still contains 'replace_me' placeholder secrets. Fill them in and re-run."; \
		exit 1; \
	fi
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/db
	mkdir -p $${SSD_DATA_DIR:-$$HOME/home_photo_repo_data}/logs
	$(PYTHON) -m home_photo_repo.db migrate
	@echo "Bootstrap complete."

ensure-db:
	@if [ ! -f .env ]; then echo "ERROR: .env missing. Run 'make bootstrap' first."; exit 1; fi
	$(PYTHON) -m home_photo_repo.db migrate

dev-worker: ensure-db
	$(PYTHON) -m home_photo_repo.worker.main

test:
	$(PYTEST)

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy

format:
	uv run ruff format src tests

smoke-immich: ensure-db
	$(PYTHON) scripts/smoke_immich.py
```

- [ ] **Step 2: Update `scripts/smoke_immich.py`**

Find:
```python
assets = client.search_metadata(updated_after=since, size=5, order="asc")
print(f"Connected to {settings.immich_base_url}; got {len(assets)} assets:")
```
Change to:
```python
assets = client.search_metadata(updated_after=since, size=5, order="desc")
print(f"Connected to {settings.immich_base_url}; got {len(assets)} most recent assets:")
```

- [ ] **Step 3: Update `pyproject.toml`**

In the `[project.optional-dependencies] dev` list, remove the line `"types-requests",` and add `"anthropic>=0.40",` to the main `[project] dependencies` list (this enables Tasks 4+).

So `[project]` becomes:
```toml
[project]
name = "home_photo_repo"
version = "0.1.0"
description = "Local home-photo ingestion + analysis service on top of Immich"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "anthropic>=0.40",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-socket>=0.7",
    "respx>=0.21",
    "ruff>=0.5",
    "mypy>=1.10",
]
```

- [ ] **Step 4: Write a smoke test for the Makefile guards — `tests/test_makefile_guards.py`**

```python
"""Sanity tests: Makefile guards prevent silent misconfiguration.

We do not run `make bootstrap` (it would touch the user's environment).
Instead we shell out `make -n bootstrap` to print the recipe and grep for
the expected guard strings.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _have_make() -> bool:
    return shutil.which("make") is not None


@pytest.mark.skipif(not _have_make(), reason="make not installed")
def test_bootstrap_has_placeholder_guard() -> None:
    result = subprocess.run(
        ["make", "-n", "bootstrap"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "replace_me" in result.stdout
    assert "exit 1" in result.stdout


@pytest.mark.skipif(not _have_make(), reason="make not installed")
def test_dev_worker_depends_on_ensure_db() -> None:
    result = subprocess.run(
        ["make", "-n", "dev-worker"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    # ensure-db's recipe should appear before dev-worker's run command
    assert "home_photo_repo.db migrate" in result.stdout
    assert "home_photo_repo.worker.main" in result.stdout
```

- [ ] **Step 5: Run uv sync and tests**

```bash
uv sync --all-extras
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
Expected: 41 tests pass (39 + 2 Makefile); mypy + ruff clean.

- [ ] **Step 6: Commit**

```bash
git add Makefile pyproject.toml scripts/smoke_immich.py tests/test_makefile_guards.py
git commit -m "chore: harden Makefile (bootstrap/dev-worker guards), add anthropic dep, drop types-requests, fix smoke order

Plan 1 follow-ups #2, #3, #4, #6.
- bootstrap exits 1 if .env was just created or contains placeholder secrets
- dev-worker depends on ensure-db so missing DB fails fast at make-target level
- pyproject: add anthropic SDK (Plan 2 Stage A/B), drop unused types-requests
- smoke_immich now uses order='desc' to show actually-recent assets"
```

---

## Task 2: ImmichClient — fetch thumbnails and originals

Stage A/B need image bytes. The pipeline asks the Immich client for a thumbnail (Stage A) or preview-size image (Stage B).

**Files:**
- Modify: `src/home_photo_repo/immich_client.py`
- Modify: `tests/test_immich_client.py`

- [ ] **Step 1: Append failing tests to `tests/test_immich_client.py`**

```python
@respx.mock
def test_get_thumbnail_returns_bytes() -> None:
    fake_bytes = b"\x89PNG fake binary"
    respx.get(
        "http://immich.local:2283/api/assets/asset-1/thumbnail"
    ).mock(
        return_value=httpx.Response(200, content=fake_bytes, headers={"content-type": "image/jpeg"})
    )
    data = _client().get_thumbnail("asset-1", size="thumbnail")
    assert data == fake_bytes


@respx.mock
def test_get_thumbnail_passes_size_param() -> None:
    route = respx.get(
        "http://immich.local:2283/api/assets/asset-1/thumbnail"
    ).mock(return_value=httpx.Response(200, content=b"x"))
    _client().get_thumbnail("asset-1", size="preview")
    # respx matched the URL; check query string carried `size=preview`
    assert route.calls.last.request.url.params["size"] == "preview"


@respx.mock
def test_get_thumbnail_404_raises() -> None:
    respx.get(
        "http://immich.local:2283/api/assets/asset-1/thumbnail"
    ).mock(return_value=httpx.Response(404))
    with pytest.raises(ImmichClientError):
        _client().get_thumbnail("asset-1")


@respx.mock
def test_get_original_returns_bytes() -> None:
    fake_bytes = b"\x89PNG bigger fake"
    respx.get(
        "http://immich.local:2283/api/assets/asset-1/original"
    ).mock(return_value=httpx.Response(200, content=fake_bytes))
    data = _client().get_original("asset-1")
    assert data == fake_bytes
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_immich_client.py -v
```
Expected: AttributeError or 4 failures — `get_thumbnail` and `get_original` not defined.

- [ ] **Step 3: Add the two methods to `src/home_photo_repo/immich_client.py`**

Add inside the `ImmichClient` class, after `search_metadata`:

```python
def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
    """Fetch an asset's thumbnail or preview.

    `size` is one of:
      - "thumbnail" (~250px, fast, Stage A)
      - "preview" (~1440px, Stage B)
    """
    if size not in ("thumbnail", "preview"):
        raise ValueError(f"invalid size {size!r}; expected 'thumbnail' or 'preview'")
    return self._get_bytes(
        f"/api/assets/{asset_id}/thumbnail", params={"size": size}
    )


def get_original(self, asset_id: str) -> bytes:
    """Fetch an asset's original full-resolution bytes."""
    return self._get_bytes(f"/api/assets/{asset_id}/original")


def _get_bytes(
    self, path: str, *, params: dict[str, str] | None = None
) -> bytes:
    url = f"{self._base_url}{path}"
    try:
        response = self._client.get(url, headers=self._headers, params=params or {})
    except httpx.HTTPError as e:
        raise ImmichClientError(f"network error calling {path}: {e!r}") from e
    if response.status_code >= 400:
        raise ImmichClientError(
            f"Immich {path} returned {response.status_code}"
        )
    return response.content
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_immich_client.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 13 tests pass (9 + 4 new); mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/home_photo_repo/immich_client.py tests/test_immich_client.py
git commit -m "feat: immich client can fetch thumbnails (250/1440px) and originals"
```

---

## Task 3: Provider base interface

Defines the Protocol that Anthropic and MLX providers implement. No real logic — just types and helpers.

**Files:**
- Create: `src/home_photo_repo/llm/__init__.py`
- Create: `src/home_photo_repo/llm/providers/__init__.py`
- Create: `src/home_photo_repo/llm/providers/base.py`
- Create: `tests/test_provider_base.py`

- [ ] **Step 1: Write the failing test — `tests/test_provider_base.py`**

```python
"""Tests for the LLM provider base interface."""

from __future__ import annotations

import pytest

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
    VisionLLMProvider,
)


def test_provider_result_is_a_frozen_dataclass() -> None:
    r = ProviderResult(
        parsed={"is_food": True},
        raw='{"is_food": true}',
        latency_ms=120,
        input_tokens=200,
        output_tokens=10,
        model="anthropic:claude-haiku-4-5",
    )
    with pytest.raises((AttributeError, Exception)):
        r.latency_ms = 999  # type: ignore[misc]


def test_provider_error_is_an_exception() -> None:
    assert issubclass(ProviderError, Exception)


def test_vision_llm_provider_is_a_protocol() -> None:
    """A class that has classify() with the right shape duck-types as a provider."""

    class FakeProvider:
        name = "fake"

        def classify(
            self,
            image_bytes: bytes,
            prompt: str,
            response_schema: dict,
            max_tokens: int = 512,
        ) -> ProviderResult:
            return ProviderResult(
                parsed={"ok": True},
                raw="{}",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                model="fake",
            )

    # Static structural check: this assignment would fail at runtime if Protocol
    # were not runtime_checkable; we use isinstance only because @runtime_checkable.
    p: VisionLLMProvider = FakeProvider()
    assert isinstance(p, VisionLLMProvider)
    assert p.name == "fake"
    result = p.classify(b"", "prompt", {})
    assert result.parsed == {"ok": True}
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_provider_base.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Create package markers and base module**

`src/home_photo_repo/llm/__init__.py`:
```python
"""LLM analysis package — providers, stages, prompts, rate limiting."""
```

`src/home_photo_repo/llm/providers/__init__.py`:
```python
"""Pluggable LLM provider implementations."""
```

`src/home_photo_repo/llm/providers/base.py`:
```python
"""Vision LLM provider interface.

Both Stage A (Haiku/local-small) and Stage B (Sonnet/local-large) call the
same `classify` method. Providers handle their own SDK / HTTP transport,
prompt encoding, and JSON-schema enforcement; this layer is a thin contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class ProviderError(Exception):
    """Raised when an LLM provider call fails or returns an un-parseable response."""


@dataclass(frozen=True)
class ProviderResult:
    parsed: dict[str, Any]
    raw: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    model: str  # "<provider>:<model>" e.g. "anthropic:claude-haiku-4-5"


@runtime_checkable
class VisionLLMProvider(Protocol):
    """A vision-capable LLM that returns structured JSON output."""

    name: str  # "anthropic" | "mlx"

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult: ...


__all__ = ["ProviderError", "ProviderResult", "VisionLLMProvider"]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_provider_base.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 3 tests pass; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/home_photo_repo/llm/__init__.py src/home_photo_repo/llm/providers/__init__.py src/home_photo_repo/llm/providers/base.py tests/test_provider_base.py
git commit -m "feat: VisionLLMProvider Protocol + ProviderResult dataclass + ProviderError"
```

---

## Task 4: Anthropic provider

Implements `VisionLLMProvider` using the official `anthropic` SDK. Uses tool-use for structured JSON output (Anthropic's canonical pattern for getting parseable structured responses). The SDK's `Anthropic` client is dependency-injected so tests can pass a fake.

**Files:**
- Create: `tests/fixtures/anthropic_stage_a_response.py` (Python module, not JSON — the SDK's response is an object tree, not raw JSON)
- Create: `src/home_photo_repo/llm/providers/anthropic_provider.py`
- Create: `tests/test_anthropic_provider.py`

- [ ] **Step 1: Create the fake SDK response fixture — `tests/fixtures/anthropic_stage_a_response.py`**

```python
"""Recorded shape of an Anthropic SDK response when using tool_use for structured output.

The real SDK returns `anthropic.types.Message` objects; we build a minimal
duck-typed equivalent for tests so we don't depend on SDK internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeUsage:
    input_tokens: int = 200
    output_tokens: int = 12


@dataclass
class FakeContentBlock:
    type: str
    # For type == "tool_use":
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    # For type == "text":
    text: str = ""


@dataclass
class FakeMessage:
    content: list[FakeContentBlock]
    usage: FakeUsage = field(default_factory=FakeUsage)
    model: str = "claude-haiku-4-5"
    stop_reason: str = "tool_use"


def make_tool_use_response(tool_name: str, tool_input: dict[str, Any]) -> FakeMessage:
    return FakeMessage(
        content=[FakeContentBlock(type="tool_use", name=tool_name, input=tool_input)],
    )


def make_text_only_response(text: str) -> FakeMessage:
    return FakeMessage(content=[FakeContentBlock(type="text", text=text)], stop_reason="end_turn")
```

- [ ] **Step 2: Write failing tests — `tests/test_anthropic_provider.py`**

```python
"""Tests for AnthropicProvider. The Anthropic SDK is dependency-injected
via the `client` kwarg, so we never need a real key in tests."""

from __future__ import annotations

from typing import Any

import pytest

from home_photo_repo.llm.providers.anthropic_provider import AnthropicProvider
from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from tests.fixtures.anthropic_stage_a_response import (
    FakeMessage,
    make_text_only_response,
    make_tool_use_response,
)


class FakeAnthropicClient:
    """Duck-types enough of `anthropic.Anthropic` for testing."""

    def __init__(self, response: FakeMessage) -> None:
        self._response = response
        self.messages = self  # SDK exposes .messages.create(...)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeMessage:
        self.calls.append(kwargs)
        return self._response


def _provider(client: FakeAnthropicClient, model: str = "claude-haiku-4-5") -> AnthropicProvider:
    return AnthropicProvider(api_key="test", model=model, client=client)


def test_classify_returns_parsed_dict_from_tool_use() -> None:
    response = make_tool_use_response(
        "classify_food", {"is_food": True, "confidence": 0.92}
    )
    client = FakeAnthropicClient(response)
    p = _provider(client)
    result = p.classify(
        image_bytes=b"fake-image",
        prompt="Is this food?",
        response_schema={
            "type": "object",
            "properties": {
                "is_food": {"type": "boolean"},
                "confidence": {"type": "number"},
            },
            "required": ["is_food", "confidence"],
        },
    )
    assert isinstance(result, ProviderResult)
    assert result.parsed == {"is_food": True, "confidence": 0.92}
    assert result.model == "anthropic:claude-haiku-4-5"
    assert result.input_tokens == 200
    assert result.output_tokens == 12


def test_classify_sends_image_and_prompt_to_sdk() -> None:
    response = make_tool_use_response("classify_food", {"is_food": False, "confidence": 0.1})
    client = FakeAnthropicClient(response)
    _provider(client).classify(
        image_bytes=b"hello-image",
        prompt="Classify.",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    call = client.calls[0]
    # Verify the message structure
    msg = call["messages"][0]
    assert msg["role"] == "user"
    content = msg["content"]
    # Should have one image block + one text block
    image_blocks = [c for c in content if c.get("type") == "image"]
    text_blocks = [c for c in content if c.get("type") == "text"]
    assert len(image_blocks) == 1
    assert len(text_blocks) == 1
    assert text_blocks[0]["text"] == "Classify."
    # Tool was passed
    assert len(call["tools"]) == 1
    assert call["tool_choice"]["type"] == "tool"


def test_classify_raises_provider_error_when_no_tool_use() -> None:
    """If the model returns text instead of tool_use, that's a failure."""
    response = make_text_only_response("Sorry, I can't classify this.")
    client = FakeAnthropicClient(response)
    p = _provider(client)
    with pytest.raises(ProviderError):
        p.classify(
            image_bytes=b"x",
            prompt="x",
            response_schema={"type": "object", "properties": {}, "required": []},
        )


def test_classify_raises_provider_error_on_sdk_exception() -> None:
    class ExplodingClient:
        messages = None

        def __init__(self) -> None:
            self.messages = self

        def create(self, **kwargs: Any) -> Any:
            raise RuntimeError("boom: rate limit or whatever")

    p = AnthropicProvider(api_key="test", model="claude-haiku-4-5", client=ExplodingClient())
    with pytest.raises(ProviderError):
        p.classify(b"", "p", {"type": "object", "properties": {}, "required": []})


def test_name_is_anthropic() -> None:
    client = FakeAnthropicClient(make_tool_use_response("x", {}))
    p = _provider(client)
    assert p.name == "anthropic"
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
uv run pytest tests/test_anthropic_provider.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `src/home_photo_repo/llm/providers/anthropic_provider.py`**

```python
"""Claude provider using the official Anthropic SDK.

Uses the SDK's tool-use feature to coerce structured JSON output: we declare
a single tool whose input schema matches the desired response shape, then
force the model to call it with `tool_choice={"type": "tool", "name": ...}`.
The tool's `input` is our parsed result.
"""

from __future__ import annotations

import base64
import time
from typing import Any

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
    VisionLLMProvider,
)


_TOOL_NAME = "record_classification"


class AnthropicProvider(VisionLLMProvider):
    """VisionLLMProvider implemented against anthropic.Anthropic."""

    name: str = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any = None,
    ) -> None:
        if client is None:
            # Late import so test envs that don't need the SDK don't pay for it.
            from anthropic import Anthropic

            client = Anthropic(api_key=api_key)
        self._client = client
        self._model = model

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        message_content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            },
            {"type": "text", "text": prompt},
        ]
        tool = {
            "name": _TOOL_NAME,
            "description": "Record the structured classification result.",
            "input_schema": response_schema,
        }
        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": message_content}],
                tools=[tool],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
            )
        except Exception as e:  # noqa: BLE001 - re-raise as ProviderError
            raise ProviderError(f"anthropic SDK call failed: {e!r}") from e
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        # Extract the tool_use block.
        tool_use = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                tool_use = block
                break
        if tool_use is None:
            raise ProviderError(
                f"anthropic returned no tool_use block; stop_reason="
                f"{getattr(response, 'stop_reason', '?')!r}"
            )

        parsed = dict(tool_use.input)
        # We don't have the literal JSON string back from the SDK; serialize the
        # parsed dict deterministically so stage_b_raw_json has a useful value.
        import json

        raw = json.dumps(parsed, sort_keys=True)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        return ProviderResult(
            parsed=parsed,
            raw=raw,
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=f"anthropic:{self._model}",
        )


__all__ = ["AnthropicProvider"]
```

- [ ] **Step 5: Add `tests/fixtures/__init__.py` if missing (so the fixture module is importable)**

```bash
test -f tests/fixtures/__init__.py || touch tests/fixtures/__init__.py
```

- [ ] **Step 6: Run tests, verify they pass**

```bash
uv run pytest tests/test_anthropic_provider.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 5 tests pass; mypy + ruff clean.

If mypy complains about `anthropic` types because the SDK is now installed and provides stubs, the late import inside `__init__` should keep mypy happy at module-level. If not, add `# type: ignore[import-not-found]` on the late import.

- [ ] **Step 7: Commit**

```bash
git add src/home_photo_repo/llm/providers/anthropic_provider.py tests/test_anthropic_provider.py tests/fixtures/anthropic_stage_a_response.py tests/fixtures/__init__.py
git commit -m "feat: AnthropicProvider using SDK tool-use for structured vision output"
```

---

## Task 5: MLX provider

Implements `VisionLLMProvider` by speaking the OpenAI Chat Completions API to a localhost MLX server (e.g., `mlx-vlm`'s `mlx_vlm.server` or `mlx-omni-server`). HTTP-only; no MLX install required at this layer.

**Files:**
- Create: `tests/fixtures/openai_compat_stage_a_response.json`
- Create: `src/home_photo_repo/llm/providers/mlx_provider.py`
- Create: `tests/test_mlx_provider.py`

- [ ] **Step 1: Create the fixture — `tests/fixtures/openai_compat_stage_a_response.json`**

```json
{
  "id": "chatcmpl-fake",
  "object": "chat.completion",
  "created": 1748800000,
  "model": "mlx-community/Qwen2-VL-2B-Instruct-4bit",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"is_food\": true, \"confidence\": 0.88}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 180,
    "completion_tokens": 24,
    "total_tokens": 204
  }
}
```

- [ ] **Step 2: Write failing tests — `tests/test_mlx_provider.py`**

```python
"""Tests for MLXProvider — OpenAI-compatible HTTP client for a localhost MLX server."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
import respx

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.providers.mlx_provider import MLXProvider

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _provider(model: str = "mlx-community/Qwen2-VL-2B-Instruct-4bit") -> MLXProvider:
    return MLXProvider(base_url="http://localhost:8081/v1", model=model)


@respx.mock
def test_classify_returns_parsed_dict() -> None:
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_load_fixture("openai_compat_stage_a_response.json"))
    )
    result = _provider().classify(
        image_bytes=b"fake-image",
        prompt="Is this food?",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    assert isinstance(result, ProviderResult)
    assert result.parsed == {"is_food": True, "confidence": 0.88}
    assert result.model.startswith("mlx:")
    assert result.input_tokens == 180
    assert result.output_tokens == 24


@respx.mock
def test_classify_sends_base64_image_in_messages() -> None:
    route = respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_load_fixture("openai_compat_stage_a_response.json"))
    )
    _provider().classify(
        image_bytes=b"hello",
        prompt="classify",
        response_schema={"type": "object", "properties": {}, "required": []},
    )
    body = json.loads(route.calls.last.request.content)
    message = body["messages"][0]
    assert message["role"] == "user"
    content = message["content"]
    image_part = next(c for c in content if c["type"] == "image_url")
    text_part = next(c for c in content if c["type"] == "text")
    assert text_part["text"] == "classify"
    expected_b64 = base64.standard_b64encode(b"hello").decode("ascii")
    assert image_part["image_url"]["url"] == f"data:image/jpeg;base64,{expected_b64}"


@respx.mock
def test_classify_raises_on_http_error() -> None:
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(ProviderError):
        _provider().classify(b"", "p", {"type": "object", "properties": {}, "required": []})


@respx.mock
def test_classify_raises_when_content_not_json() -> None:
    bad = {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "I think yes!"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=bad)
    )
    with pytest.raises(ProviderError):
        _provider().classify(b"", "p", {"type": "object", "properties": {}, "required": []})


def test_name_is_mlx() -> None:
    assert _provider().name == "mlx"
```

- [ ] **Step 3: Run tests, verify they fail**

```bash
uv run pytest tests/test_mlx_provider.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `src/home_photo_repo/llm/providers/mlx_provider.py`**

```python
"""OpenAI-compatible vision provider for a localhost MLX server.

Works against any server speaking the OpenAI Chat Completions wire protocol:
mlx-vlm's `mlx_vlm.server`, mlx-omni-server, llama.cpp's server, LM Studio,
vLLM. We ask the model to respond with strictly JSON matching the supplied
schema (we put the schema into the prompt — OpenAI-compat servers vary in
their structured-output support).
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
    VisionLLMProvider,
)


class MLXProvider(VisionLLMProvider):
    name: str = "mlx"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        # Some local servers don't honor `response_format`; instruct the model
        # in the prompt to emit strict JSON matching the schema. Stage A/B
        # validators handle deviations downstream.
        schema_hint = json.dumps(response_schema, indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            "Respond with ONLY a JSON object matching this schema, no prose:\n"
            f"{schema_hint}"
        )
        body = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                        {"type": "text", "text": full_prompt},
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        url = f"{self._base_url}/chat/completions"
        started = time.perf_counter()
        try:
            response = self._client.post(url, json=body)
        except httpx.HTTPError as e:
            raise ProviderError(f"mlx HTTP error: {e!r}") from e
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise ProviderError(
                f"mlx server returned {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as e:
            raise ProviderError(f"mlx returned non-JSON body: {e!r}") from e

        try:
            content = data["choices"][0]["message"]["content"]
            usage = data["usage"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"mlx response missing expected fields: {e!r}") from e

        try:
            parsed = json.loads(content)
        except ValueError as e:
            raise ProviderError(
                f"mlx model did not emit valid JSON: {content[:200]!r}"
            ) from e
        if not isinstance(parsed, dict):
            raise ProviderError(f"mlx model emitted non-object JSON: {type(parsed).__name__}")

        return ProviderResult(
            parsed=parsed,
            raw=content,
            latency_ms=elapsed_ms,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            model=f"mlx:{self._model}",
        )


__all__ = ["MLXProvider"]
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
uv run pytest tests/test_mlx_provider.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 5 tests pass; mypy + ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/home_photo_repo/llm/providers/mlx_provider.py tests/test_mlx_provider.py tests/fixtures/openai_compat_stage_a_response.json
git commit -m "feat: MLXProvider over OpenAI-compatible HTTP for local MLX servers"
```

---

## Task 6: Rate limiter

Token-bucket. Shared between Stage A and Stage B against the global `ANTHROPIC_RATE_LIMIT_PER_MINUTE` (Stage A also draws from it because it shares a key; MLX provider has no global limit but the limiter is harmless when applied uniformly). Time is injectable for tests.

**Files:**
- Create: `src/home_photo_repo/llm/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

- [ ] **Step 1: Write failing tests — `tests/test_rate_limiter.py`**

```python
"""Token-bucket rate limiter tests with an injectable clock."""

from __future__ import annotations

from home_photo_repo.llm.rate_limiter import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_burst_capacity_allows_immediate_n_calls() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=60, capacity=10, clock=clock.time, sleep=clock.sleep)
    for _ in range(10):
        b.acquire()
    assert clock.sleeps == []  # all 10 within burst, no sleep


def test_exceeding_capacity_sleeps_until_refill() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=60, capacity=1, clock=clock.time, sleep=clock.sleep)
    b.acquire()  # consume the one token
    b.acquire()  # must sleep ~1 second to refill at 60/min
    assert len(clock.sleeps) == 1
    assert 0.95 <= clock.sleeps[0] <= 1.05  # within rounding


def test_refill_recovers_tokens_over_time() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=120, capacity=2, clock=clock.time, sleep=clock.sleep)
    b.acquire()
    b.acquire()
    clock.now += 2.0  # 4 tokens accrued at 120/min, but capped at capacity=2
    b.acquire()
    b.acquire()
    assert clock.sleeps == []


def test_acquire_n_consumes_multiple() -> None:
    clock = FakeClock()
    b = TokenBucket(rate_per_minute=60, capacity=5, clock=clock.time, sleep=clock.sleep)
    b.acquire(3)
    b.acquire(2)
    assert clock.sleeps == []
    b.acquire(1)  # bucket now empty, must wait
    assert len(clock.sleeps) == 1
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_rate_limiter.py -v
```

- [ ] **Step 3: Implement `src/home_photo_repo/llm/rate_limiter.py`**

```python
"""Token-bucket rate limiter with injectable time/sleep for tests."""

from __future__ import annotations

import time as _time
from collections.abc import Callable


class TokenBucket:
    """Simple token-bucket rate limiter.

    `rate_per_minute` tokens refill continuously, up to `capacity`. Each
    `acquire(n)` call consumes n tokens, sleeping if necessary. The
    `clock`/`sleep` callables are injectable so tests don't actually sleep.
    """

    def __init__(
        self,
        *,
        rate_per_minute: float,
        capacity: int,
        clock: Callable[[], float] = _time.monotonic,
        sleep: Callable[[float], None] = _time.sleep,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rate_per_sec = rate_per_minute / 60.0
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last = clock()
        self._clock = clock
        self._sleep = sleep

    def acquire(self, n: int = 1) -> None:
        if n <= 0:
            raise ValueError("n must be positive")
        if n > self._capacity:
            raise ValueError(f"n={n} exceeds capacity={self._capacity}")
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return
        deficit = n - self._tokens
        wait_sec = deficit / self._rate_per_sec
        self._sleep(wait_sec)
        self._refill()
        self._tokens -= n

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_sec)
            self._last = now


__all__ = ["TokenBucket"]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_rate_limiter.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 4 tests pass; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/home_photo_repo/llm/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: token-bucket rate limiter with injectable clock"
```

---

## Task 7: Prompts module

Versioned prompt strings + JSON schemas for Stage A / Stage B. Stage B in Plan 2 only asks for dish + cuisine; Plan 3 will extend it with venue context.

**Files:**
- Create: `src/home_photo_repo/llm/prompts.py`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: Write failing tests — `tests/test_prompts.py`**

```python
"""Tests for prompt strings and JSON schemas."""

from __future__ import annotations

import json

from home_photo_repo.llm.prompts import (
    STAGE_A_PROMPT,
    STAGE_A_SCHEMA,
    STAGE_A_VERSION,
    STAGE_B_PROMPT,
    STAGE_B_SCHEMA,
    STAGE_B_VERSION,
)


def test_stage_a_prompt_not_empty() -> None:
    assert STAGE_A_PROMPT.strip()
    assert "food" in STAGE_A_PROMPT.lower()


def test_stage_a_schema_is_valid_json_schema_with_required_fields() -> None:
    assert STAGE_A_SCHEMA["type"] == "object"
    props = STAGE_A_SCHEMA["properties"]
    assert "is_food" in props
    assert props["is_food"]["type"] == "boolean"
    assert "confidence" in props
    assert props["confidence"]["type"] == "number"
    assert set(STAGE_A_SCHEMA["required"]) == {"is_food", "confidence"}
    # Round-trips through json without loss
    assert json.loads(json.dumps(STAGE_A_SCHEMA)) == STAGE_A_SCHEMA


def test_stage_b_prompt_not_empty() -> None:
    assert STAGE_B_PROMPT.strip()
    assert "dish" in STAGE_B_PROMPT.lower()


def test_stage_b_schema_has_dish_and_cuisine() -> None:
    props = STAGE_B_SCHEMA["properties"]
    assert "dish_name" in props
    assert "cuisine" in props
    assert "confidence" in props
    assert set(STAGE_B_SCHEMA["required"]) == {"dish_name", "cuisine", "confidence"}


def test_versions_are_strings() -> None:
    assert isinstance(STAGE_A_VERSION, str)
    assert isinstance(STAGE_B_VERSION, str)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_prompts.py -v
```

- [ ] **Step 3: Implement `src/home_photo_repo/llm/prompts.py`**

```python
"""Versioned prompts and JSON schemas for the two LLM stages.

Versions are bumped any time the prompt or schema changes meaningfully; the
worker can use them to decide whether to re-run a stage on existing rows
(future work — Plan 1 records only the latest result).
"""

from __future__ import annotations

from typing import Any

STAGE_A_VERSION: str = "stage_a/v1"
STAGE_B_VERSION: str = "stage_b/v1"

STAGE_A_PROMPT: str = (
    "Look at this photograph and decide whether its primary subject is "
    "food or a prepared dish (including drinks, snacks, desserts, "
    "ingredients arranged for a meal). Photos of people eating count as "
    "food only if the food itself is prominent in the frame. Photos of "
    "menus, restaurant interiors without dishes, or empty plates do not "
    "count.\n\n"
    "Respond with a structured classification including a confidence "
    "score between 0.0 (definitely not food) and 1.0 (definitely food)."
)

STAGE_A_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_food": {
            "type": "boolean",
            "description": "True if the photo primarily depicts food/dish.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence in the is_food classification.",
        },
    },
    "required": ["is_food", "confidence"],
}

STAGE_B_PROMPT: str = (
    "This photograph depicts food. Identify the specific dish and its "
    "cuisine. Be specific about the dish (e.g., 'tonkotsu ramen' not "
    "just 'noodles'). For cuisine, use a short canonical label like "
    "'Japanese', 'Italian', 'Mexican', 'Cantonese', 'Thai', 'American', "
    "'Indian', etc. If you can't determine cuisine, use 'Unknown'.\n\n"
    "Provide a confidence score from 0.0 (uncertain) to 1.0 (highly "
    "confident in both dish and cuisine)."
)

STAGE_B_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dish_name": {
            "type": "string",
            "description": "Specific dish name, e.g. 'margherita pizza'.",
        },
        "cuisine": {
            "type": "string",
            "description": "Canonical cuisine label, e.g. 'Italian'.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
    "required": ["dish_name", "cuisine", "confidence"],
}

__all__ = [
    "STAGE_A_PROMPT",
    "STAGE_A_SCHEMA",
    "STAGE_A_VERSION",
    "STAGE_B_PROMPT",
    "STAGE_B_SCHEMA",
    "STAGE_B_VERSION",
]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_prompts.py -v
```
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/home_photo_repo/llm/prompts.py tests/test_prompts.py
git commit -m "feat: versioned Stage A/B prompts + JSON schemas"
```

---

## Task 8: Stage A function

Pure function: takes a provider + image bytes, returns `StageAResult`. No DB, no Immich.

**Files:**
- Create: `src/home_photo_repo/llm/stage_a.py`
- Create: `tests/test_stage_a.py`

- [ ] **Step 1: Write failing tests — `tests/test_stage_a.py`**

```python
"""Tests for stage A (is-this-food classifier)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.stage_a import StageAResult, run_stage_a


@dataclass
class FakeProvider:
    """Returns a pre-canned ProviderResult; records each call."""

    name: str = "fake"
    parsed: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        if self.parsed is None:
            self.parsed = {"is_food": True, "confidence": 0.85}

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        self._calls.append(
            {"image_bytes": image_bytes, "prompt": prompt, "response_schema": response_schema}
        )
        return ProviderResult(
            parsed=self.parsed,
            raw='{"is_food": true, "confidence": 0.85}',
            latency_ms=100,
            input_tokens=200,
            output_tokens=10,
            model="fake:tiny",
        )


def test_run_stage_a_returns_typed_result() -> None:
    p = FakeProvider()
    out = run_stage_a(p, image_bytes=b"img")
    assert isinstance(out, StageAResult)
    assert out.is_food is True
    assert out.confidence == 0.85
    assert out.model == "fake:tiny"
    assert out.raw_json == '{"is_food": true, "confidence": 0.85}'


def test_run_stage_a_sends_correct_prompt_and_schema() -> None:
    p = FakeProvider()
    run_stage_a(p, image_bytes=b"img")
    call = p._calls[0]
    assert call["image_bytes"] == b"img"
    assert "food" in call["prompt"].lower()
    assert call["response_schema"]["required"] == ["is_food", "confidence"]


def test_run_stage_a_raises_on_missing_fields() -> None:
    p = FakeProvider(parsed={"is_food": True})  # missing confidence
    with pytest.raises(ProviderError):
        run_stage_a(p, image_bytes=b"img")


def test_run_stage_a_raises_on_wrong_type() -> None:
    p = FakeProvider(parsed={"is_food": "yes", "confidence": 0.9})  # is_food not bool
    with pytest.raises(ProviderError):
        run_stage_a(p, image_bytes=b"img")


def test_run_stage_a_clamps_confidence_to_unit_interval() -> None:
    p = FakeProvider(parsed={"is_food": True, "confidence": 1.5})
    out = run_stage_a(p, image_bytes=b"img")
    assert out.confidence == 1.0
    p2 = FakeProvider(parsed={"is_food": False, "confidence": -0.1})
    out2 = run_stage_a(p2, image_bytes=b"img")
    assert out2.confidence == 0.0
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_stage_a.py -v
```

- [ ] **Step 3: Implement `src/home_photo_repo/llm/stage_a.py`**

```python
"""Stage A: is-this-food classifier.

Pure function — takes a provider and bytes, returns a typed result. Pipeline
integration (DB writes, error handling) lives in the worker pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from home_photo_repo.llm.prompts import STAGE_A_PROMPT, STAGE_A_SCHEMA
from home_photo_repo.llm.providers.base import (
    ProviderError,
    VisionLLMProvider,
)


@dataclass(frozen=True)
class StageAResult:
    is_food: bool
    confidence: float  # clamped to [0.0, 1.0]
    model: str
    raw_json: str
    latency_ms: int


def run_stage_a(provider: VisionLLMProvider, *, image_bytes: bytes) -> StageAResult:
    result = provider.classify(
        image_bytes=image_bytes,
        prompt=STAGE_A_PROMPT,
        response_schema=STAGE_A_SCHEMA,
        max_tokens=128,
    )
    parsed = result.parsed
    if "is_food" not in parsed or "confidence" not in parsed:
        raise ProviderError(f"stage_a response missing required fields: {parsed!r}")
    if not isinstance(parsed["is_food"], bool):
        raise ProviderError(f"stage_a is_food is not bool: {parsed['is_food']!r}")
    try:
        conf = float(parsed["confidence"])
    except (TypeError, ValueError) as e:
        raise ProviderError(
            f"stage_a confidence not numeric: {parsed['confidence']!r}"
        ) from e
    conf = max(0.0, min(1.0, conf))
    return StageAResult(
        is_food=parsed["is_food"],
        confidence=conf,
        model=result.model,
        raw_json=result.raw,
        latency_ms=result.latency_ms,
    )


__all__ = ["StageAResult", "run_stage_a"]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_stage_a.py -v
```
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/home_photo_repo/llm/stage_a.py tests/test_stage_a.py
git commit -m "feat: run_stage_a pure function with validation + confidence clamping"
```

---

## Task 9: Stage B function

Same shape as Stage A but returns `StageBResult` with `dish_name`, `cuisine`, `confidence`.

**Files:**
- Create: `src/home_photo_repo/llm/stage_b.py`
- Create: `tests/test_stage_b.py`

- [ ] **Step 1: Write failing tests — `tests/test_stage_b.py`**

```python
"""Tests for stage B (dish + cuisine classifier)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.llm.stage_b import StageBResult, run_stage_b


@dataclass
class FakeProvider:
    name: str = "fake"
    parsed: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        if self.parsed is None:
            self.parsed = {
                "dish_name": "margherita pizza",
                "cuisine": "Italian",
                "confidence": 0.91,
            }

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        self._calls.append({"image_bytes": image_bytes, "prompt": prompt})
        return ProviderResult(
            parsed=self.parsed,
            raw='{"dish_name": "margherita pizza", "cuisine": "Italian", "confidence": 0.91}',
            latency_ms=350,
            input_tokens=1400,
            output_tokens=80,
            model="fake:big",
        )


def test_run_stage_b_returns_typed_result() -> None:
    out = run_stage_b(FakeProvider(), image_bytes=b"img")
    assert isinstance(out, StageBResult)
    assert out.dish_name == "margherita pizza"
    assert out.cuisine == "Italian"
    assert out.confidence == 0.91


def test_run_stage_b_strips_whitespace_from_strings() -> None:
    p = FakeProvider(parsed={
        "dish_name": "  tonkotsu ramen  ", "cuisine": "  Japanese  ", "confidence": 0.8,
    })
    out = run_stage_b(p, image_bytes=b"img")
    assert out.dish_name == "tonkotsu ramen"
    assert out.cuisine == "Japanese"


def test_run_stage_b_raises_on_missing_fields() -> None:
    p = FakeProvider(parsed={"dish_name": "x", "confidence": 0.5})  # no cuisine
    with pytest.raises(ProviderError):
        run_stage_b(p, image_bytes=b"img")


def test_run_stage_b_raises_on_empty_dish_name() -> None:
    p = FakeProvider(parsed={"dish_name": "", "cuisine": "Italian", "confidence": 0.8})
    with pytest.raises(ProviderError):
        run_stage_b(p, image_bytes=b"img")


def test_run_stage_b_clamps_confidence() -> None:
    p = FakeProvider(parsed={"dish_name": "x", "cuisine": "y", "confidence": 2.0})
    out = run_stage_b(p, image_bytes=b"img")
    assert out.confidence == 1.0
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_stage_b.py -v
```

- [ ] **Step 3: Implement `src/home_photo_repo/llm/stage_b.py`**

```python
"""Stage B: dish + cuisine classifier.

Pure function. Plan 2 returns dish_name + cuisine + confidence. Plan 3 will
extend Stage B (or layer a second LLM call) with venue resolution context.
"""

from __future__ import annotations

from dataclasses import dataclass

from home_photo_repo.llm.prompts import STAGE_B_PROMPT, STAGE_B_SCHEMA
from home_photo_repo.llm.providers.base import (
    ProviderError,
    VisionLLMProvider,
)


@dataclass(frozen=True)
class StageBResult:
    dish_name: str
    cuisine: str
    confidence: float
    model: str
    raw_json: str
    latency_ms: int


def run_stage_b(provider: VisionLLMProvider, *, image_bytes: bytes) -> StageBResult:
    result = provider.classify(
        image_bytes=image_bytes,
        prompt=STAGE_B_PROMPT,
        response_schema=STAGE_B_SCHEMA,
        max_tokens=300,
    )
    parsed = result.parsed
    for field in ("dish_name", "cuisine", "confidence"):
        if field not in parsed:
            raise ProviderError(f"stage_b response missing required field {field!r}: {parsed!r}")
    dish = str(parsed["dish_name"]).strip()
    cuisine = str(parsed["cuisine"]).strip()
    if not dish:
        raise ProviderError("stage_b dish_name is empty")
    if not cuisine:
        raise ProviderError("stage_b cuisine is empty")
    try:
        conf = float(parsed["confidence"])
    except (TypeError, ValueError) as e:
        raise ProviderError(
            f"stage_b confidence not numeric: {parsed['confidence']!r}"
        ) from e
    conf = max(0.0, min(1.0, conf))
    return StageBResult(
        dish_name=dish,
        cuisine=cuisine,
        confidence=conf,
        model=result.model,
        raw_json=result.raw,
        latency_ms=result.latency_ms,
    )


__all__ = ["StageBResult", "run_stage_b"]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_stage_b.py -v
```
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/home_photo_repo/llm/stage_b.py tests/test_stage_b.py
git commit -m "feat: run_stage_b pure function returning dish_name + cuisine + confidence"
```

---

## Task 10: Pipeline integration

Extend `process_asset` to run Stage A → maybe Stage B → write results. Pipeline now needs dependencies injected: providers for both stages, an Immich client to fetch image bytes, a rate limiter, and the Settings thresholds.

**Files:**
- Modify: `src/home_photo_repo/worker/pipeline.py`
- Modify: `tests/test_pipeline.py` (existing Plan 1 tests still pass)
- Create: `tests/test_pipeline_llm.py` (new Stage A/B integration tests)

- [ ] **Step 1: Update `src/home_photo_repo/worker/pipeline.py`**

Add to the imports:

```python
import logging
from typing import Protocol

from home_photo_repo.llm.providers.base import ProviderError, VisionLLMProvider
from home_photo_repo.llm.rate_limiter import TokenBucket
from home_photo_repo.llm.stage_a import run_stage_a
from home_photo_repo.llm.stage_b import run_stage_b
```

Add new result types to the existing `ProcessResult` enum:

```python
class ProcessResult(enum.Enum):
    INSERTED = "inserted"
    ALREADY_PRESENT = "already_present"
    DEFERRED_NOT_READY = "deferred_not_ready"
    STAGE_A_NOT_FOOD = "stage_a_not_food"
    STAGE_A_AND_B_DONE = "stage_a_and_b_done"
    STAGE_A_ONLY_ERROR = "stage_a_only_error"
    STAGE_B_ERROR = "stage_b_error"
```

Add a Protocol for the thumbnail fetcher (so tests can inject a fake without a real ImmichClient):

```python
class _ThumbnailFetcher(Protocol):
    def get_thumbnail(self, asset_id: str, *, size: str = ...) -> bytes: ...
```

Add a new module-level logger:

```python
log = logging.getLogger(__name__)
```

Replace the existing `process_asset` function with this expanded version:

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
    stage_a_food_threshold: float = 0.6,
    stage_b_review_threshold: float = 0.7,
) -> ProcessResult:
    """Process one asset.

    Plan 1 path: insert discovered row (if `stage_a_provider is None`).
    Plan 2 path: insert + Stage A + (if food) Stage B.

    Keyword `immich` is required when any provider is set (needed to fetch
    image bytes). All injection points are optional so existing Plan 1
    callers continue to work.
    """
    current_time = now or _utcnow()

    # Idempotency: skip if already present.
    existing = conn.execute(
        "SELECT stage_a_ran_at, stage_b_ran_at FROM photo_analysis WHERE immich_asset_id = ?",
        (asset.id,),
    ).fetchone()
    if existing is not None:
        # If the row exists AND Stage A already ran, treat as fully present.
        if existing["stage_a_ran_at"] is not None:
            return ProcessResult.ALREADY_PRESENT
        # Row exists but Stage A hasn't run yet — fall through to LLM section
        # if providers were given (resume case).
        row_exists = True
    else:
        row_exists = False

    has_gps = asset.latitude is not None and asset.longitude is not None
    age = current_time - asset.updated_at
    if not row_exists and not has_gps and age < READINESS_MAX_AGE:
        return ProcessResult.DEFERRED_NOT_READY

    if not row_exists:
        review_status = "auto" if has_gps else "needs_review"
        last_error = None if has_gps else "no_gps"
        conn.execute(
            """
            INSERT INTO photo_analysis (
                immich_asset_id, first_seen_at, taken_at, latitude, longitude,
                uploader_user_id, review_status, last_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset.id,
                current_time.isoformat(),
                asset.taken_at.isoformat() if asset.taken_at else None,
                asset.latitude,
                asset.longitude,
                asset.owner_id or None,
                review_status,
                last_error,
            ),
        )

    # Plan 1 stop point: if no providers were injected, we're done.
    if stage_a_provider is None:
        return ProcessResult.INSERTED

    if immich is None:
        raise ValueError("process_asset: immich client required when providers given")

    # --- Stage A ---
    try:
        if rate_limiter is not None:
            rate_limiter.acquire()
        thumb_bytes = immich.get_thumbnail(asset.id, size="thumbnail")
        stage_a = run_stage_a(stage_a_provider, image_bytes=thumb_bytes)
    except ProviderError as e:
        log.warning("stage_a failed for asset %s: %s", asset.id, e)
        _record_stage_a_error(conn, asset.id, str(e))
        return ProcessResult.STAGE_A_ONLY_ERROR
    except Exception as e:  # noqa: BLE001
        log.exception("stage_a unexpected failure for asset %s", asset.id)
        _record_stage_a_error(conn, asset.id, f"unexpected: {e!r}")
        return ProcessResult.STAGE_A_ONLY_ERROR
    _record_stage_a_result(conn, asset.id, stage_a, current_time)

    if not stage_a.is_food or stage_a.confidence < stage_a_food_threshold:
        return ProcessResult.STAGE_A_NOT_FOOD

    if stage_b_provider is None:
        # Configured Stage A only.
        return ProcessResult.STAGE_A_NOT_FOOD

    # --- Stage B ---
    try:
        if rate_limiter is not None:
            rate_limiter.acquire()
        preview_bytes = immich.get_thumbnail(asset.id, size="preview")
        stage_b = run_stage_b(stage_b_provider, image_bytes=preview_bytes)
    except ProviderError as e:
        log.warning("stage_b failed for asset %s: %s", asset.id, e)
        _record_stage_b_error(conn, asset.id, str(e))
        return ProcessResult.STAGE_B_ERROR
    except Exception as e:  # noqa: BLE001
        log.exception("stage_b unexpected failure for asset %s", asset.id)
        _record_stage_b_error(conn, asset.id, f"unexpected: {e!r}")
        return ProcessResult.STAGE_B_ERROR

    needs_review = stage_b.confidence < stage_b_review_threshold
    _record_stage_b_result(
        conn, asset.id, stage_b, current_time, needs_review=needs_review
    )
    return ProcessResult.STAGE_A_AND_B_DONE


def _record_stage_a_result(
    conn: sqlite3.Connection,
    asset_id: str,
    result: "StageAResult",
    now: datetime,
) -> None:
    conn.execute(
        """
        UPDATE photo_analysis
           SET stage_a_is_food    = ?,
               stage_a_confidence = ?,
               stage_a_model      = ?,
               stage_a_ran_at     = ?,
               last_error         = NULL
         WHERE immich_asset_id = ?
        """,
        (
            1 if result.is_food else 0,
            result.confidence,
            result.model,
            now.isoformat(),
            asset_id,
        ),
    )


def _record_stage_a_error(
    conn: sqlite3.Connection, asset_id: str, message: str
) -> None:
    conn.execute(
        """
        UPDATE photo_analysis
           SET last_error    = ?,
               error_attempts = error_attempts + 1,
               review_status  = 'needs_review'
         WHERE immich_asset_id = ?
        """,
        (f"stage_a: {message}", asset_id),
    )


def _record_stage_b_result(
    conn: sqlite3.Connection,
    asset_id: str,
    result: "StageBResult",
    now: datetime,
    *,
    needs_review: bool,
) -> None:
    review_status = "needs_review" if needs_review else "auto"
    conn.execute(
        """
        UPDATE photo_analysis
           SET dish_name          = ?,
               cuisine            = ?,
               stage_b_confidence = ?,
               stage_b_model      = ?,
               stage_b_ran_at     = ?,
               stage_b_raw_json   = ?,
               review_status      = ?,
               last_error         = NULL
         WHERE immich_asset_id = ?
        """,
        (
            result.dish_name,
            result.cuisine,
            result.confidence,
            result.model,
            now.isoformat(),
            result.raw_json,
            review_status,
            asset_id,
        ),
    )


def _record_stage_b_error(
    conn: sqlite3.Connection, asset_id: str, message: str
) -> None:
    conn.execute(
        """
        UPDATE photo_analysis
           SET last_error    = ?,
               error_attempts = error_attempts + 1,
               review_status  = 'needs_review'
         WHERE immich_asset_id = ?
        """,
        (f"stage_b: {message}", asset_id),
    )
```

Then add to the imports at top (so the type hints in `_record_*` work):

```python
from home_photo_repo.llm.stage_a import StageAResult
from home_photo_repo.llm.stage_b import StageBResult
```

And update `__all__`:
```python
__all__ = ["READINESS_MAX_AGE", "ProcessResult", "process_asset"]
```

- [ ] **Step 2: Verify existing Plan 1 pipeline tests still pass**

```bash
uv run pytest tests/test_pipeline.py -v
```
Expected: 4 passed (unchanged from Plan 1 — they don't pass providers, so the Plan 1 code path is unchanged).

- [ ] **Step 3: Write the new LLM-pipeline tests — `tests/test_pipeline_llm.py`**

```python
"""Tests for the Plan 2 pipeline extensions: Stage A and Stage B integration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_photo_repo.db import apply_migrations, get_connection
from home_photo_repo.immich_types import ImmichAsset
from home_photo_repo.llm.providers.base import ProviderError, ProviderResult
from home_photo_repo.worker.pipeline import ProcessResult, process_asset

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


@dataclass
class FakeImmich:
    """Returns canned thumbnail bytes."""

    bytes_to_return: bytes = b"fake-img"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        self.calls.append((asset_id, size))
        return self.bytes_to_return


@dataclass
class FakeProvider:
    name: str
    parsed: dict[str, Any]
    should_raise: bool = False

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        if self.should_raise:
            raise ProviderError(f"{self.name} simulated failure")
        return ProviderResult(
            parsed=self.parsed,
            raw=str(self.parsed),
            latency_ms=10,
            input_tokens=100,
            output_tokens=10,
            model=f"{self.name}:test",
        )


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "app.sqlite")
    apply_migrations(conn, MIGRATIONS)
    return conn


def _asset(aid: str = "asset-1") -> ImmichAsset:
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    return ImmichAsset(
        id=aid,
        owner_id="owner-x",
        original_file_name=f"{aid}.HEIC",
        updated_at=base,
        taken_at=base - timedelta(hours=1),
        latitude=37.0,
        longitude=-122.0,
        file_created_at=base,
    )


def test_pipeline_runs_stage_a_and_records_food_result(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider("anthropic", {"dish_name": "ramen", "cuisine": "Japanese", "confidence": 0.85})
    immich = FakeImmich()

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_AND_B_DONE
    row = conn.execute(
        "SELECT stage_a_is_food, stage_a_confidence, dish_name, cuisine, "
        "stage_b_confidence, review_status FROM photo_analysis"
    ).fetchone()
    assert row["stage_a_is_food"] == 1
    assert row["stage_a_confidence"] == pytest.approx(0.95)
    assert row["dish_name"] == "ramen"
    assert row["cuisine"] == "Japanese"
    assert row["stage_b_confidence"] == pytest.approx(0.85)
    assert row["review_status"] == "auto"


def test_pipeline_skips_stage_b_when_not_food(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": False, "confidence": 0.99})
    stage_b = FakeProvider("anthropic", {"dish_name": "X", "cuisine": "Y", "confidence": 0.5})
    immich = FakeImmich()

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_NOT_FOOD
    row = conn.execute("SELECT stage_a_is_food, dish_name FROM photo_analysis").fetchone()
    assert row["stage_a_is_food"] == 0
    assert row["dish_name"] is None  # stage B did not run


def test_pipeline_skips_stage_b_when_confidence_below_threshold(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.3})  # below 0.6
    stage_b = FakeProvider("anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    immich = FakeImmich()

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_NOT_FOOD
    row = conn.execute("SELECT dish_name FROM photo_analysis").fetchone()
    assert row["dish_name"] is None


def test_pipeline_flags_low_confidence_stage_b_for_review(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider("anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.4})  # below 0.7
    immich = FakeImmich()

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_AND_B_DONE
    row = conn.execute("SELECT review_status FROM photo_analysis").fetchone()
    assert row["review_status"] == "needs_review"


def test_pipeline_records_stage_a_error_and_stops(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {}, should_raise=True)
    stage_b = FakeProvider("anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    immich = FakeImmich()

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_A_ONLY_ERROR
    row = conn.execute("SELECT last_error, review_status, error_attempts FROM photo_analysis").fetchone()
    assert row["last_error"].startswith("stage_a:")
    assert row["review_status"] == "needs_review"
    assert row["error_attempts"] == 1


def test_pipeline_records_stage_b_error(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider("anthropic", {}, should_raise=True)
    immich = FakeImmich()

    result = process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )

    assert result is ProcessResult.STAGE_B_ERROR
    row = conn.execute(
        "SELECT stage_a_is_food, dish_name, last_error, review_status FROM photo_analysis"
    ).fetchone()
    assert row["stage_a_is_food"] == 1  # stage A still recorded
    assert row["dish_name"] is None
    assert row["last_error"].startswith("stage_b:")
    assert row["review_status"] == "needs_review"


def test_pipeline_uses_thumbnail_for_a_and_preview_for_b(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider("anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    immich = FakeImmich()

    process_asset(
        conn, _asset(), now=_asset().updated_at,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )
    sizes_requested = [size for (_, size) in immich.calls]
    assert sizes_requested == ["thumbnail", "preview"]


def test_pipeline_already_present_short_circuits_after_stage_a(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    stage_a = FakeProvider("anthropic", {"is_food": True, "confidence": 0.95})
    stage_b = FakeProvider("anthropic", {"dish_name": "x", "cuisine": "y", "confidence": 0.9})
    immich = FakeImmich()
    a = _asset()
    now = a.updated_at

    first = process_asset(
        conn, a, now=now,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )
    assert first is ProcessResult.STAGE_A_AND_B_DONE
    second = process_asset(
        conn, a, now=now,
        immich=immich, stage_a_provider=stage_a, stage_b_provider=stage_b,
    )
    assert second is ProcessResult.ALREADY_PRESENT
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_pipeline.py tests/test_pipeline_llm.py -v
uv run mypy
uv run ruff check src tests
```
Expected: 4 (Plan 1) + 8 (Plan 2) = 12 pipeline tests pass; full suite total now around 60. mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/home_photo_repo/worker/pipeline.py tests/test_pipeline_llm.py
git commit -m "feat: pipeline runs Stage A → Stage B, records results and errors"
```

---

## Task 11: Provider factory + wire into worker main

The factory reads Settings and constructs the right provider class. The main loop builds two providers (one per stage) and a rate limiter, then passes them into `run_once` which forwards them into `process_asset`.

**Files:**
- Create: `src/home_photo_repo/llm/factory.py`
- Create: `tests/test_factory.py`
- Modify: `src/home_photo_repo/worker/main.py`
- Modify: `tests/test_worker_main.py`

### Part A — Factory

- [ ] **Step 1: Write failing tests — `tests/test_factory.py`**

```python
"""Tests for build_provider — chooses Anthropic vs MLX from Settings."""

from __future__ import annotations

import pytest

from home_photo_repo.llm.factory import build_provider
from home_photo_repo.llm.providers.anthropic_provider import AnthropicProvider
from home_photo_repo.llm.providers.mlx_provider import MLXProvider


def _make_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str):
    monkeypatch.setenv("IMMICH_BASE_URL", "http://localhost:2283")
    monkeypatch.setenv("IMMICH_API_KEY", "k")
    monkeypatch.setenv("SSD_DATA_DIR", "/tmp/hpr_factory_test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", overrides.get("anthropic_key", "fake-anthropic"))
    for k, v in overrides.items():
        if k != "anthropic_key":
            monkeypatch.setenv(k, v)
    from home_photo_repo.config import Settings

    return Settings()  # type: ignore[call-arg]


def test_build_anthropic_provider_for_stage_a(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch, LLM_STAGE_A_PROVIDER="anthropic", LLM_STAGE_A_MODEL="claude-haiku-4-5")
    p = build_provider("stage_a", s)
    assert isinstance(p, AnthropicProvider)
    assert p.name == "anthropic"


def test_build_mlx_provider_for_stage_b(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(
        monkeypatch,
        LLM_STAGE_B_PROVIDER="mlx",
        LLM_STAGE_B_MODEL="mlx-community/Qwen2-VL-7B-Instruct-4bit",
    )
    p = build_provider("stage_b", s)
    assert isinstance(p, MLXProvider)
    assert p.name == "mlx"


def test_build_provider_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch, LLM_STAGE_A_PROVIDER="gemini")
    with pytest.raises(ValueError):
        build_provider("stage_a", s)


def test_build_provider_rejects_unknown_role(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _make_settings(monkeypatch)
    with pytest.raises(ValueError):
        build_provider("stage_z", s)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/test_factory.py -v
```

- [ ] **Step 3: Implement `src/home_photo_repo/llm/factory.py`**

```python
"""Provider factory — chooses Anthropic vs MLX per stage from Settings."""

from __future__ import annotations

from typing import Literal

from home_photo_repo.config import Settings
from home_photo_repo.llm.providers.anthropic_provider import AnthropicProvider
from home_photo_repo.llm.providers.base import VisionLLMProvider
from home_photo_repo.llm.providers.mlx_provider import MLXProvider

Role = Literal["stage_a", "stage_b"]


def build_provider(role: Role, settings: Settings) -> VisionLLMProvider:
    if role == "stage_a":
        provider_name = settings.llm_stage_a_provider
        model = settings.llm_stage_a_model
    elif role == "stage_b":
        provider_name = settings.llm_stage_b_provider
        model = settings.llm_stage_b_model
    else:
        raise ValueError(f"unknown role {role!r}; expected 'stage_a' or 'stage_b'")

    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=model,
        )
    if provider_name == "mlx":
        # MLX models for each stage live in their own settings keys; use the
        # role-specific override if the generic *_MODEL points at an Anthropic
        # name (common when only one stage is switched to MLX).
        mlx_model = (
            settings.mlx_stage_a_model if role == "stage_a" else settings.mlx_stage_b_model
        )
        return MLXProvider(base_url=settings.mlx_base_url, model=mlx_model)
    raise ValueError(
        f"unknown provider {provider_name!r}; expected 'anthropic' or 'mlx'"
    )


__all__ = ["Role", "build_provider"]
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
uv run pytest tests/test_factory.py -v
```
Expected: 4 tests pass.

### Part B — Worker main wiring

- [ ] **Step 5: Update `src/home_photo_repo/worker/main.py`**

At the top, add:

```python
from home_photo_repo.llm.factory import build_provider
from home_photo_repo.llm.providers.base import VisionLLMProvider
from home_photo_repo.llm.rate_limiter import TokenBucket
```

Replace the `_ImmichLike` Protocol to include the thumbnail method (so the worker can pass the ImmichClient down into the pipeline):

```python
class _ImmichLike(Protocol):
    def search_metadata(
        self,
        *,
        updated_after: datetime,
        last_id: str = ...,
        size: int = ...,
        order: str = ...,
    ) -> list[ImmichAsset]: ...

    def get_thumbnail(self, asset_id: str, *, size: str = ...) -> bytes: ...
```

Update `run_once` signature and pass-through:

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
    stage_a_food_threshold: float = 0.6,
    stage_b_review_threshold: float = 0.7,
) -> RunSummary:
```

In the per-asset loop, replace `process_asset(conn, asset, now=current_time)` with:

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
)
```

Update `run_forever` to construct providers + rate limiter and pass them to `run_once`:

```python
def run_forever(settings: Settings) -> None:  # pragma: no cover - integration entrypoint
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    repo_root = Path(__file__).resolve().parents[3]
    conn = get_connection(settings.db_path)
    apply_migrations(conn, repo_root / "migrations")
    immich = ImmichClient(
        base_url=str(settings.immich_base_url),
        api_key=settings.immich_api_key.get_secret_value(),
    )
    stage_a_provider = build_provider("stage_a", settings)
    stage_b_provider = build_provider("stage_b", settings)
    rate_limiter = TokenBucket(
        rate_per_minute=settings.anthropic_rate_limit_per_minute,
        capacity=max(1, settings.anthropic_rate_limit_per_minute // 4),
    )
    log.info(
        "worker starting: poll_interval=%ss batch_size=%s db=%s stage_a=%s stage_b=%s",
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
        stage_a_provider.name,
        stage_b_provider.name,
    )
    try:
        while True:
            summary = run_once(
                conn, immich,
                batch_size=settings.backfill_batch_size,
                stage_a_provider=stage_a_provider,
                stage_b_provider=stage_b_provider,
                rate_limiter=rate_limiter,
                stage_a_food_threshold=settings.stage_a_food_threshold,
                stage_b_review_threshold=settings.stage_b_confidence_review_threshold,
            )
            log.info(
                "run complete: seen=%d processed=%d errors=%d",
                summary.assets_seen,
                summary.assets_processed,
                summary.errors,
            )
            time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        log.info("worker shutting down (KeyboardInterrupt)")
    finally:
        immich.close()
        conn.close()
```

- [ ] **Step 6: Update `tests/test_worker_main.py` — `FakeImmich` needs `get_thumbnail`**

```python
class FakeImmich:
    def __init__(self, batches: list[list[ImmichAsset]]):
        self._batches = list(batches)
        self.calls: list[dict[str, Any]] = []

    def search_metadata(self, *, updated_after, last_id="", size=100, order="asc"):
        self.calls.append({
            "updated_after": updated_after, "last_id": last_id, "size": size, "order": order,
        })
        if not self._batches:
            return []
        return self._batches.pop(0)

    def get_thumbnail(self, asset_id: str, *, size: str = "thumbnail") -> bytes:
        return b"thumb-bytes"
```

Existing tests don't pass `stage_a_provider`, so the pipeline falls through to Plan 1 behavior. No changes to assertions needed.

- [ ] **Step 7: Add one new test exercising the LLM path through `run_once`**

```python
def test_run_once_with_providers_invokes_stage_a(tmp_path: Path) -> None:
    from typing import Any

    from home_photo_repo.llm.providers.base import ProviderResult

    class StubProvider:
        name = "stub"

        def __init__(self, parsed: dict[str, Any]) -> None:
            self.parsed = parsed
            self.calls = 0

        def classify(self, image_bytes, prompt, response_schema, max_tokens=512):
            self.calls += 1
            return ProviderResult(
                parsed=self.parsed, raw="{}", latency_ms=1,
                input_tokens=1, output_tokens=1, model=f"stub:{self.name}",
            )

    conn = _conn(tmp_path)
    a = _asset("a", 1)
    fake = FakeImmich(batches=[[a]])
    stage_a = StubProvider({"is_food": False, "confidence": 0.9})
    stage_b = StubProvider({"dish_name": "x", "cuisine": "y", "confidence": 0.9})

    summary = run_once(
        conn, fake, batch_size=10,
        now=datetime(2026, 5, 28, 13, 0, 0, tzinfo=UTC),
        stage_a_provider=stage_a, stage_b_provider=stage_b,
    )

    assert summary.assets_processed == 1
    assert stage_a.calls == 1
    assert stage_b.calls == 0  # not food
    row = conn.execute("SELECT stage_a_is_food FROM photo_analysis").fetchone()
    assert row["stage_a_is_food"] == 0
```

Make sure `UTC` and `datetime` are imported in this test file (they already are from prior Plan 1 work).

- [ ] **Step 8: Run all tests + lint + typecheck**

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```
Expected: ~65 tests pass; mypy + ruff clean.

- [ ] **Step 9: Commit**

```bash
git add src/home_photo_repo/llm/factory.py src/home_photo_repo/worker/main.py tests/test_factory.py tests/test_worker_main.py
git commit -m "feat: provider factory + worker main wires Stage A/B providers and rate limiter"
```

---

## Task 12: LLM smoke script

A one-shot script the user runs after Plan 2 install to verify their Anthropic key works end-to-end. Loads a tiny synthetic image (a small magenta PNG) and classifies it with Stage A.

**Files:**
- Create: `scripts/smoke_llm.py`
- Modify: `Makefile`

- [ ] **Step 1: Create `scripts/smoke_llm.py`**

```python
"""Manual smoke test: run Stage A on a synthetic image to verify provider config.

Run with:
    make smoke-llm
"""

from __future__ import annotations

import base64
import sys

from home_photo_repo.llm.factory import build_provider
from home_photo_repo.llm.stage_a import run_stage_a
from home_photo_repo.settings_factory import load_settings

# 16x16 solid-magenta PNG, base64-encoded. Pure synthetic — won't classify as food
# but will exercise the entire round-trip (API key, image upload, JSON parse).
_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAH0lEQVQ4jWP8//8/AzZAxh"
    "MnGEYNGDVg1IBRA0YNoCYAAFMWAv8XOmAvAAAAAElFTkSuQmCC"
)


def main() -> int:
    settings = load_settings()
    if settings.anthropic_api_key.get_secret_value() in ("", "replace_me"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        return 2
    provider = build_provider("stage_a", settings)
    print(f"Using provider: {provider.name} (model={settings.llm_stage_a_model})")
    image_bytes = base64.b64decode(_TINY_PNG_BASE64)
    result = run_stage_a(provider, image_bytes=image_bytes)
    print(f"Stage A result on synthetic image:")
    print(f"  is_food   = {result.is_food}")
    print(f"  confidence= {result.confidence}")
    print(f"  model     = {result.model}")
    print(f"  latency   = {result.latency_ms}ms")
    print(f"  raw       = {result.raw_json}")
    print("\nProvider round-trip succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Append `smoke-llm` to `Makefile`**

```makefile

smoke-llm:
	$(PYTHON) scripts/smoke_llm.py
```

Also add `smoke-llm` to the `.PHONY` list.

- [ ] **Step 3: Verify script parses + imports without running**

```bash
uv run python -c "import importlib.util, sys; spec = importlib.util.spec_from_file_location('smoke', 'scripts/smoke_llm.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('ok')"
```
Expected: `ok` (no exception).

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_llm.py Makefile
git commit -m "feat: smoke-llm script verifies provider round-trip on a synthetic image"
```

---

## Task 13: Final lint/typecheck/test sweep + README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full check sweep**

```bash
uv run pytest -v
uv run ruff check src tests
uv run mypy
```
All must be green. If anything is flagged, fix it before continuing.

- [ ] **Step 2: Update `README.md`**

Find the section that begins with `This is **Plan 1 (Foundation & Ingestion)**.` and replace through the end of that paragraph with:

```markdown
This is **Plan 2 (LLM Pipeline)**. The worker now classifies each ingested
photo: Stage A (Claude Haiku 4.5) decides whether the photo is food, and
food photos additionally get Stage B (Claude Sonnet 4.5) which fills in
`dish_name` and `cuisine`. Venue / restaurant assignment is Plan 3.
```

Find the Roadmap section and update the Plan 2 entry:

```markdown
- **Plan 2** ✅ Done — Stage A (Haiku) + Stage B (Sonnet) with pluggable
  provider interface (Anthropic default, MLX optional).
```

Add a new section after `## Development`, before `## Project layout`:

```markdown
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
```

Update the Project layout section to reflect new files:

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
```

- [ ] **Step 3: Final test/lint/typecheck after README edits**

```bash
uv run pytest -v
uv run ruff check src tests
uv run mypy
```
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README updated for Plan 2 (LLM pipeline, MLX provider, smoke-llm)"
```

---

## Plan 2 acceptance checklist

- [ ] `make test` — all tests pass (target: ~65 tests)
- [ ] `make lint` — clean
- [ ] `make typecheck` — clean
- [ ] `make bootstrap` on a fresh checkout with placeholder secrets — exits non-zero (Plan 1 follow-up #2)
- [ ] `make smoke-llm` (with real `ANTHROPIC_API_KEY`) — succeeds and prints Stage A result
- [ ] Worker on real Immich populates `stage_a_is_food`, `stage_a_confidence`; food photos additionally get `dish_name`, `cuisine`, `stage_b_confidence`
- [ ] Setting `LLM_STAGE_A_PROVIDER=mlx` swaps Stage A's provider without code changes (verify by inspecting log line on `make dev-worker` startup — should say "stage_a=mlx")
- [ ] No secrets leak in logs (check that `make dev-worker` startup line shows `db=` path but no API key string)

Once green, Plan 2 is complete. Move on to Plan 3 (place matching).
