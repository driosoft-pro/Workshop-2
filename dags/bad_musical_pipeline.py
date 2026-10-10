"""Controlled-failure batch pipeline (Test B) - Spotify CSV (corrupted) + Grammy source DB.

Workshop-2 architecture (section 5 & 15 - Mandatory Reliability Test B):

    Spotify branch (CORRUPTED)      Convergence and target                Grammy branch

    SPOTIFY BAD CSV (popularity=150)                                   GRAMMY DATABASE
        |                                                                       |
    extract_spotify (SUCCESS)                                              extract_grammys (SUCCESS)
        |                                                                       |
    validate_spotify_raw (BLOCKED - DQ-S3)                                validate_grammys_raw (SUCCESS)
                                      |
                     [Upstream Failed - DW Untouched]
                                      |
                           transform_and_integrate
                                      |
                              validate_prepared
                                      |
                                   load_dw
                                      |
                               DATA WAREHOUSE
                                      |
                                  build_kpis

Authoring interface: Airflow 3 TaskFlow (airflow.sdk).
Exposes the controlled failure demonstration directly from the Airflow UI without
requiring manual JSON configuration overrides.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import Param, dag, get_current_context, task

from src import analytics, config, extract, load, transform, validation

log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "etl-team",
    "depends_on_past": False,
    "retries": 0,
}

TRANSIENT_TASK_RETRY = {
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=10),
}


def _run_context() -> dict:
    try:
        context = get_current_context()
    except Exception:
        return {"dag_id": "manual", "task_id": "manual", "run_id": "manual", "try_number": 0}
    task_instance = context["ti"]
    return {
        "dag_id": task_instance.dag_id,
        "task_id": task_instance.task_id,
        "run_id": task_instance.run_id,
        "try_number": task_instance.try_number,
        "logical_date": str(context.get("data_interval_start") or context.get("logical_date") or ""),
    }


def _resolve_bad_spotify_source() -> Path:
    """Resolve the bad Spotify source file, auto-generating it if absent.

    Defaults to spotify_bad.csv (Test B controlled failure). If missing,
    automatically invokes make_bad_data() to guarantee that Test B executes
    with a deterministic DQ-S3 violation without requiring prior manual host setup.
    """
    try:
        conf = get_current_context()["dag_run"].conf or {}
    except Exception:
        conf = {}
    filename = str(conf.get("spotify_source_file") or "spotify_bad.csv")
    bad_path = config.BAD_DIR / filename
    if not bad_path.exists():
        candidate = config.resolve_source(filename)
        if candidate.exists():
            return candidate
        from scripts.make_bad_data import make_bad_data
        return make_bad_data(output_path=bad_path)
    return bad_path


def _enable_fuzzy_override() -> bool:
    """Check if fuzzy artist matching is enabled via DAG params or run conf."""
    try:
        context = get_current_context()
        dag_run = context.get("dag_run")
        if dag_run and dag_run.conf and "enable_fuzzy" in dag_run.conf:
            return bool(dag_run.conf["enable_fuzzy"])
        params = context.get("params", {})
        if "enable_fuzzy" in params:
            return bool(params["enable_fuzzy"])
    except Exception:
        pass
    return False


@dag(
    dag_id="bad_musical_pipeline",
    description=(
        "Controlled failure batch pipeline (Test B): ingests corrupted Spotify data "
        "(popularity=150) to demonstrate Great Expectations raw gate blocking (DQ-S3)."
    ),
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args=DEFAULT_ARGS,
    params={"enable_fuzzy": Param(False, type="boolean")},
    tags=["etl", "gx", "bad-pipeline", "controlled-failure", "workshop-2", "spotify", "grammy"],
)
def bad_musical_pipeline():
    @task(
        task_id="extract_spotify",
        execution_timeout=timedelta(minutes=15),
        doc_md="Acquire Spotify dataset (corrupted for Test B) and persist raw working extract.",
        **TRANSIENT_TASK_RETRY,
    )
    def extract_spotify_task() -> dict:
        """Acquire the corrupted Spotify CSV and persist raw working dataset."""
        run_context = _run_context()
        source_path = _resolve_bad_spotify_source()
        metadata = extract.extract_spotify(source_path=source_path)
        metadata["run_context"] = run_context
        metadata["source_override"] = source_path.name
        log.info(
            "extract_spotify context=%s rows=%s file=%s override=%s",
            run_context,
            metadata["rows"],
            metadata["source_filename"],
            source_path.name,
        )
        return metadata

    @task(
        task_id="extract_grammys",
        execution_timeout=timedelta(minutes=15),
        doc_md="Extract Grammy awards from source PostgreSQL database into raw working extract.",
        **TRANSIENT_TASK_RETRY,
    )
    def extract_grammys_task() -> dict:
        """Extract Grammy awards from the PostgreSQL SOURCE database."""
        run_context = _run_context()
        metadata = extract.extract_grammys()
        metadata["run_context"] = run_context
        log.info(
            "extract_grammys context=%s rows=%s table=%s",
            run_context,
            metadata["rows"],
            config.GRAMMY_SOURCE_TABLE,
        )
        return metadata

    @task(
        task_id="validate_spotify_raw",
        retries=0,
        doc_md="Validate raw Spotify extract against 22-column contract and quality rules via GX gate.",
    )
    def validate_spotify_raw_task(spotify_metadata: dict) -> dict:
        """Raw validation gate: catches deterministic DQ-S3 violation and halts execution."""
        run_context = _run_context()
        frame = config.read_csv(spotify_metadata["raw_path"])
        payload = validation.validate_gate(
            "raw_spotify", frame, run_context={**run_context, "stage": "raw_spotify"}
        )
        log.info(
            "validate_spotify_raw evidence=%s stats=%s warnings=%s",
            payload["evidence_path"],
            payload["statistics"],
            payload["failed_warning_rules"],
        )
        return {
            "stage": payload["stage"],
            "raw_path": spotify_metadata["raw_path"],
            "source_filename": spotify_metadata.get("source_filename"),
            "rows": spotify_metadata["rows"],
            "evidence_path": payload["evidence_path"],
            "success": payload["success"],
            "failed_warning_rules": payload["failed_warning_rules"],
        }

    @task(
        task_id="validate_grammys_raw",
        retries=0,
        doc_md="Validate raw Grammy awards extract against source quality rules via GX gate.",
    )
    def validate_grammys_raw_task(grammy_metadata: dict) -> dict:
        """Raw validation gate for the Grammy source database extract."""
        run_context = _run_context()
        frame = config.read_csv(grammy_metadata["raw_path"], dtype={"winner": "string"})
        payload = validation.validate_gate(
            "raw_grammys", frame, run_context={**run_context, "stage": "raw_grammys"}
        )
        log.info(
            "validate_grammys_raw evidence=%s stats=%s warnings=%s",
            payload["evidence_path"],
            payload["statistics"],
            payload["failed_warning_rules"],
        )
        return {
            "stage": payload["stage"],
            "raw_path": grammy_metadata["raw_path"],
            "rows": grammy_metadata["rows"],
            "evidence_path": payload["evidence_path"],
            "success": payload["success"],
            "failed_warning_rules": payload["failed_warning_rules"],
        }

    @task(
        task_id="transform_and_integrate",
        retries=0,
        doc_md="Execute T12-T16 cascade, cleaning, genre mapping, primary song flags, and bridge build.",
    )
    def transform_and_integrate_task(spotify_gate: dict, grammy_gate: dict) -> dict:
        """Clean, harmonise, integrate and derive the prepared datasets."""
        run_context = _run_context()
        enable_fuzzy = _enable_fuzzy_override()
        summary = transform.transform_and_integrate(
            spotify_raw_path=spotify_gate["raw_path"],
            grammy_raw_path=grammy_gate["raw_path"],
            enable_fuzzy=enable_fuzzy,
        )
        log.info(
            "transform_and_integrate context=%s decisions=%s fuzzy=%s",
            run_context,
            summary["decisions"],
            enable_fuzzy,
        )
        return {
            "prepared_tracks": summary["outputs"]["prepared_tracks"],
            "prepared_grammys": summary["outputs"]["prepared_grammys"],
            "prepared_bridge": summary["outputs"]["bridge_award_artist"],
            "prepared_metrics": summary["outputs"]["prepared_metrics"],
            "integration_metrics": summary["outputs"]["integration_metrics"],
            "transform_summary_path": str(config.TRANSFORM_SUMMARY_PATH),
        }

    @task(
        task_id="validate_prepared",
        retries=0,
        doc_md="Validate prepared tracks, grammys, metrics, and bridge tables against GX suites before DW load.",
    )
    def validate_prepared_task(prepared_metadata: dict) -> dict:
        """Prepared-data validation gate before the dimensional load."""
        run_context = _run_context()
        stages = [
            ("prepared_tracks", prepared_metadata["prepared_tracks"], {}),
            (
                "prepared_grammys",
                prepared_metadata["prepared_grammys"],
                {"dtype": {"winner_flag": "int64"}},
            ),
            ("prepared_metrics", prepared_metadata["prepared_metrics"], {}),
            ("prepared_bridge", prepared_metadata["prepared_bridge"], {}),
        ]

        payloads = []
        for stage, path, read_options in stages:
            frame = config.read_csv(path, **read_options)
            payloads.append(
                validation.run_stage(stage, frame, run_context={**run_context, "stage": stage})
            )

        for payload in payloads:
            validation.enforce_policy(payload)

        return {
            "gates": [
                {
                    "stage": payload["stage"],
                    "success": payload["success"],
                    "evidence_path": payload["evidence_path"],
                    "failed_warning_rules": payload["failed_warning_rules"],
                }
                for payload in payloads
            ],
            "prepared_tracks": prepared_metadata["prepared_tracks"],
            "prepared_grammys": prepared_metadata["prepared_grammys"],
            "prepared_bridge": prepared_metadata["prepared_bridge"],
            "prepared_metrics": prepared_metadata["prepared_metrics"],
            "integration_metrics": prepared_metadata["integration_metrics"],
        }

    @task(
        task_id="load_dw",
        execution_timeout=timedelta(minutes=30),
        doc_md="Load validated dimensions, facts, and award-artist bridge into PostgreSQL Data Warehouse.",
        **TRANSIENT_TASK_RETRY,
    )
    def load_dw_task(prepared_metadata: dict, prepared_gate: dict) -> dict:
        """Load validated prepared data into the dimensional Data Warehouse."""
        run_context = _run_context()
        batch_id = f"{run_context['dag_id']}__{run_context['run_id']}"
        summary = load.load_dw(
            batch_id=batch_id,
            dag_id=run_context["dag_id"],
            run_id=run_context["run_id"],
        )
        log.info("load_dw batch_id=%s rows_after=%s", batch_id, summary["row_counts_after"])
        return summary

    @task(
        task_id="build_kpis",
        execution_timeout=timedelta(minutes=15),
        doc_md="Compute analytical KPI datasets and render visualization charts for reporting and Superset BI.",
        **TRANSIENT_TASK_RETRY,
    )
    def build_kpis_task(load_summary: dict) -> dict:
        """Produce R1-R4 KPIs and visualisations from the Data Warehouse."""
        summary = analytics.build_kpis()
        log.info("build_kpis row_counts=%s", summary["row_counts"])
        return {
            "kpi_csvs": summary["kpi_csvs"],
            "charts": summary["charts"],
            "row_counts": summary["row_counts"],
            "summary_path": summary["summary_path"],
            "dw_batch_id": load_summary.get("batch_id"),
        }

    spotify_raw = extract_spotify_task()
    grammy_raw = extract_grammys_task()

    spotify_gate = validate_spotify_raw_task(spotify_raw)
    grammy_gate = validate_grammys_raw_task(grammy_raw)

    prepared = transform_and_integrate_task(spotify_gate, grammy_gate)

    prepared_gate = validate_prepared_task(prepared)

    warehouse = load_dw_task(prepared, prepared_gate)

    build_kpis_task(warehouse)


bad_musical_pipeline()
