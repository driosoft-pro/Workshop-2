"""Reliable batch pipeline - Spotify CSV + Grammy source database -> trusted DW.

Workshop-2 architecture (section 5):

    Spotify branch                 Convergence and target                Grammy branch

    SPOTIFY CSV                                                        GRAMMY DATABASE
        |                                                                       |
    extract_spotify                                                        extract_grammys
        |                                                                       |
    validate_spotify_raw          both validated branches converge         validate_grammys_raw
                                      |
                                 transform_and_integrate
                                      |
                                  validate_prepared
                                      |
                                    load_dw
                                      |
                                 DATA WAREHOUSE
                                      |
                                 build_kpis -> KPIs / DASHBOARD

Authoring interface: Airflow 3 TaskFlow (airflow.sdk). Reusable logic lives in
src/, the DAG only expresses workflow structure, dependencies and operational
policy (Workshop-2, section 9.1).

Interfaces exchange file paths and compact metadata (XCom), never DataFrames.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task

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


def _spotify_source_override() -> str | None:
    """Source file selected for this DAG run (dag_run.conf).

    Test B (controlled Critical raw failure) triggers the DAG with
    ``{"spotify_source_file": "spotify_bad.csv"}``; every other run uses the
    configured default (SPOTIFY_SOURCE_FILENAME).
    """
    try:
        conf = get_current_context()["dag_run"].conf or {}
    except Exception:
        conf = {}
    value = conf.get("spotify_source_file")
    return str(value) if value else None


@dag(
    dag_id="reliable_music_pipeline",
    description=(
        "Validated batch pipeline integrating Spotify (CSV) and Grammy Awards "
        "(PostgreSQL source) into a trusted dimensional Data Warehouse with KPIs."
    ),
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args=DEFAULT_ARGS,
    tags=["etl", "gx", "reliable-pipeline", "workshop-2", "spotify", "grammy"],
)
def reliable_music_pipeline():
    @task(
        task_id="extract_spotify",
        execution_timeout=timedelta(minutes=15),
        **TRANSIENT_TASK_RETRY,
    )
    def extract_spotify_task() -> dict:
        """Acquire the Spotify CSV and persist the raw working dataset.

        Bounded retry is justified: a missing/unmounted volume or a transient
        filesystem error can succeed on a later attempt without changing data
        or code. A missing required column raises SourceContractError, which is
        deterministic and surfaces immediately (no retry can repair it).
        """
        run_context = _run_context()
        source_override = _spotify_source_override()
        metadata = extract.extract_spotify(
            source_path=config.resolve_source(source_override)
            if source_override
            else None
        )
        metadata["run_context"] = run_context
        metadata["source_override"] = source_override
        log.info("extract_spotify context=%s rows=%s file=%s override=%s",
                 run_context, metadata["rows"], metadata["source_filename"], source_override)
        return metadata

    @task(
        task_id="extract_grammys",
        execution_timeout=timedelta(minutes=15),
        **TRANSIENT_TASK_RETRY,
    )
    def extract_grammys_task() -> dict:
        """Extract Grammy awards from the PostgreSQL SOURCE database.

        The source database is populated by scripts/prepare_source_db.py
        (source preparation). Bounded retry covers transient database
        unavailability during container startup.
        """
        run_context = _run_context()
        metadata = extract.extract_grammys()
        metadata["run_context"] = run_context
        log.info("extract_grammys context=%s rows=%s table=%s",
                 run_context, metadata["rows"], config.GRAMMY_SOURCE_TABLE)
        return metadata

    @task(task_id="validate_spotify_raw", retries=0)
    def validate_spotify_raw_task(spotify_metadata: dict) -> dict:
        """Raw validation gate: are the incoming Spotify data safe enough?

        Critical GX failures raise ValidationGateError and block the Spotify
        branch; warning results are logged and reported (documented policy).
        No retry: the rule violation is deterministic for a given input file.
        """
        run_context = _run_context()
        frame = config.read_csv(spotify_metadata["raw_path"])
        payload = validation.validate_gate(
            "raw_spotify", frame, run_context={**run_context, "stage": "raw_spotify"}
        )
        log.info("validate_spotify_raw evidence=%s stats=%s warnings=%s",
                 payload["evidence_path"], payload["statistics"],
                 payload["failed_warning_rules"])
        return {
            "stage": payload["stage"],
            "raw_path": spotify_metadata["raw_path"],
            "source_filename": spotify_metadata.get("source_filename"),
            "rows": spotify_metadata["rows"],
            "evidence_path": payload["evidence_path"],
            "success": payload["success"],
            "failed_warning_rules": payload["failed_warning_rules"],
        }

    @task(task_id="validate_grammys_raw", retries=0)
    def validate_grammys_raw_task(grammy_metadata: dict) -> dict:
        """Raw validation gate for the Grammy source database extract."""
        run_context = _run_context()
        frame = config.read_csv(grammy_metadata["raw_path"], dtype={"winner": "string"})
        payload = validation.validate_gate(
            "raw_grammys", frame, run_context={**run_context, "stage": "raw_grammys"}
        )
        log.info("validate_grammys_raw evidence=%s stats=%s warnings=%s",
                 payload["evidence_path"], payload["statistics"],
                 payload["failed_warning_rules"])
        return {
            "stage": payload["stage"],
            "raw_path": grammy_metadata["raw_path"],
            "rows": grammy_metadata["rows"],
            "evidence_path": payload["evidence_path"],
            "success": payload["success"],
            "failed_warning_rules": payload["failed_warning_rules"],
        }

    @task(task_id="transform_and_integrate", retries=0)
    def transform_and_integrate_task(spotify_gate: dict, grammy_gate: dict) -> dict:
        """Clean, harmonise, integrate and derive the prepared datasets.

        Runs only after BOTH raw gates satisfied their policy (dependencies are
        declared through the gate outputs). The integration contract is
        documented in docs/transformation_integration.md.
        """
        run_context = _run_context()
        summary = transform.transform_and_integrate(
            spotify_raw_path=spotify_gate["raw_path"],
            grammy_raw_path=grammy_gate["raw_path"],
        )
        log.info("transform_and_integrate context=%s decisions=%s",
                 run_context, summary["decisions"])
        return {
            "prepared_tracks": summary["outputs"]["prepared_tracks"],
            "prepared_grammys": summary["outputs"]["prepared_grammys"],
            "prepared_metrics": summary["outputs"]["prepared_metrics"],
            "transform_summary_path": str(config.TRANSFORM_SUMMARY_PATH),
            "decisions": summary["decisions"],
            "metrics": summary["metrics"],
            "reconciliation": summary["reconciliation"],
        }

    @task(task_id="validate_prepared", retries=0)
    def validate_prepared_task(prepared_metadata: dict) -> dict:
        """Prepared-data validation gate before the dimensional load.

        Runs every prepared checkpoint (tracks, awards, integration metrics),
        records all results, and only then applies the severity policy so that
        a single run produces complete diagnostic evidence.
        """
        run_context = _run_context()
        stages = [
            ("prepared_tracks", prepared_metadata["prepared_tracks"], {}),
            (
                "prepared_grammys",
                prepared_metadata["prepared_grammys"],
                {"dtype": {"winner_flag": "int64"}},
            ),
            ("prepared_metrics", prepared_metadata["prepared_metrics"], {}),
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
            "prepared_metrics": prepared_metadata["prepared_metrics"],
            "metrics": prepared_metadata["metrics"],
        }

    @task(
        task_id="load_dw",
        execution_timeout=timedelta(minutes=30),
        **TRANSIENT_TASK_RETRY,
    )
    def load_dw_task(prepared_metadata: dict, prepared_gate: dict) -> dict:
        """Load validated prepared data into the dimensional Data Warehouse.

        Strategy: controlled replace inside one transaction (delete + insert)
        with business-key unique constraints, so reruns cannot duplicate rows.
        The load only runs when the prepared gate passed (dependency on the
        gate output). Retry is limited to transient database failures.
        """
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
        retries=1,
        retry_delay=timedelta(minutes=1),
        retry_exponential_backoff=True,
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


reliable_music_pipeline()
