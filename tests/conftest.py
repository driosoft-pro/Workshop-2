"""Shared fixtures for the Workshop-2 test suite.

Unit tests run offline (no Docker/Podman, no PostgreSQL). Integration tests
are marked with @pytest.mark.integration and auto-skip when music_dw is not
reachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import config  # noqa: E402


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    """Redirect every output path of the pipeline to a temp directory."""
    work = tmp_path / "work"
    output = tmp_path / "output"
    bad = tmp_path / "bad"
    evidence = tmp_path / "evidence"
    for path in (work, output, bad, evidence):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "WORK_DIR", work)
    monkeypatch.setattr(config, "OUTPUT_DIR", output)
    monkeypatch.setattr(config, "BAD_DIR", bad)
    monkeypatch.setattr(config, "GX_RESULTS_DIR", evidence / "gx")
    monkeypatch.setattr(config, "KPI_RESULTS_DIR", evidence / "kpis")
    monkeypatch.setattr(config, "RUNS_EVIDENCE_DIR", evidence / "runs")
    monkeypatch.setattr(config, "PREPARED_TRACKS_PATH", work / "prepared_tracks.csv")
    monkeypatch.setattr(config, "PREPARED_GRAMMYS_PATH", work / "prepared_grammys.csv")
    monkeypatch.setattr(config, "PREPARED_METRICS_PATH", work / "prepared_metrics.csv")
    monkeypatch.setattr(config, "TRANSFORM_SUMMARY_PATH", work / "transform_summary.json")
    monkeypatch.setattr(config, "SPOTIFY_RAW_PATH", work / "spotify_raw.csv")
    monkeypatch.setattr(config, "GRAMMY_RAW_PATH", work / "grammys_raw.csv")
    return config


def dw_available() -> bool:
    """True when the analytical Data Warehouse accepts connections."""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(config.DW_DB_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def dw_url() -> str:
    if not dw_available():
        pytest.skip("music_dw unreachable - start the stack (run.sh up) for integration tests")
    return config.DW_DB_URL
