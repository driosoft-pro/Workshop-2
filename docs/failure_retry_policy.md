# Failure, Retry, Logging and Repeatability Policy

Workshop-2, sections 6.11, 7.2 and 7.3. Implementation:
`dags/reliable_music_pipeline.py`, `src/validation.py`, `src/load.py`.

## 1. Failure policy table

| Condition | Severity / type | Pipeline response | Retry? | Justification |
| --- | --- | --- | --- | --- |
| **Critical GX rule fails at a gate** (e.g. DQ-S3 with `popularity=150`) | Deterministic data/contract | Gate task raises `ValidationGateError`; task state `failed`; all downstream tasks `upstream_failed` (blocked); evidence JSON written *before* raising | **No** (`retries=0`) | Repetition reproduces the same failure for the same input file; the failure is *data*, not infrastructure. Evidence must be surfaced, not retried. |
| Warning GX rule fails | Deterministic, non-blocking | Logged (`failed_warning_rules`), persisted in the evidence JSON, returned in the gate payload; processing continues under the documented severity policy | n/a | Documented in `docs/quality_rules.md` §1: the batch stays usable, the defect stays visible. |
| Missing required column in a source (`SourceContractError`) | Deterministic contract | Extract task fails with the exact missing column list | Bounded only (2 attempts) — then stop | A contract violation never self-heals; the bounded retry keeps a transient read glitch from failing the run while guaranteeing a fast, explicit error. |
| Source file not found / volume not mounted (`FileNotFoundError`) | Operational, possibly transient | Extract task fails naming the exact path searched (`data/raw`, `data/bad`) | Yes, 2 attempts (below) | A mount race at container start can succeed on attempt 2; 2 attempts keep the feedback loop short. |
| Database unreachable during `extract_grammys` / `load_dw` | Transient operational | Task fails with the SQLAlchemy error | Yes, 2 attempts, exponential backoff | Another attempt can succeed without changing input or code (classic transient class). |
| Prepared data violates a **critical** prepared rule (DQ-P1..P12) | Deterministic data | `validate_prepared` fails after recording **all three** prepared checkpoints (complete evidence first) → `load_dw` never starts | **No** | Blocks a bad load; retrying changes nothing. |
| Load fails mid-transaction (DB error) | Transient operational | Transaction rolls back → target keeps the previous consistent state; `etl_batch_log` unchanged for that batch | Yes, 2 attempts | Atomic replace guarantees no partial load; a retry re-runs the same atomic unit. |
| KPI query / chart failure | Mixed | `build_kpis` fails after the DW is already loaded | **1** attempt | The warehouse is valid without KPIs; one retry absorbs a transient read issue without masking a broken query. |
| Airflow service crash (scheduler/dag-processor) | Infrastructure | Task states preserved in the metadata DB; Airflow restarts the worker; interrupted tasks resume per state | orchestrator-level | States and logs are the observability contract (§3). |

## 2. Selective retry configuration (per task class)

| Task | `retries` | delay / backoff | `execution_timeout` | Rationale |
| --- | --- | --- | --- | --- |
| `extract_spotify` | **2** | 1 min, exponential, cap 10 min | 15 min | transient filesystem/volume availability; input and code unchanged between attempts |
| `extract_grammys` | **2** | 1 min, exponential, cap 10 min | 15 min | transient source-database unavailability (container warm-up) |
| `validate_spotify_raw` | **0** | – | – | deterministic GX outcome for a given file — a retry reproduces it |
| `validate_grammys_raw` | **0** | – | – | same |
| `transform_and_integrate` | **0** | – | – | deterministic given its two inputs; failures indicate a code/contract bug, not an infrastructure blip |
| `validate_prepared` | **0** | – | – | deterministic; blocking must be immediate and observable |
| `load_dw` | **2** | 1 min, exponential, cap 10 min | 30 min | transient DB failures; each attempt is an atomic replace (no partial state) |
| `build_kpis` | **1** | 1 min, exponential | 15 min | one bounded retry; DW already loaded successfully |
| DAG defaults | `retries=0`, `depends_on_past=False` | – | – | **no blanket `retries=3`** — every retry above is justified by its failure class |

