"""Local smoke harness - runs the same stages as the Airflow DAG without Airflow.

The assessed orchestration is always dags/reliable_music_pipeline.py. This
script exists only to verify the engineering stages on a developer machine (or
inside the Airflow container) before triggering a DAG Run.

Usage:
    python -m scripts.smoke_test
    python -m scripts.smoke_test --source spotify_bad.csv   # controlled failure
    python -m scripts.smoke_test --skip-load --skip-kpis
"""

from __future__ import annotations

import argparse
import os
import sys

from src import analytics, config, extract, load, transform, validation
from src.validation import ValidationGateError


def run(source_filename: str | None, skip_load: bool, skip_kpis: bool) -> int:
    config.ensure_directories()
    if source_filename:
        os.environ["SPOTIFY_SOURCE_FILENAME"] = source_filename
        import importlib

        importlib.reload(config)

    print(f"[smoke] config: {config.describe()}")
    run_context = {"run_id": "local-smoke", "dag_id": "local-smoke", "task_id": "smoke"}

    spotify_metadata = extract.extract_spotify()
    grammy_metadata = extract.extract_grammys()

    spotify_frame = config.read_csv(spotify_metadata["raw_path"])
    validation.validate_gate(
        "raw_spotify", spotify_frame, run_context={**run_context, "stage": "raw_spotify"}
    )

    grammy_frame = config.read_csv(grammy_metadata["raw_path"], dtype={"winner": "string"})
    validation.validate_gate(
        "raw_grammys", grammy_frame, run_context={**run_context, "stage": "raw_grammys"}
    )

    summary = transform.transform_and_integrate(
        spotify_raw_path=spotify_metadata["raw_path"],
        grammy_raw_path=grammy_metadata["raw_path"],
    )

    for stage, path, options in (
        ("prepared_tracks", summary["outputs"]["prepared_tracks"], {}),
        (
            "prepared_grammys",
            summary["outputs"]["prepared_grammys"],
            {"dtype": {"winner_flag": "int64"}},
        ),
        ("prepared_metrics", summary["outputs"]["prepared_metrics"], {}),
    ):
        frame = config.read_csv(path, **options)
        validation.validate_gate(stage, frame, run_context={**run_context, "stage": stage})

    if not skip_load:
        load.load_dw(batch_id="local-smoke", dag_id="local-smoke", run_id="local-smoke")
        if not skip_kpis:
            analytics.build_kpis()

    print("[smoke] pipeline completed successfully")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Local smoke test for the music pipeline")
    parser.add_argument("--source", help="Override SPOTIFY_SOURCE_FILENAME (e.g. spotify_bad.csv)")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--skip-kpis", action="store_true")
    args = parser.parse_args()

    try:
        return run(args.source, args.skip_load, args.skip_kpis)
    except ValidationGateError as error:
        print(f"[smoke] BLOCKED BY VALIDATION GATE: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
