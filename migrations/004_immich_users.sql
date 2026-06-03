-- 004_immich_users.sql
-- Stores Immich user metadata discovered by the worker at startup.
-- Enables per-user processing cursors and dashboard user filtering.

CREATE TABLE IF NOT EXISTS immich_users (
    user_id      TEXT PRIMARY KEY,
    username     TEXT NOT NULL,
    display_name TEXT,
    updated_at   DATETIME NOT NULL
);

-- Index photo_analysis by uploader for per-user dashboard queries.
CREATE INDEX IF NOT EXISTS idx_photo_uploader
    ON photo_analysis(uploader_user_id);
