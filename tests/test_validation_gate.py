"""Validation gate behaviour: critical blocks, warning passes, clean data passes."""

from __future__ import annotations

import pandas as pd
import pytest

from src import validation
from src.validation import ValidationGateError, enforce_policy, validate_gate

BASE_COLUMNS = [
    "track_id", "artists", "popularity", "duration_ms",
    "danceability", "energy", "valence", "track_genre",
]


def _frame(popularity: int = 50, duration_ms: int = 200000, rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "track_id": [f"t{i}" for i in range(rows)],
        "artists": [f"Artist {i}" for i in range(rows)],
        "popularity": [popularity] * rows,
        "duration_ms": [duration_ms] * rows,
        "danceability": [0.5] * rows,
        "energy": [0.5] * rows,
        "valence": [0.5] * rows,
        "track_genre": ["pop"] * rows,
    })


@pytest.fixture(autouse=True)
def _isolated_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(validation.config, "GX_RESULTS_DIR", tmp_path / "gx")
    monkeypatch.setattr(validation.config, "KPI_RESULTS_DIR", tmp_path / "kpis")
    monkeypatch.setattr(validation.config, "RUNS_EVIDENCE_DIR", tmp_path / "runs")


def test_clean_data_passes_the_raw_spotify_gate():
    payload = validate_gate("raw_spotify", _frame(), run_context={"run_id": "test-clean"})
    assert payload["success"] is True
    assert payload["failed_critical_rules"] == []


def test_out_of_range_popularity_blocks_the_gate():
    with pytest.raises(ValidationGateError) as error:
        validate_gate("raw_spotify", _frame(popularity=150),
                      run_context={"run_id": "test-critical"})
    assert "DQ-S3" in str(error.value)


def test_warning_level_failure_does_not_block():
    payload = validate_gate("raw_spotify", _frame(duration_ms=900_000),
                            run_context={"run_id": "test-warning"})
    assert "DQ-S4" in payload["failed_warning_rules"]
    assert payload["failed_critical_rules"] == []


def test_gate_writes_machine_readable_evidence(tmp_path):
    payload = validate_gate("raw_spotify", _frame(), run_context={"run_id": "test-evidence"})
    import json
    from pathlib import Path

    evidence = Path(payload["evidence_path"])
    assert evidence.exists()
    payload_on_disk = json.loads(evidence.read_text())
    assert payload_on_disk["stage"] == "raw_spotify"
    assert payload_on_disk["run_context"]["run_id"] == "test-evidence"
    assert len(payload_on_disk["expectations"]) == 8  # S1..S6 with S5 x3
    rule_ids = {item["rule_id"] for item in payload_on_disk["expectations"]}
    assert rule_ids == {"DQ-S1", "DQ-S2", "DQ-S3", "DQ-S4", "DQ-S5", "DQ-S6"}
    assert all(item["requirement"].startswith("R") for item in payload_on_disk["expectations"])


def test_unknown_stage_is_rejected():
    with pytest.raises(ValueError):
        validation.run_stage("nope", _frame())


def test_enforce_policy_reports_gate_pass_for_clean_payload():
    payload = {"stage": "raw_spotify", "max_failure_severity": None,
               "failed_critical_rules": [], "failed_warning_rules": [], "expectations": []}
    assert enforce_policy(payload) is payload
