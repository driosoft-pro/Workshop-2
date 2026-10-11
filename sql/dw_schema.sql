-- ============================================================================
-- ANALYTICAL DATA WAREHOUSE - dimensional star schema (PostgreSQL, music_dw)
--
-- Business process : commercial performance of Spotify track listings and the
--                    Grammy Award recognition obtained by their artists.
-- Fact grain       : fact_track_artist  -> one row per Spotify track listing
--                                            (track_id x track_genre) and one
--                                            performing artist.
--                    fact_grammy_award  -> one row per Grammy award record in
--                                            the source file (year x category
--                                            x nominee x artist).
-- Conformed dims   : dim_artist, dim_year are shared by both facts.
--
-- Load strategy    : controlled replace (transactional delete + insert) with
--                    business-key uniqueness constraints as a backstop, which
--                    makes reruns idempotent. See docs/dimensional_model.md.
-- ============================================================================

CREATE TABLE IF NOT EXISTS dim_artist (
    artist_sk            BIGSERIAL    PRIMARY KEY,
    artist_bk            TEXT         NOT NULL UNIQUE,
    artist_display_name  TEXT         NOT NULL,
    from_spotify         BOOLEAN      NOT NULL DEFAULT FALSE,
    grammy_award_count   INTEGER      NOT NULL DEFAULT 0,
    spotify_track_count  INTEGER      NOT NULL DEFAULT 0,
    dominant_genre       TEXT,
    dominant_genre_family TEXT,
    n_genres             INTEGER,
    genre_tie            BOOLEAN,
    loaded_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_genre (
    genre_sk      BIGSERIAL    PRIMARY KEY,
    genre      TEXT         NOT NULL UNIQUE,
    genre_family  TEXT,
    loaded_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_year (
    year_sk    INTEGER      PRIMARY KEY,
    year       INTEGER      NOT NULL UNIQUE,
    decade     INTEGER      NOT NULL,
    loaded_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_award_category (
    category_sk      BIGSERIAL    PRIMARY KEY,
    category     TEXT         NOT NULL UNIQUE,
    category_clean   TEXT,
    category_family  TEXT,
    loaded_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_track_artist (
    track_artist_sk      BIGSERIAL    PRIMARY KEY,
    track_id             TEXT         NOT NULL,
    artist_sk            BIGINT       NOT NULL REFERENCES dim_artist (artist_sk),
    genre_sk             BIGINT       NOT NULL REFERENCES dim_genre (genre_sk),
    popularity           INTEGER      NOT NULL,
    danceability         DOUBLE PRECISION,
    energy               DOUBLE PRECISION,
    valence              DOUBLE PRECISION,
    acousticness         DOUBLE PRECISION,
    speechiness          DOUBLE PRECISION,
    is_grammy_artist     SMALLINT     NOT NULL CHECK (is_grammy_artist IN (0, 1)),
    is_grammy_artist_strict SMALLINT  NOT NULL DEFAULT 0 CHECK (is_grammy_artist_strict IN (0, 1)),
    song_key             TEXT,
    is_zero_popularity   SMALLINT     NOT NULL DEFAULT 0 CHECK (is_zero_popularity IN (0, 1)),
    is_primary_song      SMALLINT     NOT NULL DEFAULT 0 CHECK (is_primary_song IN (0, 1)),
    batch_id             TEXT         NOT NULL,
    loaded_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Grain key: one row per track x genre x performing artist
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_artist ON fact_track_artist (track_id, genre_sk, artist_sk);

CREATE INDEX IF NOT EXISTS idx_track_artist_artist  ON fact_track_artist (artist_sk);
CREATE INDEX IF NOT EXISTS idx_track_artist_genre   ON fact_track_artist (genre_sk);
CREATE INDEX IF NOT EXISTS idx_track_artist_grammy  ON fact_track_artist (is_grammy_artist);
CREATE INDEX IF NOT EXISTS idx_track_artist_batch   ON fact_track_artist (batch_id);

CREATE TABLE IF NOT EXISTS fact_grammy_award (
    grammy_award_sk    BIGSERIAL    PRIMARY KEY,
    award_bk           TEXT         NOT NULL UNIQUE,
    artist_sk          BIGINT       REFERENCES dim_artist (artist_sk),
    year_sk            INTEGER      NOT NULL REFERENCES dim_year (year_sk),
    category_sk        BIGINT       NOT NULL REFERENCES dim_award_category (category_sk),
    title              TEXT,
    nominee            TEXT,
    artist_credit       TEXT,
    workers            TEXT,
    winner_flag        SMALLINT     NOT NULL CHECK (winner_flag IN (0, 1)),
    is_matched_spotify SMALLINT     NOT NULL CHECK (is_matched_spotify IN (0, 1)),
    is_matched_strict  SMALLINT     NOT NULL DEFAULT 0 CHECK (is_matched_strict IN (0, 1)),
    is_song_confirmed  SMALLINT     NOT NULL DEFAULT 0 CHECK (is_song_confirmed IN (0, 1)),
    match_method       TEXT,
    recognition_tier   TEXT         NOT NULL DEFAULT 'none',
    batch_id           TEXT         NOT NULL,
    loaded_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Collaborative Grammy credit -> Spotify artists bridge.
-- One row per matched artist of an award credit (T12). The fact keeps only
-- the first matched artist in artist_sk so the award grain never changes.
CREATE TABLE IF NOT EXISTS bridge_award_artist (
    grammy_award_sk  BIGINT  NOT NULL REFERENCES fact_grammy_award (grammy_award_sk) ON DELETE CASCADE,
    artist_sk        BIGINT  NOT NULL REFERENCES dim_artist (artist_sk),
    artist_position  INTEGER NOT NULL,
    match_method     TEXT    NOT NULL,
    recognition_tier TEXT    NOT NULL DEFAULT 'none',
    batch_id         TEXT    NOT NULL DEFAULT '',
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (grammy_award_sk, artist_sk)
);

CREATE INDEX IF NOT EXISTS idx_bridge_artist      ON bridge_award_artist (artist_sk);
CREATE INDEX IF NOT EXISTS idx_bridge_method       ON bridge_award_artist (match_method);

CREATE INDEX IF NOT EXISTS idx_grammy_fact_artist    ON fact_grammy_award (artist_sk);
CREATE INDEX IF NOT EXISTS idx_grammy_fact_year      ON fact_grammy_award (year_sk);
CREATE INDEX IF NOT EXISTS idx_grammy_fact_category  ON fact_grammy_award (category_sk);
CREATE INDEX IF NOT EXISTS idx_grammy_fact_matched   ON fact_grammy_award (is_matched_spotify);
CREATE INDEX IF NOT EXISTS idx_grammy_fact_batch     ON fact_grammy_award (batch_id);

CREATE TABLE IF NOT EXISTS etl_batch_log (
    batch_id            TEXT         PRIMARY KEY,
    dag_id              TEXT         NOT NULL,
    run_id              TEXT         NOT NULL,
    strategy            TEXT         NOT NULL,
    target_rows_before  JSONB        NOT NULL,
    target_rows_after   JSONB        NOT NULL,
    status              TEXT         NOT NULL,
    started_at          TIMESTAMPTZ  NOT NULL,
    finished_at         TIMESTAMPTZ  NOT NULL,
    notes               TEXT
);

-- ---------------------------------------------------------------------------
-- In-place upgrade of databases created with the previous (wider) schema.
-- CREATE TABLE IF NOT EXISTS never alters an existing table, so the columns that
-- the model audit removed (docs/dimensional_model.md section 9) are dropped here.
-- No-op on a fresh database. Dropping track_genre also drops the old unique key.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS vw_fact_track_artist;
DROP VIEW IF EXISTS vw_fact_grammy_award;
ALTER TABLE dim_artist         DROP COLUMN IF EXISTS from_grammy;
ALTER TABLE dim_artist         DROP COLUMN IF EXISTS grammy_award_count_core;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS track_name;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS album_name;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS duration_ms;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS duration_min;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS explicit;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS liveness;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS loudness;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS tempo;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS artist_position;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS artist_total;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS artist_grammy_awards;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS is_outlier_duration;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS is_outlier_loudness;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS is_outlier_tempo;
ALTER TABLE fact_track_artist  DROP COLUMN IF EXISTS track_genre;
ALTER TABLE fact_grammy_award  DROP COLUMN IF EXISTS winner;
ALTER TABLE fact_grammy_award  DROP COLUMN IF EXISTS artist_source;
ALTER TABLE fact_grammy_award  DROP COLUMN IF EXISTS is_aggregate_credit;
ALTER TABLE fact_grammy_award  DROP COLUMN IF EXISTS credit_artist_count;
ALTER TABLE fact_grammy_award  DROP COLUMN IF EXISTS spotify_track_count;
ALTER TABLE fact_grammy_award  DROP COLUMN IF EXISTS award_count;
