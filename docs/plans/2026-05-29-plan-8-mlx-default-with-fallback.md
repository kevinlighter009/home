# Plan 8 — MLX-default with Anthropic fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local MLX the default provider; when MLX is unreachable, the worker automatically falls back to Anthropic for that call. Per-call fallback, no manual switching needed.

**Architecture:** A new `FallbackProvider` wraps a primary `VisionLLMProvider` and a fallback `VisionLLMProvider`. On `classify()`, it tries the primary first; on connection-class errors (`httpx.ConnectError`, `httpx.TimeoutException`, 5xx HTTP responses surfaced as `ProviderError`), it transparently retries via the fallback. Configuration errors (401, 403, malformed-response `ProviderError`) propagate up — they're not transient. A new `llm_fallback_provider` Setting controls whether the factory wraps providers in `FallbackProvider`. Defaults change to `mlx` for both stages with `anthropic` as the fallback, so a fresh install (with both keys configured) gets local-first behavior out of the box.

**Tech Stack:** No new deps. Touches `home_photo_repo.llm.providers.fallback_provider` (new), `factory.py`, `config.py`, `.env.example`. Adds ~10 tests.

**Plan 7 follow-up addressed:** Plan 7 #2 (MLX server auto-warmup probe) is partially solved by this — instead of a probe, we let the first request fail and transparently retry on Anthropic.

**Definition of done:**
- New users with both `ANTHROPIC_API_KEY` and an MLX server set up get MLX-first classification with automatic Anthropic fallback when the server is unreachable.
- Worker startup log line shows `stage_a=mlx→anthropic` (the new format) when fallback is configured.
- Tests cover: primary success (no fallback), primary connection error → fallback used, primary auth error → propagates, no fallback configured → original behavior.
- ruff + mypy clean.

---

## File map

| Path | Created in task | Purpose |
|---|---|---|
| `src/home_photo_repo/llm/providers/fallback_provider.py` | 1 | `FallbackProvider` class wrapping primary + fallback |
| `tests/test_fallback_provider.py` | 1 | Unit tests for fallback behavior |
| `src/home_photo_repo/config.py` (modify) | 2 | Add `llm_fallback_provider: str = ""` field; constants for new defaults |
| `.env.example` (modify) | 2 | Reflect new defaults — MLX primary, Anthropic fallback |
| `src/home_photo_repo/llm/factory.py` (modify) | 3 | Wrap in `FallbackProvider` when `llm_fallback_provider` is set |
| `tests/test_factory.py` (modify) | 3 | Test that factory composes correctly |
| `src/home_photo_repo/worker/main.py` (modify) | 4 | Update startup log to show fallback chain (e.g., `stage_a=mlx→anthropic`) |
| `docs/operations.md` (modify) | 5 | Document fallback behavior |
| `README.md` (modify) | 5 | Update LLM provider options section |
| `docs/plans/2026-05-29-plan-8-followups.md` | 5 | Capture anything that comes up |

---

## Task 1: `FallbackProvider`

### Files
- Create: `src/home_photo_repo/llm/providers/fallback_provider.py`
- Create: `tests/test_fallback_provider.py`

### Step 1: Failing tests — `tests/test_fallback_provider.py`

