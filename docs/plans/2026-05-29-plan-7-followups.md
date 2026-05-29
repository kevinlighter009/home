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
