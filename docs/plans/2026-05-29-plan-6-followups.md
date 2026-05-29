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

## Surfaced during final review

These came up in the Plan 6 final code review. All minor — no fix required to ship.

1. **`pipeline.py:35` — `disambiguate` re-export with `noqa: F401`.**
   Added during Task 10 with a "for users who want to compose manually"
   comment, but no caller uses it. Either delete or document the intended
   composition pattern with a docstring example.

2. **Curated-side ambiguity never populates `ambiguous_candidates`.**
   `matcher.py:_resolve_local` is intentionally asymmetric with the
   Google branch — the LLM disambiguator targets Google candidates per
   spec §4.3. Worth a one-line comment explaining the asymmetry so
   future maintainers don't try to "fix" it.

3. **`0.6` disambiguator confidence threshold is a magic number** at
   `pipeline.py:228`. All other thresholds (Plan 2 #8) were hoisted into
   `config.py` as `DEFAULT_*_THRESHOLD` constants. This one wasn't.
   Should be `DEFAULT_DISAMBIGUATOR_CONFIDENCE_THRESHOLD` in config.

4. **`DISAMBIGUATE_PROMPT_VERSION = "disambiguator/v1"`** is defined in
   `venue_disambiguator.py` but never persisted to the DB (unlike Stage
   A/B versions which land in `stage_*_prompt_version` columns). If you
   iterate the disambiguator prompt later, you won't be able to filter
   rows by version. Either drop the constant or add a column +
   migration.

All four are at-leisure polish, not blockers.