Supporting guards: `max_active_runs=1` (single concurrent batch),
`dagrun_timeout=2h`, `catchup=False` (no historical backfill storms).

## 3. Logging and observability

| Question | Evidence |
| --- | --- |
| **What ran?** | DAG run id + run context logged by every task: `dag_id`, `task_id`, `run_id`, `try_number`, `logical_date` (e.g. `transform_and_integrate context={…run_id': 'test_a_success'…}`) |
| **When?** | `docs/evidence/runs/airflow_*_summary.json` (start/end/duration per task) and task logs with timestamps |
| **Did it succeed?** | Task states in the run summary (`success`×8 for Test A) plus material results: `rows=` per extract, `row_counts_after` per load, GX statistics per gate |
| **Where did it fail?** | Test B: `validate_spotify_raw=failed`, `transform_and_integrate|validate_prepared|load_dw|build_kpis=upstream_failed` (no partial load, no batch row in `etl_batch_log`) |
| **Why?** | Failed task log contains `ValidationGateError … DQ-S3(expect_column_values_to_be_between column=popularity unexpected_count=1 …)` plus the GX evidence JSON with `partial_unexpected_list=[150]` |
| **What happened next?** | Per policy: no retry for the gate (try_number stays 1), downstream skipped, run state `failed`; the corrected batch succeeds on the next manual run |

Material row counts and validation outcomes are logged at each step
(`[gx] stage=… stats=…`, `[transform] metrics=…`, `load_dw batch_id=… rows_after=…`),
so a run can be audited from logs alone.

## 4. Controlled failure (Test B) — what and why

* Trigger: manual run with `conf={"spotify_source_file": "spotify_bad.csv"}`.
* Defect: `scripts/make_bad_data.py` sets `popularity = 150` (source range is
  0–100) on one row of a copy of the source file → violates **DQ-S3 (critical)**.
* Expected and observed behaviour (run `test_b_critical_failure`, 20.1 s):

| Stage | State | Note |
| --- | --- | --- |
| `extract_spotify` | success | extraction does **not** hide source-quality problems |
| `extract_grammys`, `validate_grammys_raw` | success | Grammy branch unaffected (isolated failure) |
| `validate_spotify_raw` | **failed** | `ValidationGateError`, `failed_critical_rules=["DQ-S3"]` |
| `transform_and_integrate` → `build_kpis` | upstream_failed | downstream never executed |
| Data Warehouse | untouched | no `etl_batch_log` row for this run; counts unchanged |

## 5. Repeatability / safe rerun

**Strategy: controlled replace** (transactional `DELETE` + `INSERT` per batch,
business-key UNIQUE constraints as a backstop, `etl_batch_log` upsert keyed by
`batch_id = <dag_id>__<run_id>`).

| Evidence | Shows |
| --- | --- |
| `docs/evidence/runs/airflow_dw_counts_after_test_c.csv` | after run A **and** rerun C: 157,530 / 4,810 / 30,894 / 114 / 62 / 638 — identical, never doubled |
| `docs/evidence/runs/airflow_etl_batch_log.csv` | two batch rows (`test_a_success`, `test_c_safe_rerun`), each with the same `target_rows_after` |
| `airflow_test_c_safe_rerun_log_load_dw.txt` | `row_counts_before` = previous batch's counts, `row_counts_after` = same counts → replace, not append |
| `docs/evidence/runs/safe_rerun_run1_counts.csv` / `…_run2_counts.csv` | same guarantee at module level (identical diff) |
| DDL | `UNIQUE (track_id, track_genre, artist_sk)` and `UNIQUE (award_bk)` make an accidental append fail loudly instead of silently duplicating |

**Partially completed or failed run**: because the load is one transaction,
a crash leaves the target exactly as it was (`row_counts_before` in the next
successful run equals the last committed state). A run that fails *before*
`load_dw` writes nothing at all (Test B). `etl_batch_log` only receives rows
for committed batches, so the log never records a load that did not happen.
