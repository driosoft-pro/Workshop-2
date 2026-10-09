"""Great Expectations suites must stay in sync with the RULES catalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import config
from src.validation import RULES, STAGE_SPEC

SUITE_FILES = sorted(Path(config.GX_DIR, "expectations").glob("*.json"))


def _suite_expectations(path: Path) -> dict:
    payload = json.loads(path.read_text())
    return payload["name"], payload["expectations"]


def test_six_suite_files_exist():
    assert len(SUITE_FILES) == 6
    names = {payload["name"] for payload in map(lambda p: json.loads(p.read_text()), SUITE_FILES)}
    assert names == {spec["suite"] for spec in STAGE_SPEC.values()}


def test_forty_five_expectations_total():
    total = sum(len(_suite_expectations(path)[1]) for path in SUITE_FILES)
    assert total == 45



def test_every_expectation_carries_rule_meta():
    for path in SUITE_FILES:
        suite_name, expectations = _suite_expectations(path)
        for expectation in expectations:
            meta = expectation.get("meta") or {}
            rule_id = meta.get("rule_id")
            assert rule_id, f"{path.name}: expectation without rule_id"
            assert rule_id in RULES, f"{path.name}: unknown rule {rule_id}"
            rule = RULES[rule_id]
            assert meta.get("severity") == rule["severity"], f"{suite_name}/{rule_id}"
            assert meta.get("requirement") == rule["requirement"], f"{suite_name}/{rule_id}"
            assert meta.get("quality_dimension") == rule["dimension"], f"{suite_name}/{rule_id}"
            assert expectation.get("severity") == rule["severity"], f"{suite_name}/{rule_id}"
            assert expectation.get("type", "").startswith("expect_"), f"{suite_name}/{rule_id}"
            assert expectation.get("kwargs", {}).get("column") or "value_set" in expectation.get(
                "kwargs", {}
            ) or "column" in str(expectation.get("kwargs", {}))


def test_suite_stage_mapping_matches_validation_stages():
    for path in SUITE_FILES:
        suite_name, _ = _suite_expectations(path)
        stages = [stage for stage, spec in STAGE_SPEC.items() if spec["suite"] == suite_name]
        assert len(stages) == 1, f"{suite_name} not mapped to exactly one stage"


def test_raw_spotify_suite_blocks_out_of_range_popularity():
    """DQ-S3 (critical) is the expectation exercised by Test B."""
    suite_name, expectations = _suite_expectations(
        Path(config.GX_DIR, "expectations", "spotify_raw_suite.json")
    )
    popularity = [
        e for e in expectations
        if e["meta"]["rule_id"] == "DQ-S3" and e["kwargs"].get("column") == "popularity"
    ]
    assert len(popularity) == 1
    assert popularity[0]["kwargs"]["min_value"] == 0
    assert popularity[0]["kwargs"]["max_value"] == 100
    assert popularity[0]["severity"] == "critical"
