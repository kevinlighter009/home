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
