"""Integration tests against the analytical Data Warehouse (music_dw).

Run with the stack up:  pytest -m integration
Auto-skipped when PostgreSQL is unreachable.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from src import config
from tests.conftest import dw_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not dw_available(), reason="music_dw unreachable (run.sh up)"),
]

DW_TABLES = [
    "dim_artist", "dim_genre", "dim_year", "dim_award_category",
    "fact_track_artist", "fact_grammy_award", "bridge_award_artist", "etl_batch_log",
]


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(config.DW_DB_URL)
    yield engine
    engine.dispose()


def _count(engine, table: str) -> int:
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def test_dw_objects_exist(engine):
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )).scalars().all()
    for table in DW_TABLES:
        assert table in rows, table


def test_documented_row_counts_after_a_full_load(engine):
    expected = {
        "fact_track_artist": 157_530,
        "fact_grammy_award": 4_810,
        "dim_artist": 30_989,
        "dim_genre": 114,
        "dim_year": 62,
        "dim_award_category": 638,
        "bridge_award_artist": 2_841,
    }
    actual = {table: _count(engine, table) for table in expected}
    if any(count == 0 for count in actual.values()):
        pytest.skip(f"DW not loaded yet: {actual} - trigger the DAG first")
    assert actual == expected


def test_etl_batch_log_records_committed_batches(engine):
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT batch_id, status, target_rows_after FROM etl_batch_log "
            "ORDER BY started_at DESC"
        )).fetchall()
    if not rows:
        pytest.skip("no batch logged yet - trigger the DAG first")
    assert all(row.status == "success" for row in rows)
    assert all("fact_track_artist" in row.target_rows_after for row in rows)
    assert "bridge_award_artist" in rows[0].target_rows_after


def test_surrogate_keys_are_unique_and_awards_may_be_unmatched(engine):
    with engine.connect() as connection:
        artist_sk = connection.execute(text(
            "SELECT COUNT(*) FROM (SELECT artist_sk FROM dim_artist GROUP BY artist_sk "
            "HAVING COUNT(*) > 1) duplicated"
        )).scalar()
        null_sk = connection.execute(text(
            "SELECT COUNT(*) FROM fact_grammy_award WHERE artist_sk IS NULL"
        )).scalar()
        total = connection.execute(text("SELECT COUNT(*) FROM fact_grammy_award")).scalar()
    assert artist_sk == 0
    assert null_sk > 0  # unmatched awards keep artist_sk NULL by design
    assert null_sk < total
