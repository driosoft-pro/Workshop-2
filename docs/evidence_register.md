# Reliability Evidence Register

Workshop-2, section 4.4 and the checklist in section 8.3. Every claim below is
reproducible from the artefact path (relative to the repository root). Airflow
runs were executed on the Docker/Podman stack; task logs are the same files the
Web UI shows (`logs/dag_id=…/run_id=…/task_id=…/attempt=1.log`).

## Register

| Evidence ID | Run / Task | Artefact or path | What it proves | Related policy / rule |
| --- | --- | --- | --- | --- |
| **E1** | Source preparation | `docs/evidence/runs/source_preparation.json`, `sql/source_setup.sql`, `scripts/prepare_source_db.py` | Grammy CSV loaded into PostgreSQL `music_source.grammy_awards`, 4,810 = 4,810 row reconciliation, DDL + import decisions documented | §6.2 source preparation (not the ETL Load) |
| **E2** | Environment | `docker-compose.yaml`, `Dockerfile`, `.env.example`; `docs/evidence/runs/airflow_api_version_and_runs.json` (persisted `GET /api/v2/version` → `{"version":"3.1.8"}` plus the 3 dagRuns) | reproducible compose environment; **Airflow reports 3.1.8**; DAG + run history survive a stack restart | §6.2 environment |
| **E3** | Profiling | `notebooks/data_profiling.ipynb` (executed, 27 cells) + `docs/evidence/profiling_summary.json` | structure/completeness/uniqueness/categorical/numerical/temporal/cross-source evidence for every risk in `docs/quality_rules.md` §2 | §6.3 profiling |
| **E4** | Quality design | `docs/quality_rules.md`, `RULES` in `src/validation.py` | 34 rules with metric, threshold, severity, justification and R tags (includes DQ-S7, DQ-G6..G11, DQ-P13..P16) | §6.5 rules & thresholds |
| **E5** | GX design | `docs/gx_design.md`, `gx/expectations/*.json`, `gx/validation_definitions/*.json`, `gx/checkpoints/*.json` | Rule ID ↔ Expectation mapping; 40 expectations across 6 suites/checkpoints for raw and prepared | §6.6 GX design |
| **E6** | Test A — raw gates | `docs/evidence/gx/raw_spotify/20261003T032258323783_test_a_success.json`, `…/raw_grammys/…_test_a_success.json` | both raw gates pass (8/8, 6/6 expectations; `success_percent=100`) with full per-rule evidence | §6.7 raw validation |
| **E7** | Test A — prepared gates | `docs/evidence/gx/prepared_tracks|prepared_grammys|prepared_metrics/*_test_a_success.json` | 26 prepared expectations pass across tracks, awards, bridge, metrics; prepared suites distinct from raw suites | §6.9 prepared validation |
| **E8** | Test A — successful DAG run | `docs/evidence/runs/airflow_test_a_success_summary.json`, `airflow_test_a_success_dagrun.json`, `airflow_test_a_success_log_*.txt` (8 task logs) | all 8 tasks `success` (try=1) in 61.3 s: extract → both raw gates → transform → prepared gate → load → KPIs | §7.1 Test A |
| **E9** | Test A — reconciliation | `airflow_test_a_success_log_transform_and_integrate.txt` | `114,000 → 157,530` track-artist rows (T1 −1, T2 −450, T3 explode); `4,810 → 4,810` Grammy rows; enriched match metrics (~48.7%), strict (29.0%) | §6.8 transformation |
| **E10** | Test A — load | `airflow_test_a_success_log_load_dw.txt` | `row_counts_before = all 0`, `row_counts_after = 157,530 / 4,810 / 31,001 / 114 / 62 / 638 / 2,757 bridge`; batch id recorded | §6.10 loading |
| **E11** | **Test B — controlled critical failure** | run `test_b_critical_failure`: `airflow_test_b_critical_failure_summary.json` (gate `failed`, 4 tasks `upstream_failed`), `airflow_test_b_critical_failure_log_validate_spotify_raw.txt` | extract succeeds, gate fails on **DQ-S3** with `ValidationGateError … unexpected_count=1 … popularity`, downstream never runs | §7.2 Test B; severity policy (critical blocks) |
| **E12** | Test B — GX result | `docs/evidence/gx/raw_spotify/20261003T032430534472_test_b_critical_failure.json` | `success=false`, `max_failure_severity=critical`, `failed_critical_rules=["DQ-S3"]`, `partial_unexpected_list=[150]`, `success_percent=87.5` | §6.7 evidence for failed execution |
| **E13** | Test B — isolation | `docs/evidence/gx/raw_grammys/20261003T032429936261_test_b_critical_failure.json` (`success=true`) + absence of a `test_b_critical_failure` row in `etl_batch_log` | the defect is isolated to the Spotify branch; the Data Warehouse was not written | failure policy |
| **E14** | Selective retries | task configuration in `dags/reliable_music_pipeline.py` + `airflow_test_*_summary.json` (`try_number=1` everywhere, including the failing gate) | retries are selective (2/1/0 per class), no blanket `retries=3`; a deterministic failure is not retried | §6.11 retries |
| **E15** | **Test C — safe rerun** | `airflow_test_c_safe_rerun_summary.json` + `airflow_dw_counts_after_test_c.csv` | rerun of the same input: 8/8 tasks success, DW counts **identical** to Test A (no duplication) | §7.3 safe rerun |
| **E16** | Test C — replace mechanics | `airflow_test_c_safe_rerun_log_load_dw.txt` (`row_counts_before` = previous batch counts) + `airflow_etl_batch_log.csv` | strategy `replace` in one transaction; `etl_batch_log` holds one row per batch with equal `target_rows_after` | §7.3 strategy |
| **E17** | Module-level rerun | `docs/evidence/runs/safe_rerun_run1_counts.csv`, `safe_rerun_run2_counts.csv` (diff empty) | same idempotence guarantee outside Airflow | §7.3 |
| **E18** | Analytics from the DW | `docs/evidence/kpis/kpi_*.csv` (13 result sets), `kpi_summary.json`, `ar1..ar4_*.png` (4 redesigned charts), Superset 21 charts | 13 KPIs and 4 redesigned visualizations querying `music_dw`, Superset published dashboard | §8.1 analytics |
| **E19** | Traceability | `docs/traceability_matrix.md`, R tags in `src/validation.py`, `-- Rn` tags in `sql/kpi_queries.sql` | requirement → rule → expectation → transformation → DW → KPI chain | §8.2 traceability |
| **E20** | Security hygiene | `.env.example` (no secrets), `.gitignore` (ignores `.env`, `data/work`, `data/output`, `data/bad`, `gx/uncommitted`), masked credentials in logs (`config.describe()` prints `***`) | no credentials committed; only documented variables | §6.2 secrets |
| **E21** | Task-state overview (Grid-view equivalent) | `docs/evidence/runs/airflow_task_states.png`, `docs/dag_structure.png` | all 8 task states side by side: Test A/C green, Test B red at `validate_spotify_raw` + orange `upstream_failed` downstream; the implemented dependency graph with per-task retry class | §7.1/§7.2 evidence with interpretation |

