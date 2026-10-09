"""Quality rule catalog: structure, tags and severity policy (offline)."""

from __future__ import annotations

import re

import pandas as pd
import pytest

from src import validation
from src.validation import RULES, STAGES, ValidationGateError, enforce_policy

REQUIREMENTS = {"R1", "R2", "R3", "R4"}
DIMENSIONS = {"Completeness", "Validity", "Uniqueness", "Consistency"}
SEVERITIES = {"critical", "warning"}


def test_rule_catalog_has_34_rules():
    assert len(RULES) == 34


def test_rule_ids_match_documented_pattern():
    pattern = re.compile(r"^DQ-(S|G|P)\d+$")
    assert all(pattern.match(rule_id) for rule_id in RULES)


def test_every_stage_has_rules_and_layers_are_valid():
    layers = {rule["layer"] for rule in RULES.values()}
    assert layers == set(STAGES)
    for stage in STAGES:
        assert any(rule["layer"] == stage for rule in RULES.values())


def test_rule_metadata_is_complete_and_typed():
    for rule_id, rule in RULES.items():
        assert rule["severity"] in SEVERITIES, rule_id
        assert rule["dimension"] in DIMENSIONS, rule_id
        assert rule["threshold"], rule_id
        assert rule["rule"], rule_id
        assert rule["attribute"], rule_id


def test_requirement_tags_are_r1_to_r4():
    for rule_id, rule in RULES.items():
        tags = [tag.strip() for tag in rule["requirement"].split(",")]
        assert tags, rule_id
        assert set(tags) <= REQUIREMENTS, f"{rule_id}: {tags}"
        # every requirement must be covered by at least one rule
    covered = {
        tag.strip()
        for rule in RULES.values()
        for tag in rule["requirement"].split(",")
    }
    assert covered == REQUIREMENTS


def test_critical_and_warning_rules_both_exist():
    severities = {rule["severity"] for rule in RULES.values()}
    assert severities == SEVERITIES


def test_policy_blocks_on_critical_failure():
    payload = {
        "stage": "raw_spotify",
        "max_failure_severity": validation.CRITICAL.value,
        "expectations": [
            {"success": False, "severity": "critical", "rule_id": "DQ-S3",
             "expectation": "expect_column_values_to_be_between",
             "result": {"unexpected_count": 1}},
        ],
    }
    with pytest.raises(ValidationGateError) as error:
        enforce_policy(payload)
    assert "DQ-S3" in str(error.value)


def test_policy_allows_warning_failures():
    payload = {
        "stage": "raw_spotify",
        "max_failure_severity": validation.WARNING.value,
        "failed_warning_rules": ["DQ-S4"],
        "expectations": [
            {"success": False, "severity": "warning", "rule_id": "DQ-S4",
             "expectation": "expect_column_values_to_be_between",
             "result": {"unexpected_count": 2}},
        ],
    }
    assert enforce_policy(payload) is payload


def test_policy_allows_clean_payload():
    payload = {
        "stage": "prepared_tracks",
        "max_failure_severity": None,
        "failed_warning_rules": [],
        "expectations": [],
    }
    assert enforce_policy(payload) is payload
