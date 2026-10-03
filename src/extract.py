"""Source extraction for the two pipeline branches.

Spotify  : CSV file (documented project path data/raw/).
Grammy   : PostgreSQL source database table ``grammy_awards`` (source
           preparation import performed by scripts/prepare_source_db.py).

Extraction performs projection and source-contract verification only.
No cleaning happens here: source-quality problems must remain visible to the
raw validation gate (Workshop-2, section 6.7).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src import config


class SourceContractError(RuntimeError):
    """Raised when the source does not expose the attributes the pipeline needs."""


def _verify_columns(frame: pd.DataFrame, required: list[str], source: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SourceContractError(
            f"Source contract violated for {source}: missing columns {missing}. "
            "Retrying cannot repair a missing column; fix the source contract."
        )


def extract_spotify(
    source_path: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    config.ensure_directories()
    source_path = Path(source_path or config.SPOTIFY_SOURCE_PATH)
    output_path = Path(output_path or config.SPOTIFY_RAW_PATH)

    if not source_path.exists():
        raise FileNotFoundError(f"Spotify source file not found: {source_path}")

    frame = config.read_csv(source_path)
    _verify_columns(frame, config.SPOTIFY_REQUIRED_COLUMNS, f"Spotify CSV {source_path.name}")

    raw = frame[config.SPOTIFY_REQUIRED_COLUMNS].copy()
    raw.to_csv(output_path, index=False)

    metadata = {
        "source": str(source_path),
        "raw_path": str(output_path),
        "rows": int(len(raw)),
        "columns": list(raw.columns),
        "source_filename": source_path.name,
    }
    print(f"[extract_spotify] {metadata}")
    return metadata


def extract_grammys(
    output_path: Path | None = None,
    db_url: str | None = None,
    table: str | None = None,
) -> dict:
    config.ensure_directories()
    output_path = Path(output_path or config.GRAMMY_RAW_PATH)
    db_url = db_url or config.SOURCE_DB_URL
    table = table or config.GRAMMY_SOURCE_TABLE

    engine = create_engine(db_url)
    columns_sql = ", ".join(config.GRAMMY_REQUIRED_COLUMNS)
    with engine.connect() as connection:
        result = connection.execute(
            text(f"SELECT {columns_sql} FROM {table} ORDER BY year, category, nominee")
        )
        frame = pd.DataFrame(result.fetchall(), columns=result.keys())
    engine.dispose()

    _verify_columns(frame, config.GRAMMY_REQUIRED_COLUMNS, f"PostgreSQL table {table}")

    raw = frame.copy()
    raw["winner"] = raw["winner"].astype("boolean")
    raw.to_csv(output_path, index=False)

    metadata = {
        "source": f"postgresql+table={table}",
        "raw_path": str(output_path),
        "rows": int(len(raw)),
        "columns": list(raw.columns),
    }
    print(f"[extract_grammys] {metadata}")
    return metadata
