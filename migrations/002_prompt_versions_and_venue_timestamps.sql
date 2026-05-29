-- 002_prompt_versions_and_venue_timestamps.sql
-- Plan 2 follow-up #4: persist which prompt version produced each Stage A/B
-- result, so future prompt changes don't silently mix incompatible outputs.
-- Plan 2 follow-up #9: record when venue resolution was attempted, so the
-- worker can re-attempt venue matching after curated places change.

ALTER TABLE photo_analysis ADD COLUMN stage_a_prompt_version TEXT;
ALTER TABLE photo_analysis ADD COLUMN stage_b_prompt_version TEXT;
ALTER TABLE photo_analysis ADD COLUMN venue_resolved_at DATETIME;
