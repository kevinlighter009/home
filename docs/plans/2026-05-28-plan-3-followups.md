# Plan 3 Follow-ups (from final review)

Plan 3 shipped. The final reviewer surfaced items worth addressing in Plan 4
or as standalone cleanups.

## Important

### 1. Stage B doesn't see Google Places candidates
Spec §4.3 step 2 says Google candidates should be passed into Stage B's
prompt so the LLM can pick using visual context (signage, decor, dish
style). The current matcher (`matcher.py:75-94`) just picks nearest by
haversine and caches that, skipping the LLM tiebreaker entirely.

In practice this means: a photo near multiple restaurants always resolves
to the geometrically-closest one, even if the photo clearly shows another
venue's signage.

**Fix shape:** when the matcher gets multiple Google candidates AND has
access to a vision provider, pass them as `nearby_places` into a small
follow-up Stage B prompt. Cap the candidate list to N=5 by distance.
Either: (a) split Stage B into B1=dish+cuisine and B2=venue picker, or
(b) extend Stage B's prompt and schema to optionally include venue.

Defer to Plan 4 or its own mini-plan — not a Plan 3 blocker.

### 2. Cached `gplaces:*` rows hardcode `type="restaurant"`
`matcher.py:85` discards the Google `types` tuple and labels every cached
result as `type="restaurant"`. Spec §4.3 includes `cafe`, `bakery`, `bar`,
`meal_takeaway` in the search. A Starbucks ends up labeled "restaurant"
in the cache.

**Fix shape:** map the first matching Google type to one of our canonical
buckets (e.g., a `_GOOGLE_TYPE_TO_VENUE` dict). Or just preserve the
raw Google types in `notes` for now and let Plan 4's UI render them.

### 3. `outdoor` venue_type defined in spec but never emitted
Spec §5.2 lists `outdoor` as a valid `venue_type`, but neither the matcher
(`_CURATED_VENUE_TYPES`) nor the CLI (`_VALID_TYPES`) accept it. A user
who wants to tag a picnic spot can't.

**Fix shape:** add `outdoor` to both `_VALID_TYPES` (CLI) and
`_CURATED_VENUE_TYPES` (matcher passthrough). One-line change in each.

## Minor

4. **`_record_venue_match` may overwrite Stage B's `review_notes`** when
   the match is ambiguous. Probably acceptable (venue ambiguity is more
   actionable than confidence ambiguity), but worth a comment.
5. **`matcher.py` swallows place-cache insert errors** via
   `contextlib.suppress(Exception)`. Reasonable defensively, but a
   `log.warning` would help debugging.
6. **`smoke_places` returns 0 even on zero results.** Add a `--strict`
   flag for CI verification.
7. **No index on `places.google_place_id`** — fine for <100 rows but
   trivial to add when the cache grows.
8. **Cached `gplaces:*` `radius_m` uses `ambiguous_threshold_m` (50m
   default).** Correct choice but not obvious — add a one-line comment
   explaining why we use the tight radius for cache hits.
9. **Per-asset prompt versions are written but no `006_index_*` migration
   exists to query by them.** If we ever need "find all photos
   classified by stage_a/v1", an index on `(stage_a_prompt_version,
   stage_a_ran_at)` would help.

## Recommendation for Plan 4 (Dashboard)

Plan 4's dashboard will visualize Plan 3's data. Bundle:
- Items #2, #3 into Plan 4's first task (cleanup before UI work) — the
  type accuracy directly affects what users see.
- Item #1 (Stage B candidate prompting) deserves its own mini-plan after
  Plan 4; it changes pipeline semantics non-trivially.
- Items #4-9 are at-leisure polish.

The dashboard itself has clean data to work with: `venue_columns are populated,
the `places` table is unified, and the `id` prefix convention makes
curated-vs-cached trivially distinguishable in the UI.
