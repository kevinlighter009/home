# Plan 4 Follow-ups (from final review)

Plan 4 shipped. Final reviewer identified quality refactors worth folding
into Plan 5 or an early follow-up commit. None block shipping.

## Important

### 1. Generator-iteration boilerplate repeats 8 times
Every dashboard route uses:
```python
gen = deps.get_db(); conn = next(gen)
try: ...
finally:
    with contextlib.suppress(StopIteration):
        next(gen)
```
Across `routes/{map_view,place,feed,review,places_editor,status}.py`. Works but:
- DRY violation: 4-line ritual × 8 sites
- Not exception-safe in the throw-into-generator sense — fine today,
  footgun for any future transactional logic

**Fix shape:** add `DashboardDeps.db_conn() -> ContextManager[sqlite3.Connection]`
via `@contextmanager`; rewrite each route to use `with deps.db_conn() as conn:`.
Same length, no `next()` dance, exception-safe.

### 2. Dead method `DashboardDeps.get_immich`
`deps.py:36-43` defines `get_immich()` but `routes/proxy.py` constructs
`ImmichClient` inline. Either route the proxy through `get_immich()` or
delete the method.

### 3. `_VALID_TYPES` duplicated in 3 places
- `places_editor.py:17` (tuple)
- `places/cli.py:21` (tuple)
- `places/matcher.py:29` (set)

A divergence here silently breaks venue resolution.

**Fix shape:** define once in `places/types.py` as `VALID_VENUE_TYPES`,
import in all three call sites.

## Minor

4. Templates have lots of inline `style="…"` — should mostly live in `style.css`.
5. `/feed` venue dropdown hardcoded in `feed.html`, not derived from `_VALID_TYPES`.
6. `feed.py` uses f-string SQL with `# noqa: S608`. Could be branched
   to avoid the noqa.
7. `map.html` constructs popup HTML via string concatenation without
   HTML-escaping `m.dish` / `m.cuisine`. Single-user dashboard so low
   risk, but worth fixing.
8. `review.py` silently maps any `decision != "correct"` to `"confirmed"`.
   No validation. Add a check for `decision in {"confirm", "correct"}`.
9. `map.html` line 27 has a trailing `#` in `/place/${id}#` href —
   unnecessary noop anchor jump.
10. `main.py:13`: if `DASHBOARD_BIND=0.0.0.0` (no port), silently falls
    back to port 8000. Add a log line or validator.

## Plan 5 recommendation

Bundle items #1 (`db_conn` context manager), #2 (`get_immich` cleanup),
and #3 (centralize `_VALID_TYPES`) into Plan 5 Task 1 as quality cleanup
before launchd work. The rest are at-leisure polish.
