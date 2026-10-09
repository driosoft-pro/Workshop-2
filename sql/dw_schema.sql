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
    from_grammy          BOOLEAN      NOT NULL DEFAULT FALSE,
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
    track_genre          TEXT         NOT NULL,
    artist_sk            BIGINT       NOT NULL REFERENCES dim_artist (artist_sk),
    genre_sk             BIGINT       NOT NULL REFERENCES dim_genre (genre_sk),
    track_name           TEXT,
    album_name           TEXT,
    popularity           INTEGER      NOT NULL,
    duration_ms          BIGINT       NOT NULL,
    duration_min         DOUBLE PRECISION,
    explicit             BOOLEAN      NOT NULL,
    danceability         DOUBLE PRECISION,
    energy               DOUBLE PRECISION,
    valence              DOUBLE PRECISION,
    acousticness         DOUBLE PRECISION,
    speechiness          DOUBLE PRECISION,
    liveness             DOUBLE PRECISION,
    loudness             DOUBLE PRECISION,
    tempo                DOUBLE PRECISION,
    artist_position      INTEGER      NOT NULL,
    artist_total         INTEGER      NOT NULL,
    is_grammy_artist     SMALLINT     NOT NULL CHECK (is_grammy_artist IN (0, 1)),
    artist_grammy_awards INTEGER      NOT NULL DEFAULT 0,
    song_key             TEXT,
    is_zero_popularity   SMALLINT     NOT NULL DEFAULT 0 CHECK (is_zero_popularity IN (0, 1)),
    is_outlier_duration  SMALLINT     NOT NULL DEFAULT 0 CHECK (is_outlier_duration IN (0, 1)),
    is_outlier_loudness  SMALLINT     NOT NULL DEFAULT 0 CHECK (is_outlier_loudness IN (0, 1)),
    is_outlier_tempo     SMALLINT     NOT NULL DEFAULT 0 CHECK (is_outlier_tempo IN (0, 1)),
    is_primary_song      SMALLINT     NOT NULL DEFAULT 0 CHECK (is_primary_song IN (0, 1)),
    batch_id             TEXT         NOT NULL,
    loaded_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (track_id, track_genre, artist_sk)
);

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
    winner             BOOLEAN      NOT NULL,
    winner_flag        SMALLINT     NOT NULL CHECK (winner_flag IN (0, 1)),
    is_matched_spotify SMALLINT     NOT NULL CHECK (is_matched_spotify IN (0, 1)),
    is_matched_strict  SMALLINT     NOT NULL DEFAULT 0 CHECK (is_matched_strict IN (0, 1)),
    is_song_confirmed  SMALLINT     NOT NULL DEFAULT 0 CHECK (is_song_confirmed IN (0, 1)),
    artist_source      TEXT,
    match_method       TEXT,
    credit_artist_count INTEGER     NOT NULL DEFAULT 0,
    spotify_track_count INTEGER      NOT NULL DEFAULT 0,
    award_count        SMALLINT     NOT NULL DEFAULT 1,
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
    batch_id         TEXT    NOT NULL DEFAULT '',
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (grammy_award_sk, artist_sk)
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
-- Idempotent upgrade for databases created before the T12-T16 extension.
-- CREATE TABLE IF NOT EXISTS cannot add columns to an existing table, so the
-- new attributes are declared here as well (no-op when they already exist).
-- ---------------------------------------------------------------------------
ALTER TABLE dim_artist          ADD COLUMN IF NOT EXISTS dominant_genre        TEXT;
ALTER TABLE dim_artist          ADD COLUMN IF NOT EXISTS dominant_genre_family TEXT;
ALTER TABLE dim_artist          ADD COLUMN IF NOT EXISTS n_genres              INTEGER;
ALTER TABLE dim_artist          ADD COLUMN IF NOT EXISTS genre_tie             BOOLEAN;
ALTER TABLE dim_genre           ADD COLUMN IF NOT EXISTS genre_family          TEXT;
ALTER TABLE dim_award_category  ADD COLUMN IF NOT EXISTS category_clean        TEXT;
ALTER TABLE dim_award_category  ADD COLUMN IF NOT EXISTS category_family       TEXT;
ALTER TABLE fact_track_artist   ADD COLUMN IF NOT EXISTS song_key              TEXT;
ALTER TABLE fact_track_artist   ADD COLUMN IF NOT EXISTS is_zero_popularity    SMALLINT DEFAULT 0;
ALTER TABLE fact_track_artist   ADD COLUMN IF NOT EXISTS is_outlier_duration   SMALLINT DEFAULT 0;
ALTER TABLE fact_track_artist   ADD COLUMN IF NOT EXISTS is_outlier_loudness   SMALLINT DEFAULT 0;
ALTER TABLE fact_track_artist   ADD COLUMN IF NOT EXISTS is_outlier_tempo      SMALLINT DEFAULT 0;
ALTER TABLE fact_track_artist   ADD COLUMN IF NOT EXISTS is_primary_song       SMALLINT DEFAULT 0;
ALTER TABLE fact_grammy_award   ADD COLUMN IF NOT EXISTS artist_source         TEXT;
ALTER TABLE fact_grammy_award   ADD COLUMN IF NOT EXISTS match_method          TEXT;
ALTER TABLE fact_grammy_award   ADD COLUMN IF NOT EXISTS credit_artist_count   INTEGER DEFAULT 0;
ALTER TABLE fact_grammy_award   ADD COLUMN IF NOT EXISTS is_matched_strict     SMALLINT DEFAULT 0;
ALTER TABLE fact_grammy_award   ADD COLUMN IF NOT EXISTS is_song_confirmed     SMALLINT DEFAULT 0;