```python
"""Tests for FallbackProvider — composes a primary + fallback VisionLLMProvider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
)
from home_photo_repo.llm.providers.fallback_provider import FallbackProvider


@dataclass
class FakeProvider:
    """Returns a canned ProviderResult, or raises a canned exception."""

    name: str
    canned_result: ProviderResult | None = None
    canned_exception: BaseException | None = None

    def __post_init__(self) -> None:
        self.calls: int = 0

    def classify(
        self, image_bytes: bytes, prompt: str, response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        self.calls += 1
        if self.canned_exception is not None:
            raise self.canned_exception
        assert self.canned_result is not None
        return self.canned_result


def _ok_result(model: str) -> ProviderResult:
    return ProviderResult(
        parsed={"is_food": True, "confidence": 0.9},
        raw='{"is_food": true, "confidence": 0.9}',
        latency_ms=10, input_tokens=1, output_tokens=1, model=model,
    )


def test_fallback_returns_primary_when_primary_succeeds() -> None:
    primary = FakeProvider("primary", canned_result=_ok_result("mlx:m"))
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "mlx:m"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_fallback_used_when_primary_raises_connect_error() -> None:
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx HTTP error: ConnectError()"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "anthropic:c"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_fallback_used_when_primary_raises_5xx_provider_error() -> None:
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx server returned 503: Service Unavailable"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "anthropic:c"
    assert fallback.calls == 1


def test_fallback_used_when_primary_raises_timeout() -> None:
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx HTTP error: TimeoutException()"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    result = p.classify(b"img", "prompt", {})

    assert result.model == "anthropic:c"
    assert fallback.calls == 1


def test_auth_errors_propagate_no_fallback() -> None:
    """401/403 are config errors — failing over wouldn't help. Propagate."""
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx server returned 401: Unauthorized"),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    with pytest.raises(ProviderError):
        p.classify(b"img", "prompt", {})
    assert fallback.calls == 0


def test_malformed_response_propagates_no_fallback() -> None:
    """Bad JSON shape is the model's fault — fallback wouldn't help."""
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx model did not emit valid JSON: ..."),
    )
    fallback = FakeProvider("fallback", canned_result=_ok_result("anthropic:c"))
    p = FallbackProvider(primary=primary, fallback=fallback)

    with pytest.raises(ProviderError):
        p.classify(b"img", "prompt", {})
    assert fallback.calls == 0


def test_name_reflects_chain() -> None:
    primary = FakeProvider("primary", canned_result=_ok_result("x"))
    fallback = FakeProvider("fallback", canned_result=_ok_result("y"))
    primary.name = "mlx"  # type: ignore[misc]
    fallback.name = "anthropic"  # type: ignore[misc]
    p = FallbackProvider(primary=primary, fallback=fallback)
    assert p.name == "mlx→anthropic"


def test_fallback_propagates_when_fallback_also_fails() -> None:
    """If fallback ALSO fails, the fallback's exception is raised
    (with the primary's context attached)."""
    primary = FakeProvider(
        "primary",
        canned_exception=ProviderError("mlx connection refused"),
    )
    fallback = FakeProvider(
        "fallback",
        canned_exception=ProviderError("anthropic 503"),
    )
    p = FallbackProvider(primary=primary, fallback=fallback)
    with pytest.raises(ProviderError) as exc_info:
        p.classify(b"img", "prompt", {})
    # Fallback's error should be in the message
    assert "anthropic" in str(exc_info.value)
```

### Step 2: Run, verify fail

```bash
uv run pytest tests/test_fallback_provider.py -v
```

### Step 3: Implement `src/home_photo_repo/llm/providers/fallback_provider.py`

```python
"""FallbackProvider — composes two VisionLLMProviders with auto-fallback.

The primary provider is tried first. If it raises a *transient* error
(connection refused, timeout, 5xx HTTP response), the fallback is invoked.
Configuration errors (4xx auth, malformed responses) propagate so the
operator can see them.

Usage:
    primary = MLXProvider(base_url="http://localhost:8081/v1", model=...)
    fallback = AnthropicProvider(api_key=..., model=...)
    provider = FallbackProvider(primary=primary, fallback=fallback)
"""

from __future__ import annotations

import logging
from typing import Any

from home_photo_repo.llm.providers.base import (
    ProviderError,
    ProviderResult,
    VisionLLMProvider,
)

log = logging.getLogger(__name__)

# Substrings in a ProviderError message that indicate a transient failure
# where falling over to another provider could succeed.
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "ConnectError",
    "ConnectTimeout",
    "TimeoutException",
    "ReadTimeout",
    "Network is unreachable",
    "Connection refused",
    "returned 500",
    "returned 502",
    "returned 503",
    "returned 504",
)


def _looks_transient(error: BaseException) -> bool:
    msg = str(error)
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


class FallbackProvider(VisionLLMProvider):
    """Try primary, fall back to secondary on transient failures only."""

    name: str

    def __init__(
        self,
        *,
        primary: VisionLLMProvider,
        fallback: VisionLLMProvider,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self.name = f"{primary.name}→{fallback.name}"

    def classify(
        self,
        image_bytes: bytes,
        prompt: str,
        response_schema: dict[str, Any],
        max_tokens: int = 512,
    ) -> ProviderResult:
        try:
            return self._primary.classify(
                image_bytes=image_bytes,
                prompt=prompt,
                response_schema=response_schema,
                max_tokens=max_tokens,
            )
        except ProviderError as primary_err:
            if not _looks_transient(primary_err):
                # Not a transient error — propagate so operator notices
                # configuration / model problems immediately.
                raise
            log.warning(
                "primary provider %s failed (%s); falling back to %s",
                self._primary.name, primary_err, self._fallback.name,
            )
            try:
                return self._fallback.classify(
                    image_bytes=image_bytes,
                    prompt=prompt,
                    response_schema=response_schema,
                    max_tokens=max_tokens,
                )
            except ProviderError as fallback_err:
                raise ProviderError(
                    f"both providers failed — primary {self._primary.name}: "
                    f"{primary_err!r}; fallback {self._fallback.name}: {fallback_err!r}"
                ) from fallback_err


__all__ = ["FallbackProvider"]
```

