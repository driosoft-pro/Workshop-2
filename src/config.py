"""Central configuration for the Workshop-2 reliable music pipeline.

All paths and connections are resolved from environment variables so the same
code runs inside the Airflow containers (/opt/airflow/...) and on a developer
host (repository layout). See .env.example for the documented variables.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _default_data_dir() -> Path:
    container_path = Path("/opt/airflow/data")
    if container_path.exists():
        return container_path
    return PROJECT_ROOT / "data"


DATA_DIR = _env_path("MUSIC_DATA_DIR", _default_data_dir())
RAW_DIR = DATA_DIR / "raw"
WORK_DIR = DATA_DIR / "work"
OUTPUT_DIR = DATA_DIR / "output"
BAD_DIR = DATA_DIR / "bad"

GX_DIR = _env_path(
    "MUSIC_GX_DIR",
    Path("/opt/airflow/gx") if Path("/opt/airflow/gx").exists() else PROJECT_ROOT / "gx",
)
GX_PROJECT_ROOT = GX_DIR.parent

EVIDENCE_DIR = _env_path(
    "MUSIC_EVIDENCE_DIR",
    Path("/opt/airflow/docs/evidence")
    if Path("/opt/airflow/docs/evidence").exists()
    else PROJECT_ROOT / "docs" / "evidence",
)
GX_RESULTS_DIR = EVIDENCE_DIR / "gx"
KPI_RESULTS_DIR = EVIDENCE_DIR / "kpis"
RUNS_EVIDENCE_DIR = EVIDENCE_DIR / "runs"

SQL_DIR = PROJECT_ROOT / "sql" if (PROJECT_ROOT / "sql").exists() else Path("/opt/airflow/sql")

SPOTIFY_SOURCE_FILENAME = os.environ.get("SPOTIFY_SOURCE_FILENAME", "spotify_dataset.csv")
GRAMMY_SOURCE_FILENAME = os.environ.get("GRAMMY_SOURCE_FILENAME", "the_grammy_awards.csv")

def _resolve_source(filename: str) -> Path:
    """Locate a source file in data/raw, falling back to data/bad (Test B)."""
    for base in (RAW_DIR, BAD_DIR):
        candidate = base / filename
        if candidate.exists():
            return candidate
    return RAW_DIR / filename


def resolve_source(filename: str) -> Path:
    """Public helper used by the DAG to honour a dag_run.conf source override."""
    return _resolve_source(filename)


SPOTIFY_SOURCE_PATH = _resolve_source(SPOTIFY_SOURCE_FILENAME)
GRAMMY_SOURCE_PATH = _resolve_source(GRAMMY_SOURCE_FILENAME)

SOURCE_DB_URL = os.environ.get(
    "MUSIC_SOURCE_DB_URL",
    "postgresql+psycopg2://music:music@localhost:5432/music_source",
)
DW_DB_URL = os.environ.get(
    "MUSIC_DW_DB_URL",
    "postgresql+psycopg2://music:music@localhost:5432/music_dw",
)

DW_LOAD_STRATEGY = os.environ.get("DW_LOAD_STRATEGY", "replace")

GRAMMY_SOURCE_TABLE = "grammy_awards"

SPOTIFY_REQUIRED_COLUMNS = [
    "track_id",
    "artists",
    "album_name",
    "track_name",
    "popularity",
    "duration_ms",
    "explicit",
    "danceability",
    "energy",
    "valence",
    "acousticness",
    "speechiness",
    "liveness",
    "loudness",
    "tempo",
    "track_genre",
]

GRAMMY_REQUIRED_COLUMNS = [
    "year",
    "title",
    "published_at",
    "updated_at",
    "category",
    "nominee",
    "artist",
    "workers",
    "winner",
]

SPOTIFY_RAW_PATH = WORK_DIR / "spotify_raw.csv"
GRAMMY_RAW_PATH = WORK_DIR / "grammys_raw.csv"
PREPARED_TRACKS_PATH = WORK_DIR / "prepared_tracks.csv"
PREPARED_GRAMMYS_PATH = WORK_DIR / "prepared_grammys.csv"
PREPARED_METRICS_PATH = WORK_DIR / "prepared_metrics.csv"
TRANSFORM_SUMMARY_PATH = WORK_DIR / "transform_summary.json"

ARTIST_DIM_PATH = OUTPUT_DIR / "dim_artist.csv"
GENRE_DIM_PATH = OUTPUT_DIR / "dim_genre.csv"
YEAR_DIM_PATH = OUTPUT_DIR / "dim_year.csv"
CATEGORY_DIM_PATH = OUTPUT_DIR / "dim_award_category.csv"
TRACK_FACT_PATH = OUTPUT_DIR / "fact_track_artist.csv"
GRAMMY_FACT_PATH = OUTPUT_DIR / "fact_grammy_award.csv"
LOAD_SUMMARY_PATH = OUTPUT_DIR / "load_summary.json"


def read_csv(path, **kwargs):
    """Read a pipeline CSV using the project's NA policy.

    Only empty fields are treated as missing. Literal source tokens such as
    ``N/A`` (an actual artist name in the Spotify file) stay text, so no source
    value is silently converted into a null.
    """
    import pandas as pd

    kwargs.setdefault("keep_default_na", False)
    kwargs.setdefault("na_values", [""])
    return pd.read_csv(path, **kwargs)


def ensure_directories() -> None:
    for path in (WORK_DIR, OUTPUT_DIR, BAD_DIR, GX_RESULTS_DIR, KPI_RESULTS_DIR, RUNS_EVIDENCE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def describe() -> dict[str, str]:
    return {
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(DATA_DIR),
        "gx_dir": str(GX_DIR),
        "evidence_dir": str(EVIDENCE_DIR),
        "source_db_url": _safe_url(SOURCE_DB_URL),
        "dw_db_url": _safe_url(DW_DB_URL),
        "spotify_source_file": SPOTIFY_SOURCE_FILENAME,
        "grammy_source_file": GRAMMY_SOURCE_FILENAME,
        "dw_load_strategy": DW_LOAD_STRATEGY,
    }


def _safe_url(url: str) -> str:
    if "@" in url and "//" in url:
        prefix, rest = url.split("//", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{prefix}//{user}:***@{host}"
    return url
