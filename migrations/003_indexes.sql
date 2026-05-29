-- 003_indexes.sql
-- Plan 3 follow-up #7: index on places.google_place_id for fast lookups
-- when re-caching or migrating Google results.
-- Plan 3 follow-up #9: index for filtering photo_analysis rows by
-- prompt version (used by future re-classification tooling).

CREATE INDEX IF NOT EXISTS idx_places_google_id
    ON places(google_place_id);

CREATE INDEX IF NOT EXISTS idx_photo_stage_a_version_ran_at
    ON photo_analysis(stage_a_prompt_version, stage_a_ran_at);
