"""Tests for match audit sampling and scoring tool (F4)."""

import pandas as pd
import pytest

from scripts.match_audit import sample_matches, score_audit, wilson_score_interval


def test_wilson_score_interval_math():
    # 0 of 0
    assert wilson_score_interval(0, 0) == (0.0, 0.0)
    
    # 40 of 40 (100% precision)
    low, high = wilson_score_interval(40, 40)
    assert 0.90 < low < 1.0
    assert high == 1.0

    # 20 of 40 (50% precision)
    low, high = wilson_score_interval(20, 40)
    assert 0.34 < low < 0.40
    assert 0.60 < high < 0.66
    assert low < 0.5 < high


def test_score_audit_unlabelled_pending(tmp_path):
    csv_file = tmp_path / "test_audit.csv"
    summary_file = tmp_path / "test_summary.json"
    
    df = pd.DataFrame([
        {"match_method": "exact", "label": ""},
        {"match_method": "workers", "label": ""},
    ])
    df.to_csv(csv_file, index=False)

    res = score_audit(input_path=csv_file, summary_path=summary_file)
    assert res["status"] == "AUDIT PENDING"


def test_score_audit_labelled_scores(tmp_path):
    csv_file = tmp_path / "test_audit.csv"
    summary_file = tmp_path / "test_summary.json"

    df = pd.DataFrame([
        {"match_method": "exact", "label": "y"},
        {"match_method": "exact", "label": "y"},
        {"match_method": "workers", "label": "y"},
        {"match_method": "workers", "label": "n"},
    ])
    df.to_csv(csv_file, index=False)

    res = score_audit(input_path=csv_file, summary_path=summary_file)
    assert res["status"] == "COMPLETED"
    assert res["methods"]["exact"]["precision"] == 1.0
    assert res["methods"]["workers"]["precision"] == 0.5
    assert res["overall"]["precision"] == 0.75
