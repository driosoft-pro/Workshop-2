"""Analytical contract: KPI queries, requirement tags and the dimensional DDL."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KPI_SQL = PROJECT_ROOT / "sql" / "kpi_queries.sql"
DW_SCHEMA = PROJECT_ROOT / "sql" / "dw_schema.sql"

DW_OBJECTS = [
    "dim_artist", "dim_genre", "dim_year", "dim_award_category",
    "fact_track_artist", "fact_grammy_award", "bridge_award_artist", "etl_batch_log",
]


def test_kpi_queries_with_requirement_tags():
    sql = KPI_SQL.read_text()
    lines = re.findall(r"^-- (R[1-4](?:/R[1-4])*)", sql, flags=re.MULTILINE)
    assert len(lines) == 14, lines
    covered = {tag for line in lines for tag in line.split("/")}
    assert covered == {"R1", "R2", "R3", "R4"}


def test_kpi_queries_are_named_and_commented():
    sql = KPI_SQL.read_text()
    names = re.findall(r"^--\s*@name:\s*([A-Za-z0-9_]+)\s*$", sql, flags=re.MULTILINE)
    assert len(names) == 14, names
    assert len(set(names)) == 14
    for name in names:
        assert name.startswith("kpi_"), name


def test_dw_schema_declares_all_objects():
    ddl = DW_SCHEMA.read_text()
    for object_name in DW_OBJECTS:
        assert re.search(rf"CREATE TABLE IF NOT EXISTS {object_name}\b", ddl), object_name


def test_business_keys_are_unique_constrained():
    ddl = DW_SCHEMA.read_text()
    for constraint in (
        "artist_bk            TEXT         NOT NULL UNIQUE",
        "genre      TEXT         NOT NULL UNIQUE",
        "year       INTEGER      NOT NULL UNIQUE",
        "category     TEXT         NOT NULL UNIQUE",
        "award_bk           TEXT         NOT NULL UNIQUE",
        "uq_track_artist ON fact_track_artist (track_id, genre_sk, artist_sk)",
    ):
        assert constraint in ddl, constraint


def test_fact_grain_matches_documented_grain():
    ddl = DW_SCHEMA.read_text()
    assert "uq_track_artist ON fact_track_artist (track_id, genre_sk, artist_sk)" in ddl
    assert "artist_sk" in ddl.split("CREATE TABLE IF NOT EXISTS fact_grammy_award", 1)[1]


def test_batch_log_has_before_after_counts():
    ddl = DW_SCHEMA.read_text()
    block = ddl.split("CREATE TABLE IF NOT EXISTS etl_batch_log", 1)[1]
    for column in ("batch_id", "started_at", "target_rows_after", "status"):
        assert column in block, column


def _table_block(ddl: str, table: str) -> str:
    return ddl.split(f"CREATE TABLE IF NOT EXISTS {table}", 1)[1].split(");", 1)[0]


REMOVED_COLUMNS = {
    "dim_artist": ["from_grammy", "grammy_award_count_core"],
    "fact_track_artist": [
        "track_name", "album_name", "duration_ms", "explicit", "liveness", "loudness",
        "tempo", "artist_position", "artist_total", "artist_grammy_awards", "track_genre",
        "is_outlier_duration", "is_outlier_loudness", "is_outlier_tempo",
    ],
    "fact_grammy_award": [
        "winner ", "artist_source", "is_aggregate_credit", "credit_artist_count",
        "spotify_track_count", "award_count",
    ],
}


def test_slim_model_has_no_unused_columns_and_no_views():
    ddl = DW_SCHEMA.read_text()
    for table, columns in REMOVED_COLUMNS.items():
        block = _table_block(ddl, table)
        for column in columns:
            assert column not in block, (table, column)
    assert "CREATE VIEW" not in ddl


def test_every_column_dropped_from_old_databases_is_declared():
    ddl = DW_SCHEMA.read_text()
    for table, columns in REMOVED_COLUMNS.items():
        for column in columns:
            assert f"{table}" in ddl and f"DROP COLUMN IF EXISTS {column.strip()}" in ddl, column
