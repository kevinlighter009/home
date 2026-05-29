# Plan 7 — Local MLX Pipeline (second provider option) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make running a local MLX vision model a first-class alternative to the Anthropic API — sensible defaults for a 36GB Mac, one-command install, smoke test, and clear docs.

**Architecture:** Plumbing already exists from Plan 2: `MLXProvider` speaks the OpenAI Chat Completions wire format to a localhost server; `LLM_STAGE_A_PROVIDER` / `LLM_STAGE_B_PROVIDER` env vars switch per stage; a `com.homephoto.mlx.plist.template` boots the server at login. This plan picks a strong default model (`mlx-community/Qwen2.5-VL-7B-Instruct-4bit` — ~5 GB RAM, excellent vision quality, fast on Apple Silicon), wires it as the default in config + template, adds `mlx-vlm` as an opt-in dep group, and adds `make install-mlx` / `make smoke-mlx` for one-command setup and verification.

**Tech Stack:** `mlx-vlm>=0.1.20` (provides `mlx_vlm.server` — OpenAI-compatible Chat Completions endpoint). No code changes needed to `MLXProvider`. Apple Silicon (M1+) required.

**Model rationale for a 36GB Mac:**

| Goal | Model | RAM | Notes |
|---|---|---|---|
| **Default (balanced)** | `mlx-community/Qwen2.5-VL-7B-Instruct-4bit` | ~5 GB | Best quality/size; serves both stages |
| Speed-first (≤16GB Mac) | `mlx-community/Qwen2-VL-2B-Instruct-4bit` | ~1.5 GB | Lower quality but fast |
| Quality-first (64GB+) | `mlx-community/Qwen2.5-VL-32B-Instruct-4bit` | ~18 GB | Heavier; slower per call |
| Lighter-weight 7B alternative | `mlx-community/Qwen2.5-VL-7B-Instruct-6bit` | ~6 GB | Slightly better than 4-bit, ~10% more RAM |

The default leaves ~30 GB free on a 36GB machine for Docker + Immich + browser + OS — comfortable headroom.

**Single-model-per-server constraint:** `mlx_vlm.server --model X --port 8081` loads ONE model. Both Stage A and Stage B requests hit the same server, so `MLX_STAGE_A_MODEL` and `MLX_STAGE_B_MODEL` must match the server's loaded model. Running different models per stage requires two MLX servers on different ports — that's advanced and documented but not the default.

**Definition of done:**
- New users can run a single `make install-mlx` after `make bootstrap` and be running fully offline within ~5 min (model download time aside).
- `make smoke-mlx` verifies the MLX server is reachable and returns a valid classification result.
- Default config + launchd template + `.env.example` all reference `Qwen2.5-VL-7B-Instruct-4bit`.
- `docs/operations.md` MLX section is the canonical reference: install, switch providers, model options.
- README explains "Provider option B: Local MLX" alongside the Anthropic option.
- All existing tests pass (no behavioral regressions); ruff + mypy clean.

---

## File map

