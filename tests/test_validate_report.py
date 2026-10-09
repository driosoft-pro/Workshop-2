"""Tests for validation report (F5)."""

from pathlib import Path
import pytest

from scripts.validate_report import run_all_checks, REPORT_MD, REPORT_JSON


def test_validate_report_runs_offline():
    # When DB is unreachable, DB checks should return SKIP, file checks PASS, and no crash
    checks = run_all_checks(superset_flag=False)
    assert len(checks) == 16
    
    check_ids = [c["id"] for c in checks]
    assert check_ids == [f"V{i}" for i in range(1, 17)]
    
    # Non-DB checks should be PASS or WARN, not crashing
    v16 = next(c for c in checks if c["id"] == "V16")
    assert v16["status"] == "PASS"

    v11 = next(c for c in checks if c["id"] == "V11")
    assert v11["status"] in ("PASS", "SKIP")