### Step 4: Run + commit

```bash
uv run pytest tests/test_fallback_provider.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/llm/providers/fallback_provider.py \
        tests/test_fallback_provider.py
git commit -m "feat: FallbackProvider — primary + fallback with transient-error detection"
```

Expected: 8 new tests pass; full suite ~195.

---

## Task 2: Settings field + defaults

### Files
- Modify: `src/home_photo_repo/config.py`
- Modify: `.env.example`

### Step 1: Modify `src/home_photo_repo/config.py`

Add a new field to the `Settings` class (place it near the other `llm_*` fields):

```python
    # When the per-stage provider raises a transient error (connection refused,
    # timeout, 5xx), automatically retry with this fallback provider. Set to
    # an empty string to disable fallback (original strict behavior).
    llm_fallback_provider: str = "anthropic"
```

Change the default per-stage providers to `mlx`:

```python
    llm_stage_a_provider: str = "mlx"
    llm_stage_a_model: str = "claude-haiku-4-5"
    llm_stage_b_provider: str = "mlx"
    llm_stage_b_model: str = "claude-sonnet-4-5"
```

(Stage models stay as Anthropic names — they're only consulted when the resolved provider is Anthropic. The MLX model is set by `mlx_stage_*_model`.)

### Step 2: Modify `.env.example`

Find the existing LLM provider block (around the `LLM_STAGE_A_PROVIDER=anthropic` lines). Replace with:

```dotenv
# LLM provider selection
# Default: MLX local server primary, Anthropic API fallback if MLX unreachable.
# Requires both:
#   - mlx-vlm + launchd MLX service (see docs/operations.md § Provider option B)
#   - A valid ANTHROPIC_API_KEY for fallback
# Switch to API-only by setting LLM_STAGE_*_PROVIDER=anthropic.
LLM_STAGE_A_PROVIDER=mlx
LLM_STAGE_A_MODEL=claude-haiku-4-5
LLM_STAGE_B_PROVIDER=mlx
LLM_STAGE_B_MODEL=claude-sonnet-4-5
# Fallback when primary fails transiently. Empty string disables fallback.
LLM_FALLBACK_PROVIDER=anthropic
```

### Step 3: Run test sweep (no behavior change yet — factory wires up in Task 3)

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

Existing factory tests should still pass — they test default-built providers and don't set `llm_fallback_provider`.

### Step 4: Commit

```bash
git add src/home_photo_repo/config.py .env.example
git commit -m "feat: defaults flip to MLX-primary + Anthropic-fallback; new llm_fallback_provider setting"
```

---

## Task 3: Factory composition

### Files
- Modify: `src/home_photo_repo/llm/factory.py`
- Modify: `tests/test_factory.py`

### Step 1: Modify `src/home_photo_repo/llm/factory.py`

Add to imports:

```python
from home_photo_repo.llm.providers.fallback_provider import FallbackProvider
```

Refactor `build_provider` so the existing per-name construction is extracted, then wrapped in `FallbackProvider` when fallback is configured.

Find the existing function. Replace with:

```python
def _build_concrete_provider(
    role: Role, provider_name: str, settings: Settings
) -> VisionLLMProvider:
    """Build the specific provider type — no fallback wrapping."""
    if role == "stage_a":
        model = settings.llm_stage_a_model
    elif role == "stage_b":
        model = settings.llm_stage_b_model
    else:
        raise ValueError(f"unknown role {role!r}; expected 'stage_a' or 'stage_b'")

    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=model,
        )
    if provider_name == "mlx":
        mlx_model = (
            settings.mlx_stage_a_model if role == "stage_a" else settings.mlx_stage_b_model
        )
        return MLXProvider(base_url=settings.mlx_base_url, model=mlx_model)
    raise ValueError(
        f"unknown provider {provider_name!r}; expected 'anthropic' or 'mlx'"
    )


def build_provider(role: Role, settings: Settings) -> VisionLLMProvider:
    """Build the provider for `role`, optionally wrapping in FallbackProvider.

    If `settings.llm_fallback_provider` is set AND differs from the primary,
    the result is a FallbackProvider that tries the primary first and falls
    back to the secondary on transient errors.
    """
    if role == "stage_a":
        primary_name = settings.llm_stage_a_provider
    elif role == "stage_b":
        primary_name = settings.llm_stage_b_provider
    else:
        raise ValueError(f"unknown role {role!r}; expected 'stage_a' or 'stage_b'")

    primary = _build_concrete_provider(role, primary_name, settings)

    fallback_name = settings.llm_fallback_provider
    if not fallback_name or fallback_name == primary_name:
        # No fallback configured, or fallback is the same as primary — no wrapping.
        return primary

    fallback = _build_concrete_provider(role, fallback_name, settings)
    return FallbackProvider(primary=primary, fallback=fallback)
```

Keep the existing `Role` type alias and `__all__`.

### Step 2: Append failing tests to `tests/test_factory.py`

```python
def test_build_provider_wraps_in_fallback_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When llm_fallback_provider is set and differs from primary, the
    factory returns a FallbackProvider composing both."""
    from home_photo_repo.llm.providers.fallback_provider import FallbackProvider

    s = _make_settings(
        monkeypatch,
        LLM_STAGE_A_PROVIDER="mlx",
        LLM_FALLBACK_PROVIDER="anthropic",
    )
    p = build_provider("stage_a", s)
    assert isinstance(p, FallbackProvider)
    assert p.name == "mlx→anthropic"


def test_build_provider_no_wrap_when_fallback_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty fallback means no wrapping — returns the raw provider."""
    s = _make_settings(
        monkeypatch,
        LLM_STAGE_A_PROVIDER="mlx",
        LLM_FALLBACK_PROVIDER="",
    )
    p = build_provider("stage_a", s)
    assert p.name == "mlx"  # not 'mlx→…'


def test_build_provider_no_wrap_when_fallback_equals_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If fallback == primary, composition is pointless. No wrap."""
    s = _make_settings(
        monkeypatch,
        LLM_STAGE_A_PROVIDER="anthropic",
        LLM_FALLBACK_PROVIDER="anthropic",
    )
    p = build_provider("stage_a", s)
    assert p.name == "anthropic"
```

### Step 3: Run + commit

```bash
uv run pytest tests/test_factory.py -v
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/llm/factory.py tests/test_factory.py
git commit -m "feat: factory composes FallbackProvider when llm_fallback_provider is set"
```

Expected: ~3 new tests + full suite ~198.

---

## Task 4: Worker startup log + small cleanup

### Files
- Modify: `src/home_photo_repo/worker/main.py`

### Step 1: Modify `src/home_photo_repo/worker/main.py`

Find the existing `log.info("worker starting: ..."` block. Update it to show the composed chain (already works because `provider.name` is the chained name like `mlx→anthropic`):

Find:

```python
    log.info(
        "worker starting: poll_interval=%ss batch_size=%s db=%s "
        "stage_a=%s stage_b=%s google_places=%s",
        settings.poll_interval_seconds,
        settings.backfill_batch_size,
        settings.db_path,
        stage_a_provider.name,
        stage_b_provider.name,
        "enabled" if google_client else "disabled (curated places only)",
    )
```

No change needed to this line — `stage_a_provider.name` will already be `mlx→anthropic` when fallback is wired. But add a startup-time validation: if the resolved primary provider for either stage is `mlx`, hit the MLX `/v1/models` endpoint once with a 2-second timeout and log whether it's reachable. This gives the operator immediate feedback at startup, not on the first photo.

Add after the providers are built and before the `log.info("worker starting...")`:

```python
    # Friendly heads-up: probe MLX once at startup so the operator sees
    # immediately whether the local server is reachable.
    if "mlx" in (settings.llm_stage_a_provider, settings.llm_stage_b_provider):
        try:
            import httpx as _httpx
            r = _httpx.get(f"{settings.mlx_base_url}/models", timeout=2.0)
            if r.status_code == 200:
                log.info("MLX server reachable at %s", settings.mlx_base_url)
            else:
                log.warning(
                    "MLX server at %s returned %s — fallback will be used per-call",
                    settings.mlx_base_url, r.status_code,
                )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "MLX server at %s unreachable (%s) — fallback will be used per-call",
                settings.mlx_base_url, e,
            )
```

### Step 2: Run + commit

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add src/home_photo_repo/worker/main.py
git commit -m "feat: worker probes MLX at startup and logs reachability"
```

---

## Task 5: Docs + Plan 8 follow-ups + push

### Files
- Modify: `docs/operations.md`
- Modify: `README.md`
- Create: `docs/plans/2026-05-29-plan-8-followups.md`

### Step 1: Update `docs/operations.md`

Find the "Provider option B: Local MLX (Apple Silicon)" section. At the top, after the intro paragraph, insert a new subsection:

```markdown
### Automatic fallback (default behavior)

The default configuration sets MLX as primary AND configures Anthropic as
the per-call fallback (`LLM_FALLBACK_PROVIDER=anthropic` in `.env.example`).
What this means in practice:

- **MLX server up + reachable** → all classification happens locally.
- **MLX server down / not installed / model not yet downloaded** → the
  worker's `classify()` raises a transient error, the FallbackProvider
  catches it, and Anthropic handles the call. No data loss, no
  needs_review flag — just a `log.warning` line and per-call slowness.

This means a fresh install with both an `ANTHROPIC_API_KEY` and an MLX
server set up will use local inference by default. If you haven't run
`make install-mlx` yet, fallback to Anthropic is automatic; the worker
keeps running.

To **disable** fallback (strict mode — fail loudly if primary is down):

```dotenv
LLM_FALLBACK_PROVIDER=
```

To **use only Anthropic** (no MLX at all):

```dotenv
LLM_STAGE_A_PROVIDER=anthropic
LLM_STAGE_B_PROVIDER=anthropic
LLM_FALLBACK_PROVIDER=
```

The worker's startup log line will show the active chain, e.g.
`stage_a=mlx→anthropic` (fallback configured) vs `stage_a=mlx` (strict).
```

Also update the "Reverting to Anthropic" subsection — keep it but note that
the auto-fallback often makes manual reversion unnecessary.

### Step 2: Update `README.md`

Find `## LLM provider options`. Replace the section with:

```markdown
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
```

### Step 3: Create `docs/plans/2026-05-29-plan-8-followups.md`

```markdown
# Plan 8 Follow-ups

Plan 8 made MLX the default with Anthropic auto-fallback. Items captured.

## Open

1. **Circuit-breaker for repeated MLX failures.** Today, when MLX is
   down, every classify() call still tries MLX first (paying the
   connection-refused round-trip ~10ms) before falling back. A
   per-process circuit breaker that remembers "MLX is down for the next
   N minutes" would skip the wasted attempt. Worth doing if real-world
   logs show meaningful latency from repeated probes.

2. **Per-stage fallback override.** Today `LLM_FALLBACK_PROVIDER` is a
   single value applied to both stages. If someone wants Stage A to
   fail strictly (no fallback) but Stage B to fall back, they need a
   per-stage knob: `LLM_STAGE_A_FALLBACK_PROVIDER`,
   `LLM_STAGE_B_FALLBACK_PROVIDER`. Not requested yet.

3. **Metrics on fallback rate.** A `worker_runs.fallback_invocations`
   column would let the dashboard show "MLX-vs-Anthropic ratio" over
   time. Useful for understanding whether MLX is healthy. Not a UX
   priority.

## Deliberately skipped

- **Async fallback** that races both providers and uses the faster one.
  Too clever; obscures cost accounting.
- **Health-check endpoint on the dashboard** showing MLX/Anthropic status
  separately. The /status page already shows pipeline errors; doubling
  up on provider status would be noisy.
```

### Step 4: Update README Roadmap

Find the Roadmap. Add at the end:

```markdown
- **Plan 8** ✅ Done — MLX-default with Anthropic auto-fallback.
  Local-first classification when MLX is reachable; transparent fallback
  per-call when not.
```

### Step 5: Final sweep + commit + push

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add docs/operations.md README.md docs/plans/2026-05-29-plan-8-followups.md
git commit -m "docs: Plan 8 (MLX-default + Anthropic fallback) + Plan 8 follow-ups"

git push origin main
```

## Plan 8 acceptance checklist

- [ ] `make test` passes (~198 tests)
- [ ] `make lint` + `make typecheck` clean
- [ ] `FallbackProvider` raises on auth/config errors; falls back on transient errors
- [ ] `build_provider` returns `FallbackProvider` when `llm_fallback_provider` is set + differs from primary
- [ ] `build_provider` returns the raw provider when `llm_fallback_provider` is empty or equal to primary
- [ ] Worker startup probes MLX once and logs reachability
- [ ] `.env.example` defaults to MLX with Anthropic fallback
- [ ] README + operations.md explain the new behavior
- [ ] All 6 prior plans still work — strict-mode Anthropic-only path (`LLM_FALLBACK_PROVIDER=`) preserves the original behavior