| Path | Created in task | Purpose |
|---|---|---|
| `src/home_photo_repo/config.py` (modify) | 1 | Update `mlx_stage_a_model` and `mlx_stage_b_model` defaults to `Qwen2.5-VL-7B-Instruct-4bit` |
| `.env.example` (modify) | 1 | Same default |
| `launchd/com.homephoto.mlx.plist.template` (modify) | 1 | Same default in `--model` arg |
| `tests/test_config.py` (modify) | 1 | Update expected-default assertion if any (most likely none — the existing test doesn't pin the value) |
| `pyproject.toml` (modify) | 2 | Add `[project.optional-dependencies] mlx = ["mlx-vlm>=0.1.20"]` |
| `requirements-mlx.txt` | 2 | Mirror for pip users |
| `Makefile` (modify) | 3 | Add `install-mlx` + `smoke-mlx` targets |
| `scripts/smoke_mlx.py` | 3 | Manual smoke test: start server, classify synthetic image, exit |
| `docs/operations.md` (modify) | 4 | Comprehensive "Provider B: Local MLX" section with model alternatives |
| `README.md` (modify) | 4 | Add quick-start blurb pointing at operations.md |
| `docs/plans/2026-05-29-plan-7-followups.md` | 5 | Capture anything that comes up |

---

## Conventions

- Repo root: `/Users/kailiang-mac-deeproute/Documents/code/llm_project/home`.
- TDD: tests where applicable; config/Makefile/docs tasks are verified via execution + inspection.
- No new top-level dependencies; `mlx-vlm` is opt-in.

---

## Task 1: Update default MLX model to Qwen2.5-VL-7B-Instruct-4bit

### Files
- Modify: `src/home_photo_repo/config.py`
- Modify: `.env.example`
- Modify: `launchd/com.homephoto.mlx.plist.template`

### Step 1: Modify `src/home_photo_repo/config.py`

Find the existing MLX field defaults:

```python
    mlx_stage_a_model: str = "mlx-community/Qwen2-VL-2B-Instruct-4bit"
    mlx_stage_b_model: str = "mlx-community/Qwen2-VL-7B-Instruct-4bit"
```

Change both to the same new default:

```python
    # Default to a single 7B model that comfortably fits ~5 GB on a 16+ GB Mac
    # and serves both stages. mlx_vlm.server hosts ONE model at a time, so
    # these two values must match unless you run two MLX servers on
    # different ports. See docs/operations.md for the multi-model setup.
    mlx_stage_a_model: str = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
    mlx_stage_b_model: str = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
```

### Step 2: Modify `.env.example`

Find:

```dotenv
MLX_STAGE_A_MODEL=mlx-community/Qwen2-VL-2B-Instruct-4bit
MLX_STAGE_B_MODEL=mlx-community/Qwen2-VL-7B-Instruct-4bit
```

Change to:

```dotenv
# MLX server hosts ONE model — Stage A + Stage B must use the same value.
# Default (~5 GB RAM, excellent on Apple Silicon):
MLX_STAGE_A_MODEL=mlx-community/Qwen2.5-VL-7B-Instruct-4bit
MLX_STAGE_B_MODEL=mlx-community/Qwen2.5-VL-7B-Instruct-4bit
```

### Step 3: Modify `launchd/com.homephoto.mlx.plist.template`

Find the existing `--model` arg in the `ProgramArguments` array:

```xml
        <string>--model</string>
        <string>mlx-community/Qwen2-VL-2B-Instruct-4bit</string>
```

Change to:

```xml
        <string>--model</string>
        <string>mlx-community/Qwen2.5-VL-7B-Instruct-4bit</string>
```

### Step 4: Verify mlx-template test still passes

```bash
uv run pytest tests/test_install_launchd.py::test_mlx_template_substitutes_to_valid_xml -v
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

Expected: all ~187 tests still pass; mypy + ruff clean.

### Step 5: Commit

```bash
git add src/home_photo_repo/config.py .env.example launchd/com.homephoto.mlx.plist.template
git commit -m "feat: bump default MLX model to Qwen2.5-VL-7B-Instruct-4bit

Stronger out-of-the-box vision quality at ~5 GB RAM, comfortable on a
16+ GB Mac. The MLX server hosts one model at a time, so Stage A and
Stage B now default to the same value — multi-model setups are an
advanced option documented in operations.md."
```

---

## Task 2: Add `mlx-vlm` as opt-in dependency group

### Files
- Modify: `pyproject.toml`
- Create: `requirements-mlx.txt`

### Step 1: Modify `pyproject.toml`

Find the `[project.optional-dependencies]` block. It currently has only `dev`. Add a new group `mlx`:

```toml
[project.optional-dependencies]
dev = [
    # ... existing dev deps ...
]
mlx = [
    "mlx-vlm>=0.1.20",
]
```

Don't touch existing entries.

### Step 2: Create `requirements-mlx.txt`

```text
# Optional MLX local-model dependencies.
# Install with: pip install -r requirements-mlx.txt
# (Apple Silicon only — mlx-vlm requires Metal.)

-r requirements.txt
mlx-vlm>=0.1.20
```

### Step 3: Verify `uv` understands the new group

```bash
uv sync --extra mlx --dry-run 2>&1 | head -20
```

Expected: `uv` reports that it would install `mlx-vlm` (and its deps, primarily `mlx`). No errors.

Do NOT actually install (the implementer's environment is probably not Apple Silicon, and even if it is, installing mlx-vlm in CI is overkill). Production users install via `make install-mlx` in Task 3.

### Step 4: Commit

```bash
git add pyproject.toml requirements-mlx.txt
git commit -m "feat: opt-in mlx-vlm dependency group (Apple Silicon only)

Install with 'uv sync --extra mlx' or 'pip install -r requirements-mlx.txt'.
make install-mlx wraps this in Task 3."
```

---

## Task 3: `make install-mlx` + `make smoke-mlx` + smoke script

### Files
- Modify: `Makefile`
- Create: `scripts/smoke_mlx.py`

### Step 1: Add Makefile targets

In `Makefile`'s `.PHONY` list, add `install-mlx` and `smoke-mlx`:

Find the existing line (it currently lists many targets):

```
.PHONY: bootstrap bootstrap-existing ensure-db dev-worker dev-dashboard test lint typecheck format smoke-immich smoke-llm smoke-places smoke-dashboard install-launchd uninstall-launchd logs backup-now
```

Add `install-mlx smoke-mlx` at the end:

```
.PHONY: bootstrap bootstrap-existing ensure-db dev-worker dev-dashboard test lint typecheck format smoke-immich smoke-llm smoke-places smoke-dashboard install-launchd uninstall-launchd logs backup-now install-mlx smoke-mlx
```

At the bottom of `Makefile`, append:

```makefile

install-mlx:
	@echo "Installing mlx-vlm (Apple Silicon required)..."
	uv sync --extra mlx
	@echo ""
	@echo "Installing the MLX launchd service..."
	$(PYTHON) -m launchd.install_launchd mlx
	@echo ""
	@echo "MLX installed. Model will download on first run (~5 GB)."
	@echo "Switch a stage to MLX by setting in .env:"
	@echo "    LLM_STAGE_A_PROVIDER=mlx"
	@echo "    LLM_STAGE_B_PROVIDER=mlx"
	@echo "Then: make smoke-mlx  (verifies end-to-end)"

smoke-mlx:
	$(PYTHON) scripts/smoke_mlx.py
```

### Step 2: Create `scripts/smoke_mlx.py`

```python
"""Manual smoke test: verify the local MLX server is reachable and classifies
a synthetic image end-to-end.

Run with:
    make smoke-mlx

Assumes either:
  - The MLX launchd service is running (make install-mlx installed it), OR
  - You started the server manually: uv run mlx_vlm.server --model X --port 8081
"""

from __future__ import annotations

import struct
import sys
import time
import zlib

import httpx

from home_photo_repo.llm.providers.mlx_provider import MLXProvider
from home_photo_repo.llm.stage_a import run_stage_a
from home_photo_repo.settings_factory import load_settings


def _make_solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Generate a minimal valid RGB PNG. Same helper smoke_llm uses."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data)
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    r, g, b = rgb
    row = bytes([0]) + bytes([r, g, b]) * width
    raw = row * height
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _wait_for_server(base_url: str, timeout_s: float = 10.0) -> bool:
    """Poll /v1/models until the server responds 200 or timeout."""
    deadline = time.monotonic() + timeout_s
    url = f"{base_url}/models"
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    settings = load_settings()
    base_url = settings.mlx_base_url
    print(f"MLX server: {base_url}")
    print(f"Stage A model: {settings.mlx_stage_a_model}")

    if not _wait_for_server(base_url):
        print(
            f"\nERROR: MLX server at {base_url} not reachable.\n"
            "Start it manually:\n"
            f"    uv run mlx_vlm.server --model {settings.mlx_stage_a_model} --port 8081\n"
            "Or install the launchd service: make install-mlx\n",
            file=sys.stderr,
        )
        return 2

    provider = MLXProvider(
        base_url=base_url, model=settings.mlx_stage_a_model,
    )
    print("Classifying a 256x256 synthetic image (Stage A)...")
    image_bytes = _make_solid_png(256, 256, (255, 0, 255))
    result = run_stage_a(provider, image_bytes=image_bytes)
    print(f"  is_food   = {result.is_food}")
    print(f"  confidence= {result.confidence}")
    print(f"  model     = {result.model}")
    print(f"  latency   = {result.latency_ms}ms")
    print(f"  raw       = {result.raw_json}")
    print("\nMLX round-trip succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Step 3: Verify script imports cleanly (no real network)

```bash
uv run python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('s', 'scripts/smoke_mlx.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('ok')
"
```

Expected: `ok`.

### Step 4: Run full test suite (no behavior change; these are inert config files)

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

Expected: all green.

### Step 5: Commit

```bash
git add Makefile scripts/smoke_mlx.py
git commit -m "feat: make install-mlx / smoke-mlx for one-command local provider setup"
```

---

## Task 4: Operations docs + README update

### Files
- Modify: `docs/operations.md`
- Modify: `README.md`

### Step 1: Update `docs/operations.md` — replace the existing MLX section

Find the existing "Optional: MLX vision server" section. Replace it ENTIRELY with the following expanded version (which makes MLX a first-class option, not a footnote):

```markdown
## Provider option B: Local MLX (Apple Silicon)

The default pipeline uses Anthropic's Claude API. If you'd rather run
everything locally (zero per-call cost, full offline operation), swap in
a vision model running on your Mac via [mlx-vlm](https://github.com/Blaizzy/mlx-vlm).
The architecture supports per-stage provider selection — you can keep
Anthropic for one stage and MLX for the other, or use MLX for both.

### Requirements

- Apple Silicon (M1 or newer)
- ≥16 GB unified memory (the default model needs ~5 GB; comfortable on 16 GB+; recommended ≥24 GB)
- ~10 GB free disk for model + cache

### Quick install

```bash
make install-mlx
```

This:
1. Installs `mlx-vlm` via the `mlx` extras group.
2. Installs the `com.homephoto.mlx` launchd service (auto-starts at login).
3. Prints next-step instructions.

Then enable MLX for one or both stages by editing `.env`:

```dotenv
LLM_STAGE_A_PROVIDER=mlx     # use MLX for is-food check
LLM_STAGE_B_PROVIDER=mlx     # use MLX for dish + cuisine
```

Then verify and restart the worker:

```bash
make smoke-mlx                                       # round-trip a synthetic image
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
```

The worker's startup log line will now print `stage_a=mlx` (or `stage_b=mlx`).

### Choosing a model

The MLX server hosts ONE model at a time. Stage A and Stage B both target
that single model unless you run two MLX servers on different ports (advanced).

| Use case | Model | RAM | Speed | Notes |
|---|---|---|---|---|
| **Default (balanced)** | `mlx-community/Qwen2.5-VL-7B-Instruct-4bit` | ~5 GB | Fast | What `make install-mlx` installs |
| Lighter (16 GB Mac, prefer speed) | `mlx-community/Qwen2-VL-2B-Instruct-4bit` | ~1.5 GB | Fastest | Lower quality |
| Better quality, slightly more RAM | `mlx-community/Qwen2.5-VL-7B-Instruct-6bit` | ~6 GB | Slightly slower than 4-bit | ~10% RAM overhead |
| High quality (64 GB+ Mac) | `mlx-community/Qwen2.5-VL-32B-Instruct-4bit` | ~18 GB | Slower | Production-grade vision |

To change the model:

1. Edit `launchd/com.homephoto.mlx.plist.template` — change the `--model` value.
2. Edit `.env` — set `MLX_STAGE_A_MODEL` and `MLX_STAGE_B_MODEL` to the SAME new value.
3. Re-install:

   ```bash
   uv run python -m launchd.install_launchd mlx
   ```

The first invocation after a model change triggers a one-time download
(~3–20 GB depending on model). Subsequent boots are instant.

### Different models per stage (advanced)

If you want a fast small model for Stage A and a heavier model for
Stage B, you need to run two MLX servers on two ports:

1. Add a second port (e.g., `8082`) and a second plist
   (`launchd/com.homephoto.mlx-b.plist.template`).
2. Adjust `MLX_BASE_URL_STAGE_A` / `MLX_BASE_URL_STAGE_B` — but note that
   the current code uses a single `MLX_BASE_URL`. You'd need to extend
   `Settings` and `build_provider` to accept two URLs. This is a real
   change, not just config.

For most users, the single-model default delivers good results without
the operational complexity.

### Reverting to Anthropic

```bash
# In .env:
LLM_STAGE_A_PROVIDER=anthropic
LLM_STAGE_B_PROVIDER=anthropic

# Optionally uninstall the MLX launchd service:
uv run python -m launchd.uninstall_launchd mlx

# Restart the worker:
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
```

### Verifying the local pipeline

After enabling MLX:

```bash
make smoke-mlx       # round-trip a synthetic image through Stage A
```

Then take a food photo with your iPhone. Within one poll cycle, the
worker should classify it without making any external API calls — you
can verify with Activity Monitor (no Anthropic-bound network traffic
during processing).

### Troubleshooting

- **`make smoke-mlx` says "server not reachable"** — the launchd service
  may still be starting. First-run loads the model from disk; that can
  take 10–30 s. Wait, then re-try. Check
  `tail ~/Library/Logs/home_photo_repo/mlx.err.log` for errors.
- **Model download stalls** — `mlx-vlm` downloads from Hugging Face on
  first run. If you're behind a corporate proxy, set `HF_ENDPOINT` or
  use `huggingface-cli login` first.
- **High thermal throttling** — the 32B model can heat a MacBook
  noticeably under sustained load. Use 7B unless you have an iMac or
  Mac Studio with active cooling.
- **`mlx-vlm` install fails on Intel Mac** — Intel is not supported.
  Stay on the Anthropic provider.
```

### Step 2: Update `README.md`

Find the existing `## LLM provider selection` section (or similar — it currently mentions Anthropic + MLX as a brief one-liner). Replace it with:

```markdown
## LLM provider options

Two providers ship out of the box:

### Provider A: Anthropic Claude (default)

`make smoke-llm` verifies your `ANTHROPIC_API_KEY`. Cost: ~$10/year at
typical family use. No local resources required.

### Provider B: Local MLX (Apple Silicon)

Run everything offline on your Mac. Default model
(`Qwen2.5-VL-7B-Instruct-4bit`) uses ~5 GB RAM and works well on any
16+ GB Apple Silicon Mac.

```bash
make install-mlx    # installs mlx-vlm + launchd service
```

Then enable in `.env`:

```dotenv
LLM_STAGE_A_PROVIDER=mlx
LLM_STAGE_B_PROVIDER=mlx
```

Verify:

```bash
make smoke-mlx
```

See [`docs/operations.md` § Provider option B](docs/operations.md#provider-option-b-local-mlx-apple-silicon)
for model alternatives, mixing providers per stage, and troubleshooting.

### Mixing providers

Each stage's provider is independent:

```dotenv
LLM_STAGE_A_PROVIDER=mlx        # fast local is-food check
LLM_STAGE_B_PROVIDER=anthropic  # higher-quality dish identification
```

This pattern uses MLX for the high-volume Stage A (every photo) and
Anthropic for the lower-volume Stage B (only food photos) — minimizing
both latency and API spend.
```

### Step 3: Final test sweep

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests
```

All green. Expected total: ~187 tests pass (no new tests; docs-only commit).

### Step 4: Commit

```bash
git add docs/operations.md README.md
git commit -m "docs: Provider option B (Local MLX) — comprehensive setup + model alternatives"
```

---

## Task 5: Plan 7 follow-ups + push

### Step 1: Create `docs/plans/2026-05-29-plan-7-followups.md`

```markdown
# Plan 7 Follow-ups

Plan 7 made the local MLX provider first-class. Items captured for future
reference.

## Open (advanced)

1. **Per-stage MLX URLs.** Today `Settings` has a single `mlx_base_url`.
   Users wanting different models per stage need to run two MLX servers
   on different ports — but the code path only supports one URL. Extend
   to `mlx_base_url_stage_a` / `mlx_base_url_stage_b` (with the single
   `mlx_base_url` as a fallback for both). Self-contained change in
   `config.py` + `llm/factory.py`.

2. **MLX server auto-warmup probe.** First request after the server
   boots can take 10–30 s as the model loads. The worker has no
   awareness — it just sees a slow response. A small `/v1/models` probe
   in `MLXProvider.__init__` (or first `classify()` call) with a warmup
   timeout would degrade gracefully.

3. **Model-caching policy.** mlx-vlm downloads models to
   `~/.cache/huggingface/`. On a system with limited disk, multiple
   model trials can fill up disk fast. Document `HF_HUB_CACHE` override
   for users wanting to keep models on the external SSD.

## Deliberately skipped

- **Bundling the model.** Tempting to pre-download
  `Qwen2.5-VL-7B-Instruct-4bit` into the install flow, but ~5 GB of
  model weights inflates the repo and complicates licensing audits.
  Lazy download on first server boot is the right tradeoff.
- **MLX provider auto-detection.** Probing whether MLX is reachable and
  silently falling back to Anthropic would mask configuration errors.
  Explicit `.env` choice keeps behavior predictable.
```

### Step 2: Update README's Roadmap

Find the Roadmap section. Add a Plan 7 line at the end:

```markdown
- **Plan 7** ✅ Done — Local MLX vision pipeline as a first-class
  alternative to the Anthropic API. One-command install
  (`make install-mlx`), default model `Qwen2.5-VL-7B-Instruct-4bit`.
```

### Step 3: Final commit + push

```bash
uv run pytest -v
uv run mypy
uv run ruff check src tests

git add docs/plans/2026-05-29-plan-7-followups.md README.md
git commit -m "docs: Plan 7 follow-ups + roadmap entry"

git push origin main
```

Expected: all green; push succeeds.

---

## Plan 7 acceptance checklist

- [ ] `make test` — all tests pass (~187, no new tests)
- [ ] `make lint` + `make typecheck` clean
- [ ] Config + .env.example + launchd template all reference `Qwen2.5-VL-7B-Instruct-4bit`
- [ ] `pyproject.toml` has `[project.optional-dependencies] mlx = ["mlx-vlm>=0.1.20"]`
- [ ] `requirements-mlx.txt` mirrors for pip
- [ ] `make -n install-mlx` shows the expected recipe
- [ ] `make -n smoke-mlx` shows the expected recipe
- [ ] `scripts/smoke_mlx.py` imports cleanly
- [ ] README + operations.md both explain Provider B in proportion to Provider A
- [ ] Plan 7 follow-ups committed

Once green, anyone on an Apple Silicon Mac can switch from Anthropic to
local MLX in two commands (`make install-mlx` + edit `.env`) — no other
plumbing required.
