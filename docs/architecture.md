# Pipeline Architecture

Workshop-2, sections 4.2, 5 and 6.11.

## 1. Reliable pipeline pattern

```
                        Spotify branch            Convergence / target             Grammy branch

  data/raw/spotify_dataset.csv                  PostgreSQL music_source
            |                                               |
      extract_spotify                                extract_grammys
            |                                               |
   validate_spotify_raw  ---- both raw gates ----  validate_grammys_raw
                              converge (AND)
                                   |
                        transform_and_integrate            T1-T11: cleaning, harmonisation,
                                   |                        integration, derivation
                              validate_prepared      3 prepared checkpoints
                                   |                        AND gate
                                 load_dw             transactional replace into the star schema
                                   |
                              DATA WAREHOUSE  (music_dw: 4 dims + 2 facts + etl_batch_log)
                                   |
                               build_kpis      7 SQL KPIs + 4 PNG charts (AR1-AR4)
                                   |
                          KPIs / DASHBOARD (Power BI on music_dw)
```

Quality design around the flow: *profiling → quality risks → quality rules →
Great Expectations → validation gates*.
Reliability design around the flow: *dependencies → selective retries → logs →
monitoring → controlled failure → safe rerun*.

## 2. Component inventory

| Layer | Implementation | Location |
| --- | --- | --- |
| Orchestration | Apache Airflow **3.1.8**, TaskFlow API (`from airflow.sdk import dag, task, get_current_context`), LocalExecutor | `dags/reliable_music_pipeline.py`, `docker-compose.yaml` |
| Reusable logic | Extract / transform / validate / load / analytics modules (no business logic in the DAG) | `src/*.py` |
| Automated validation | Great Expectations **1.23.1**, file-mode project, 5 suites, 5 validation definitions, 5 checkpoints | `gx/`, `src/validation.py` |
| Source DB (Grammy) | PostgreSQL 16, `music_source.grammy_awards` | `sql/source_setup.sql`, `scripts/prepare_source_db.py` |
| Data Warehouse | PostgreSQL 16, `music_dw` star schema | `sql/dw_schema.sql`, `src/load.py` |
| Analytics | 7 SQL queries + pandas/matplotlib charts | `sql/kpi_queries.sql`, `src/analytics.py` |
| Dashboard | Power BI Desktop on `music_dw` (PostgreSQL) | `docs/powerbi_dashboard.md` |
| Evidence | GX JSON results, run summaries, KPI CSV/PNG, task logs | `docs/evidence/` |

## 3. Implemented DAG structure

![Implemented DAG structure](dag_structure.png)

Task graph (`dags/reliable_music_pipeline.py`) — 8 TaskFlow tasks, each an
individually observable state in the Grid view:

| Task | Depends on | Reads | Writes | Retries |
| --- | --- | --- | --- | --- |
| `extract_spotify` | – | `data/raw/spotify_dataset.csv` (or `dag_run.conf.spotify_source_file`) | `data/work/spotify_raw.csv` | 2 (transient FS) |
| `extract_grammys` | – | PostgreSQL `music_source.grammy_awards` | `data/work/grammys_raw.csv` | 2 (transient DB) |
| `validate_spotify_raw` | `extract_spotify` | `spotify_raw.csv` | `docs/evidence/gx/raw_spotify/*.json` | **0** (deterministic) |
| `validate_grammys_raw` | `extract_grammys` | `grammys_raw.csv` | `docs/evidence/gx/raw_grammys/*.json` | **0** |
| `transform_and_integrate` | **both** raw gates | the two raw CSVs | `prepared_tracks.csv`, `prepared_grammys.csv`, `prepared_metrics.csv`, `transform_summary.json` | **0** |
| `validate_prepared` | transform | the three prepared CSVs | `docs/evidence/gx/prepared_*/` | **0** |
| `load_dw` | prepared gate | the three prepared CSVs | `music_dw` tables + `etl_batch_log`, `data/output/*.csv`, `load_summary.json` | 2 (transient DB) |
| `build_kpis` | `load_dw` | `music_dw` | `docs/evidence/kpis/*.csv`, `*.png`, `kpi_summary.json` | 1 |