## Claim → artefact quick map

| Checklist item (§8.3) | Evidence |
| --- | --- |
| Analytical-requirement table and scope | `docs/analytical_requirements.md`, E19 |
| Conceptual architecture and DAG structure | `docs/architecture.md`, E2, E8 |
| Profiling notebook and evidence for both sources | E3 |
| Quality-risk analysis and quality-rule table | E4 |
| GX design and validation outputs (raw + prepared) | E5, E6, E7, E12 |
| Transformation and integration decision record | `docs/transformation_integration.md`, E9 |
| Dimensional model and executable schema | `docs/dimensional_model.md`, `sql/dw_schema.sql`, E10 |
| Successful DAG Run evidence | E8, E10 |
| Controlled failed DAG Run + failed task log | E11, E12, E13 |
| Selective-retry evidence / justification | E14, `docs/failure_retry_policy.md` §2 |
| Safe-rerun evidence | E15, E16, E17 |
| Dashboard connection to the DW + requirement-to-KPI traceability | `docs/superset_dashboard.md`, `docs/powerbi_dashboard.md`, E18, E19 |

## How to re-inspect a run

```bash
podman compose -f docker-compose.yaml up -d          # start the stack
# Web UI: http://localhost:8080  (user/pass: airflow/airflow) -> Grid view
# API JSON already captured in docs/evidence/runs/*.json
cat docs/evidence/runs/airflow_test_b_critical_failure_summary.json
grep -o '"exc_value":"[^"]*' docs/evidence/runs/airflow_test_b_critical_failure_log_validate_spotify_raw.txt
```
