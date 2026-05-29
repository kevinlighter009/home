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
