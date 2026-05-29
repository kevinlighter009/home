-- 003_indexes.sql
-- Plan 3 follow-up #7: index on places.google_place_id for fast lookups
-- when re-caching or migrating Google results.
-- Plan 3 follow-up #9: index for filtering photo_analysis rows by
-- prompt version (used by future re-classification tooling).

CREATE INDEX IF NOT EXISTS idx_places_google_id
    ON places(google_place_id);

CREATE INDEX IF NOT EXISTS idx_photo_stage_a_version_ran_at
    ON photo_analysis(stage_a_prompt_version, stage_a_ran_at);

-- Documentation note (no schema change):
-- `photo_analysis.stage_b_raw_json` is a NORMALIZED re-serialization of the
-- LLM's parsed output (via `json.dumps(parsed, sort_keys=True)`), not the
-- model's literal output bytes. The Anthropic SDK returns parsed tool-use
-- input, not a raw text payload, so there is no "original" string to record.
-- This comment serves as the canonical documentation; renaming the column
-- would force a destructive migration on existing rows.
