-- ============================================================================
-- SOURCE PREPARATION - Grammy source database (PostgreSQL, database music_source)
--
-- Loading the provided the_grammy_awards.csv into this table creates the
-- operational SOURCE that the pipeline extracts from.
-- This is NOT the final ETL Load into the analytical Data Warehouse
-- (that happens in sql/dw_schema.sql / src/load.py).
--
-- Import (documented, reproducible):
--   docker compose exec airflow-scheduler python -m scripts.prepare_source_db
-- The script executes this file, loads the CSV with pandas, and reconciles
-- the row count against the source file (expected: 4810 rows).
-- ============================================================================
DROP TABLE IF EXISTS grammy_awards CASCADE;

CREATE TABLE grammy_awards (
    source_row_number BIGINT       PRIMARY KEY,
    year              SMALLINT     NOT NULL CHECK (year BETWEEN 1958 AND 2100),
    title             TEXT         NOT NULL,
    published_at      TEXT,
    updated_at        TEXT,
    category          TEXT         NOT NULL,
    nominee           TEXT,
    artist            TEXT,
    workers           TEXT,
    img               TEXT,
    winner            BOOLEAN      NOT NULL,
    loaded_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CHECK (category <> ''),
    CHECK (winner IN (TRUE, FALSE))
);

CREATE INDEX idx_grammy_awards_year     ON grammy_awards (year);
CREATE INDEX idx_grammy_awards_category ON grammy_awards (category);
CREATE INDEX idx_grammy_awards_artist   ON grammy_awards (artist);
