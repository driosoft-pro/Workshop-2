"""Central configuration for the Workshop-2 reliable music pipeline.

All paths and connections are resolved from environment variables so the same
code runs inside the Airflow containers (/opt/airflow/...) and on a developer
host (repository layout). See .env.example for the documented variables.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


_load_env_file()


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if value:
        if value.startswith("/opt/airflow") and not Path("/opt/airflow").exists():
            return default
        return Path(value)
    return default


def _default_data_dir() -> Path:
    container_path = Path("/opt/airflow/data")
    if container_path.exists():
        return container_path
    return PROJECT_ROOT / "data"


DATA_DIR = _env_path("MUSIC_DATA_DIR", _default_data_dir())
RAW_DIR = DATA_DIR / "raw"
WORK_DIR = DATA_DIR / "work"
OUTPUT_DIR = DATA_DIR / "output"
DATA_PROCESSED_DIR = OUTPUT_DIR
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

def _resolve_db_url(env_var: str, default_db_name: str) -> str:
    url = os.environ.get(env_var)
    if url:
        return url
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("MUSIC_POSTGRES_PORT", "5432")
    if user and password:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{default_db_name}"
    return f"postgresql+psycopg2://{host}:{port}/{default_db_name}"


SOURCE_DB_URL = _resolve_db_url("MUSIC_SOURCE_DB_URL", os.environ.get("POSTGRES_DB", "music_source"))
DW_DB_URL = _resolve_db_url("MUSIC_DW_DB_URL", "music_dw")

DW_LOAD_STRATEGY = os.environ.get("DW_LOAD_STRATEGY", "replace")

GRAMMY_SOURCE_TABLE = "grammy_awards"

SPOTIFY_SOURCE_COLUMNS = [
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
    # audio/musical metadata previously profiled but not loaded (T15 contract)
    "key",
    "mode",
    "instrumentalness",
    "time_signature",
]

# Raw Spotify contract (22 columns): the 20 source columns above plus
# source_row_index (CSV row provenance, values untouched) and duration_min
# (derived presentation measure). Every source column is now loaded, so no
# profiled-but-dropped column can hide a quality problem.
SPOTIFY_REQUIRED_COLUMNS = SPOTIFY_SOURCE_COLUMNS + [
    "source_row_index",
    "duration_min",
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
BRIDGE_AWARD_ARTIST_PATH = WORK_DIR / "bridge_award_artist.csv"
TRANSFORM_SUMMARY_PATH = WORK_DIR / "transform_summary.json"
INTEGRATION_METRICS_PATH = RUNS_EVIDENCE_DIR / "integration_metrics.json"

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
