-- 001_initial.sql — full schema per spec §5.2.
-- Most stage_*/venue_* columns are populated only by later plans;
-- they are nullable here so Plan 1's worker can insert minimal rows.

CREATE TABLE photo_analysis (
    immich_asset_id     TEXT PRIMARY KEY,
    first_seen_at       DATETIME NOT NULL,
    taken_at            DATETIME,
    latitude            REAL,
    longitude           REAL,
    uploader_user_id    TEXT,

    stage_a_is_food     INTEGER,                            -- BOOLEAN as 0/1
    stage_a_confidence  REAL,
    stage_a_model       TEXT,
    stage_a_ran_at      DATETIME,

    dish_name           TEXT,
    cuisine             TEXT,
    stage_b_confidence  REAL,
    stage_b_model       TEXT,
    stage_b_ran_at      DATETIME,
    stage_b_raw_json    TEXT,

    venue_type          TEXT,
    place_id            TEXT,
    place_match_source  TEXT,
    place_match_distance_m  REAL,

    review_status       TEXT NOT NULL DEFAULT 'auto',
    reviewed_at         DATETIME,
    review_notes        TEXT,

    last_error          TEXT,
    error_attempts      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_photo_taken_at ON photo_analysis(taken_at);
CREATE INDEX idx_photo_place    ON photo_analysis(place_id);
CREATE INDEX idx_photo_review   ON photo_analysis(review_status);

CREATE TABLE places (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    radius_m        INTEGER NOT NULL DEFAULT 50,
    google_place_id TEXT,
    address         TEXT,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    notes           TEXT
);
CREATE INDEX idx_places_type ON places(type);

CREATE TABLE worker_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       DATETIME NOT NULL,
    finished_at      DATETIME,
    assets_seen      INTEGER DEFAULT 0,
    assets_processed INTEGER DEFAULT 0,
    errors           INTEGER DEFAULT 0,
    notes            TEXT
);

CREATE TABLE worker_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
