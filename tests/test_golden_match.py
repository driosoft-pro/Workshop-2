"""Tests for golden match counts consistency (F6)."""

import json
from pathlib import Path
import pytest

from src import config

GOLDEN_PATH = Path("tests/golden_match_counts.json")


def test_golden_match_counts_match_integration_metrics():
    assert GOLDEN_PATH.exists()
    golden = json.loads(GOLDEN_PATH.read_text())

    metrics_path = config.INTEGRATION_METRICS_PATH
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text())

    assert metrics["rows_grammy"] == golden["rows_grammy"]
    assert metrics["bridge_rows"] == golden["bridge_rows"]
    assert metrics["aggregate_excluded"] == golden["aggregate_excluded"]
    assert metrics["match_rate_pct"] == golden["match_rate_pct"]
    assert metrics["match_rate_strict_pct"] == golden["match_rate_strict_pct"]

    # Verify method counts
    for method, count in golden["methods"].items():
        assert metrics["match_rate_by_method"][method]["rows"] == count

    # Verify tier counts
    for tier, count in golden["tiers"].items():
        assert metrics["match_rate_by_tier"][tier]["rows"] == count
