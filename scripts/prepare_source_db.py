"""Source preparation for the Grammy relational source.

Loads the provided the_grammy_awards.csv into the PostgreSQL source database
(table ``grammy_awards`` in ``music_source``). This creates the operational
source the pipeline extracts from (Workshop-2, section 6.2). It is NOT the
final ETL Load into the analytical Data Warehouse.

Usage:
    docker compose exec airflow-scheduler python -m scripts.prepare_source_db
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src import config

EXPECTED_SOURCE_ROWS = 4810


def prepare_source_db(csv_path=None, ddl_path=None) -> dict:
    csv_path = Path(csv_path) if csv_path else config.GRAMMY_SOURCE_PATH
    ddl_path = Path(ddl_path) if ddl_path else config.SQL_DIR / "source_setup.sql"

    frame = config.read_csv(csv_path, dtype={"winner": "string"})
    source_rows = len(frame)

    frame = frame.reset_index(drop=True)
    frame.insert(0, "source_row_number", (frame.index + 1).astype("int64"))
    frame["year"] = frame["year"].astype("int16")

    def _parse_winner(value):
        if value is None or pd.isna(value) or str(value).strip() == "":
            return None
        return str(value).strip().lower() == "true"

    frame["winner"] = frame["winner"].map(_parse_winner)
    if frame["winner"].isna().any():
        raise RuntimeError("winner column contains values that are not boolean literals")

    engine = create_engine(config.SOURCE_DB_URL)
    ddl = ddl_path.read_text()
    with engine.begin() as connection:
        for statement in [item.strip() for item in ddl.split(";") if item.strip()]:
            connection.execute(text(statement))
        frame.to_sql(config.GRAMMY_SOURCE_TABLE, connection, if_exists="append", index=False)

    with engine.connect() as connection:
        db_rows = int(
            connection.execute(
                text(f"SELECT count(*) FROM {config.GRAMMY_SOURCE_TABLE}")
            ).scalar_one()
        )
        min_year = int(
            connection.execute(
                text(f"SELECT min(year) FROM {config.GRAMMY_SOURCE_TABLE}")
            ).scalar_one()
        )
        max_year = int(
            connection.execute(
                text(f"SELECT max(year) FROM {config.GRAMMY_SOURCE_TABLE}")
            ).scalar_one()
        )
        distinct_winners = int(
            connection.execute(
                text(f"SELECT count(DISTINCT winner) FROM {config.GRAMMY_SOURCE_TABLE}")
            ).scalar_one()
        )
    engine.dispose()

    reconciliation = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(csv_path),
        "source_rows_in_csv": source_rows,
        "rows_loaded": db_rows,
        "row_count_matches": db_rows == source_rows,
        "year_range": [min_year, max_year],
        "distinct_winner_values": distinct_winners,
        "table": config.GRAMMY_SOURCE_TABLE,
        "database": config.SOURCE_DB_URL.rsplit("/", 1)[-1],
        "ddl": str(ddl_path),
    }
    if db_rows != source_rows:
        raise RuntimeError(
            f"Row-count reconciliation failed: csv={source_rows} db={db_rows}"
        )
    if source_rows != EXPECTED_SOURCE_ROWS:
        print(
            f"[prepare_source_db] WARNING: expected {EXPECTED_SOURCE_ROWS} rows, "
            f"observed {source_rows}"
        )

    evidence_path = config.RUNS_EVIDENCE_DIR / "source_preparation.json"
    evidence_path.write_text(json.dumps(reconciliation, indent=2))
    print(f"[prepare_source_db] {json.dumps(reconciliation, indent=2)}")
    return reconciliation


def main() -> int:
    config.ensure_directories()
    prepare_source_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
