"""Tests for DQ-P14 match rate threshold and regression checks (F1c).

Rule: Warning if rate < 0.40 OR drops > 2pp vs previous committed batch.
None previous -> pass.
"""

import pytest
from src.validation import evaluate_match_rate_threshold


def test_no_previous_batch_passes_when_above_minimum():
    res = evaluate_match_rate_threshold(current_rate=0.51, previous_rate=None)
    assert res["success"]
    assert res["severity"] == "pass"


def test_no_previous_batch_fails_when_below_minimum():
    res = evaluate_match_rate_threshold(current_rate=0.38, previous_rate=None)
    assert not res["success"]
    assert res["severity"] == "warning"
    assert any("below minimum" in r for r in res["reasons"])


def test_drop_within_2pp_passes():
    # 51% vs previous 52% (drop 1pp <= 2pp)
    res = evaluate_match_rate_threshold(current_rate=0.51, previous_rate=0.52)
    assert res["success"]
    assert res["severity"] == "pass"


def test_drop_exceeding_2pp_triggers_warning():
    # 48% vs previous 52% (drop 4pp > 2pp)
    res = evaluate_match_rate_threshold(current_rate=0.48, previous_rate=0.52)
    assert not res["success"]
    assert res["severity"] == "warning"
    assert any("exceeding" in r for r in res["reasons"])


def test_drop_3pp_triggers_warning():
    # Drop 3pp (e.g. 52.4% -> 49.4%)
    res = evaluate_match_rate_threshold(current_rate=0.494, previous_rate=0.524)
    assert not res["success"]
    assert res["severity"] == "warning"