Guarantees enforced by dependencies:

* transformation is unreachable until **both** raw gates satisfy the severity
  policy (`transform_and_integrate` takes both gate outputs as arguments);
* the load is unreachable until `validate_prepared` returned (its output is a
  positional argument of `load_dw`);
* `max_active_runs=1` prevents concurrent batches on the same target;
* task interfaces exchange **paths and compact metadata only** (XCom dictionaries
  of scalar values/paths) — DataFrames are never pushed into the metadata store.

## 4. Environments and data flow

### 4.1 Source preparation (distinct from the ETL Load)

```
the_grammy_awards.csv  --scripts/prepare_source_db.py-->  music_source.grammy_awards
```

This only creates the operational source the pipeline extracts from
(section 6.2). It is **not** the Load stage: the Load writes `music_dw`.

### 4.2 Container topology (`docker-compose.yaml`)

| Service | Image | Purpose |
| --- | --- | --- |
| `postgres` | postgres:16 | Airflow metadata DB |
| `music-postgres` | postgres:16 | `music_source` (source) + `music_dw` (target); SQL auto-init via `sql/db_init/01_create_dw.sql` |
| `airflow-init` | build `Dockerfile` | one-off: `airflow db migrate`, admin user, version banner |
| `airflow-scheduler`, `airflow-dag-processor`, `airflow-triggerer`, `airflow-apiserver` | build `Dockerfile` | Airflow 3.1.8 runtime (LocalExecutor, no Redis/Celery) |
| `airflow-cli` | build `Dockerfile` | `profile: debug` — ad-hoc CLI (`podman compose run --rm airflow-cli ...`) |

The custom image adds `pandas 2.3.3`, `great_expectations 1.23.1`,
`SQLAlchemy 2.0.41`, `psycopg2-binary 2.9.10`, `matplotlib 3.10.7`
(`requirements.txt`); Airflow itself comes from `apache/airflow:3.1.8`.

Project folders are bind-mounted (`dags/`, `src/`, `gx/`, `data/`, `docs/`,
`sql/`, `scripts/`, `logs/`, `config/`, `plugins/`), so evidence written by the
containers lands in the repository.

### 4.3 Developer host (evidence runs without Docker)

The same modules run outside Airflow (`scripts/smoke_test.py`) with
`PYTHONPATH=.` and the `MUSIC_*` environment variables (see `README.md`).
This is used for fast iteration; the assessed runs are the Airflow runs.

## 5. Interface contract between stages

| From → To | Payload (XCom/return value) |
| --- | --- |
| extract → gate | `{raw_path, rows, columns, source_filename, run_context}` |
| gate → transform | `{raw_path, rows, success, evidence_path, failed_warning_rules}` |
| transform → prepared gate | `{prepared_tracks, prepared_grammys, prepared_metrics, decisions, metrics, reconciliation}` |
| prepared gate → load | the three prepared paths + `metrics` + per-stage evidence paths |
| load → build_kpis | `load_summary` (batch id, row counts before/after, strategy) |

## 6. Failure and observability model

* Deterministic data/contract failures (`SourceContractError`, `ValidationGateError`)
  raise with an actionable message and **never** retry — see
  [`failure_retry_policy.md`](failure_retry_policy.md).
* Transient operational failures (DB/filesystem) use a bounded exponential
  backoff (2 retries, 1 min base, 10 min cap).
* Every gate writes a machine-readable evidence JSON containing the run context,
  per-rule results and the failed rule ids, under `docs/evidence/gx/<stage>/`.
* Airflow states/logs answer: what ran (task instances), when (timestamps),
  did it succeed (states + row counts), where it failed (failed task + skipped
  downstream), why (exception + GX evidence path), what happened next
  (retry/stop per policy).
