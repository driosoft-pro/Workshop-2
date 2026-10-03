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
    loaded_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_genre (
    genre_sk   BIGSERIAL    PRIMARY KEY,
    genre      TEXT         NOT NULL UNIQUE,
    loaded_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_year (
    year_sk    INTEGER      PRIMARY KEY,
    year       INTEGER      NOT NULL UNIQUE,
    decade     INTEGER      NOT NULL,
    loaded_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_award_category (
    category_sk  BIGSERIAL    PRIMARY KEY,
    category     TEXT         NOT NULL UNIQUE,
    loaded_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
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
    spotify_track_count INTEGER      NOT NULL DEFAULT 0,
    award_count        SMALLINT     NOT NULL DEFAULT 1,
    batch_id           TEXT         NOT NULL,
    loaded_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

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
