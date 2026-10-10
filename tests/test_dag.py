"""Airflow DAG contract: task graph and reliability policy (offline)."""

from __future__ import annotations

import pytest

airflow = pytest.importorskip("airflow", reason="apache-airflow not installed")

from pathlib import Path  # noqa: E402

from airflow.models import DagBag  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAG_IDS = ["reliable_music_pipeline", "bad_musical_pipeline"]
EXPECTED_TASKS = [
    "extract_spotify",
    "extract_grammys",
    "validate_spotify_raw",
    "validate_grammys_raw",
    "transform_and_integrate",
    "validate_prepared",
    "load_dw",
    "build_kpis",
]


@pytest.fixture(scope="module")
def dag_bag():
    bag = DagBag(dag_folder=str(PROJECT_ROOT / "dags"), include_examples=False)
    assert not bag.import_errors, bag.import_errors
    for dag_id in DAG_IDS:
        assert dag_id in bag.dags, bag.dag_ids
    return bag


@pytest.fixture(params=DAG_IDS)
def dag(dag_bag, request):
    return dag_bag.dags[request.param]


def test_dag_exposes_eight_taskflow_tasks(dag):
    task_ids = sorted(task.task_id for task in dag.tasks)
    assert task_ids == sorted(EXPECTED_TASKS)


def test_dag_reliability_settings(dag):
    from airflow.timetables.simple import NullTimetable

    assert isinstance(dag.timetable, NullTimetable)  # schedule=None (manual runs only)
    assert dag.max_active_runs == 1
    assert dag.catchup is False
    assert dag.dagrun_timeout.total_seconds() == 2 * 3600


def test_gates_are_enforced_through_dependencies(dag):
    transform = dag.get_task("transform_and_integrate")
    upstream = {task.task_id for task in transform.upstream_list}
    assert upstream == {"validate_spotify_raw", "validate_grammys_raw"}

    load = dag.get_task("load_dw")
    assert "validate_prepared" in {task.task_id for task in load.upstream_list}

    prepared = dag.get_task("validate_prepared")
    assert "transform_and_integrate" in {task.task_id for task in prepared.upstream_list}


def test_data_quality_tasks_never_retry(dag):
    for task_id in (
        "validate_spotify_raw", "validate_grammys_raw",
        "transform_and_integrate", "validate_prepared",
    ):
        task = dag.get_task(task_id)
        assert task.retries == 0, task_id
