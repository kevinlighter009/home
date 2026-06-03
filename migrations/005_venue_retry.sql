-- Migration 005: venue_retry_after column
--
-- Tracks when a photo's venue resolution should next be attempted.
-- NULL  → eligible immediately (includes all existing 'unknown' rows —
--          they failed only because no Google key was configured).
-- DATE  → retry on or after this date (set to 1st of next month after
--          a genuine Google miss, so new venues have time to appear).
--
-- The budget gate writes this when Google returns no candidates or the
-- monthly cap is exhausted.  The venue backfill query filters on it so
-- the same photo is never retried more than once per month.

ALTER TABLE photo_analysis ADD COLUMN venue_retry_after DATETIME;
CREATE INDEX IF NOT EXISTS idx_photo_venue_retry
    ON photo_analysis(venue_retry_after);
