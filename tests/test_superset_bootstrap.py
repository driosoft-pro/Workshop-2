"""Superset bootstrap contract: specs stay in sync with the KPI SQL (offline)."""

from __future__ import annotations

import pytest

from scripts import superset_bootstrap as boot


def test_kpi_sql_defines_fourteen_queries():
    queries = boot.load_kpi_queries()
    assert len(queries) == 14
    assert all(name.startswith("kpi_") for name in queries)



def test_every_chart_dataset_exists_in_sql_and_specs():
    queries = boot.load_kpi_queries()
    for spec in boot.CHART_SPECS:
        dataset = spec["dataset"]
        if dataset != "etl_batch_log":
            assert dataset in queries, dataset
        assert dataset in boot.DATASET_SPECS, dataset
        assert spec["requirement"] and set(
            part.strip() for part in spec["requirement"].split(",")
        ) <= {"R1", "R2", "R3", "R4"}
        assert spec["slice_name"]


def test_every_requirement_has_at_least_one_chart():
    covered = {
        tag.strip()
        for spec in boot.CHART_SPECS
        for tag in spec["requirement"].split(",")
    }
    assert covered == {"R1", "R2", "R3", "R4"}


def test_chart_candidates_end_with_table_fallback():
    for spec in boot.CHART_SPECS:
        viz_types = [viz for viz, _ in spec["candidates"]]
        assert viz_types, spec["slice_name"]
        if len(viz_types) > 1:
            assert viz_types[-1] == "table", spec["slice_name"]


@pytest.mark.parametrize(
    "form,expected_groupby,expected_metrics",
    [
        ({"all_columns": ["a", "b"], "row_limit": 10}, ["a", "b"], []),
        ({"x_axis": "decade", "metrics": ["grammy_awards"]}, ["decade"], ["grammy_awards"]),
        ({"groupby": ["g"], "metrics": ["m"]}, ["g"], ["m"]),
        ({"columns": ["c"], "metrics": ["m"]}, ["c"], ["m"]),
    ],
)
def test_validation_query_shapes(form, expected_groupby, expected_metrics):
    query = boot._validation_query(form)
    assert query["groupby"] == expected_groupby
    assert query["metrics"] == expected_metrics
    assert query["row_limit"] >= 1
    assert "time_grain_sqla" in query["extras"]
