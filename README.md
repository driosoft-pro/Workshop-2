# Workshop-2 — Reliable Batch Data Pipeline (Spotify × Grammy Awards)

A production-style, **reliability-first** batch pipeline: Spotify CSV + Grammy
Awards (PostgreSQL source) → two Great Expectations validation gates →
harmonization/integration → trusted dimensional Data Warehouse (PostgreSQL) →
KPIs and a Power BI dashboard, orchestrated by **Apache Airflow 3.1.8** with the
TaskFlow API.

> Reliable does not mean that nothing fails. Reliable means that failures are
> anticipated, controlled and observable — and that a rerun never corrupts the
> analytical target.

---

## 1. Problem and analytical objective

Award recognition (Grammy) and streaming catalogue performance (Spotify) live in
two incompatible sources: a file and a relational table, with no shared
identifier. The objective is a **trusted Data Warehouse** that lets analysts ask
questions that neither source can answer alone — e.g. *do Grammy-recognized
artists behave differently on Spotify, and which genres dominate among award
winners* — while making data quality a measured, gated, evidenced property of
every batch.

## 2. Analytical requirements

Full table: [`docs/analytical_requirements.md`](docs/analytical_requirements.md).

| ID | Question | Both sources needed because |
| --- | --- | --- |
| **AR1** | Do Grammy-recognized artists perform differently on Spotify than the rest of the catalogue? | recognition flag comes from Grammys, popularity/audio profile from Spotify |
| **AR2** | Which Spotify genres dominate among Grammy-recognized artists? | genre from Spotify, award signal from Grammys |
| **AR3** | How has the profile of recognized artists evolved by decade? | timeline from Grammys, artist profile from Spotify |
| **AR4** | Which artists accumulate the most awards, and how are they represented in the Spotify catalogue? | award rank from Grammys, catalogue coverage from Spotify |

## 3. Data sources

| Source | Form used by the pipeline | Rows | Notes |
| --- | --- | --- | --- |
| Spotify tracks | `data/raw/spotify_dataset.csv` (CSV) | 114,000 | 21 raw columns → **16 contract columns** extracted (`key`, `mode`, `instrumentalness`, `time_signature`, unnamed index are profiled but not loaded) |
| Grammy Awards | PostgreSQL `music_source.grammy_awards` | 4,810 | **Source preparation**: `scripts/prepare_source_db.py` imports the provided CSV (evidence `docs/evidence/runs/source_preparation.json`). This is *not* the ETL Load — the Load writes `music_dw` |

NA policy: `keep_default_na=False, na_values=[""]` — the Spotify file contains
the literal artist name `"N/A"`, which default pandas parsing would corrupt.

## 4. Pipeline architecture

[`docs/architecture.md`](docs/architecture.md)

```
spotify CSV ─ extract_spotify ─ validate_spotify_raw ─┐
                                                      ├─ transform_and_integrate ─ validate_prepared ─ load_dw ─ build_kpis
postgres   ─ extract_grammys ─ validate_grammys_raw ──┘                                     (music_dw)    (KPIs/PNG)
```

![Implemented DAG structure](docs/dag_structure.png)

8 TaskFlow tasks, both source branches observable, both gates enforced through
dependencies, interfaces exchange paths/compact metadata only.

## 5. Data profiling findings

[`notebooks/data_profiling.ipynb`](notebooks/data_profiling.ipynb)
(executed; machine summary `docs/evidence/profiling_summary.json`).

| Dimension | Key findings |
| --- | --- |
| Structure | Spotify 114,000×21 (16 in contract); Grammy 4,810×10 (9 in contract) |
| Completeness | 1 Spotify row without artist credit (0.0009%); Grammy `artist` missing in **1,840 rows (38.25%)**, `nominee` missing in 6 (0.12%), `workers` 45.5% |
| Uniqueness | 24,259 repeated `track_id`; **450 duplicate `(track_id, track_genre)`** grains; 0 fully duplicated rows; Grammy award business key unique (0 dupes) |
| Categorical | 114 genres × exactly 1,000 rows; 638 award categories; `winner` = `True` in all 4,810 rows (winners-only dataset) |
| Numerical | `popularity` 0–100 clean; 1 row `duration_ms=0`, 603 rows >10 min, 16 rows >1 h; 90 rows loudness >0 dB; 157 rows tempo ≤0; 163 `time_signature=0` |
| Temporal | awards 1958–2019, 62 distinct years, **no gaps**; `published_at` parseable 4,810/4,810 |
| Cross-source | 29,789 Spotify vs 1,636 Grammy artist keys → **531 matched keys**; 1,395 award rows matched (**29.0021%**); 90 normalized keys merge >1 display name |

## 6. Quality risks and quality rules

[`docs/quality_rules.md`](docs/quality_rules.md) — 24 rules (DQ-S1…S6,
DQ-G1…G5, DQ-P1…P12) with metric, threshold, severity, justification and AR tags.

Severity policy: **critical** → gate raises `ValidationGateError` → downstream
blocked (`upstream_failed`); **warning** → recorded, logged, batch continues.
Thresholds are engineering decisions documented per rule (e.g. DQ-S4 99% because
0.53% of real durations exceed 10 min; DQ-P11 ≥25% because the measured match
rate is 29.0021%).

## 7. Great Expectations validation design

[`docs/gx_design.md`](docs/gx_design.md) — GX 1.23.1 file-mode project in `gx/`:
5 suites ↔ 5 validation definitions ↔ 5 checkpoints, 28 expectations carrying
`meta.rule_id/severity/dimension/requirement`. Results are written as
machine-readable JSON to `docs/evidence/gx/<stage>/<stamp>_<run_id>.json`
(per-rule counts, sample unexpected values, failed rule ids).

* Raw gate: *can these data enter transformation?*
* Prepared gate: *did transformation produce load-ready data?* (runs all three
  prepared checkpoints, then applies policy)

## 8. Transformation and integration strategy

[`docs/transformation_integration.md`](docs/transformation_integration.md) —
rules **T1…T11** (drop keyless rows −1, dedupe grain −450, explode on `;`,
normalize artist key, **no value repair (T5)**, derive recognition flags,
`winner_flag`, match flags, emit integration metrics).

Integration contract: key `artist_key` (name-based — no shared ID exists),
cardinality track↔artists 1..n and award↔artist 0..1 (many-to-many across
sources), unmatched rows **measured and retained** (`is_matched_spotify=0`),
ambiguous display names merged and counted (90), documented limitations
(38.25% of award rows have no artist credit; winners-only dataset).

## 9. Dimensional model

[`docs/dimensional_model.md`](docs/dimensional_model.md), DDL
[`sql/dw_schema.sql`](sql/dw_schema.sql):

| Object | Rows | Grain |
| --- | --- | --- |
| `dim_artist` | 30,894 | `artist_bk` (normalized artist key) |
| `dim_genre` | 114 | `genre` |
| `dim_year` | 62 | `year` (natural PK) + `decade` |
| `dim_award_category` | 638 | `category` |
| `fact_track_artist` | 157,530 | track listing × performing artist |
| `fact_grammy_award` | 4,810 | year × category × nominee × artist |
| `etl_batch_log` | 1 per batch | load audit (before/after counts) |

Surrogate keys are generated inside the load transaction; business keys are
UNIQUE-constrained; unmatched awards keep `artist_sk NULL` by design.

## 10. Airflow DAG design

[`dags/reliable_music_pipeline.py`](dags/reliable_music_pipeline.py) —
`from airflow.sdk import dag, task, get_current_context`, `schedule=None`,
`max_active_runs=1`, `catchup=False`, `dagrun_timeout=2h`. Dependencies encode
the policy: transformation requires **both** raw gates; load requires the
prepared gate. Task interfaces pass paths/metadata only (no DataFrames in XCom).

## 11. Failure and retry policy

[`docs/failure_retry_policy.md`](docs/failure_retry_policy.md)

| Class | Tasks | Retry |
| --- | --- | --- |
| Transient operational (FS/DB) | `extract_spotify`, `extract_grammys`, `load_dw` | 2 attempts, 1 min exponential, 10 min cap |
| Deterministic data/contract | both raw gates, `transform_and_integrate`, `validate_prepared` | **0** — surface evidence instead |
| Post-load analytics | `build_kpis` | 1 attempt |

No blanket `retries=3`; every retry is justified by its failure class.

## 12. Successful execution evidence

Run **`test_a_success`** (Airflow 3.1.8): 8/8 tasks `success`, try=1, 61.3 s.
Artefacts: `docs/evidence/runs/airflow_test_a_success_summary.json` +
`airflow_test_a_success_log_*.txt`, GX results (E6/E7), load counts
`row_counts_after = 157,530 / 4,810 / 30,894 / 114 / 62 / 638`.

![Task states across the three reliability tests](docs/evidence/runs/airflow_task_states.png)

## 13. Controlled failure evidence (Test B)

Run **`test_b_critical_failure`** with
`conf={"spotify_source_file": "spotify_bad.csv"}` (file produced by
`scripts/make_bad_data.py`: `popularity=150` on one row):

* `extract_spotify` **success** → `validate_spotify_raw` **failed**
  (`ValidationGateError: … DQ-S3(expect_column_values_to_be_between column=popularity unexpected_count=1)`)
* `transform_and_integrate`, `validate_prepared`, `load_dw`, `build_kpis` →
  `upstream_failed` (never executed)
* Data Warehouse untouched (no `etl_batch_log` row for that run)
* GX evidence: `docs/evidence/gx/raw_spotify/20261003T032430534472_test_b_critical_failure.json`
* Failed task log: `docs/evidence/runs/airflow_test_b_critical_failure_log_validate_spotify_raw.txt`
* State matrix (with interpretation): `docs/evidence/runs/airflow_task_states.png`

## 14. Repeatability strategy

**Controlled replace** — one transaction per batch: `DELETE` + `INSERT` over the
six tables, business-key UNIQUE constraints as backstop, `etl_batch_log` upsert
keyed by `batch_id = <dag_id>__<run_id>`, sequences realigned with `setval`.
A crash rolls back completely (target keeps the previous consistent state).

Evidence (run `test_c_safe_rerun`, same input as Test A): identical row counts
before/after, `etl_batch_log` shows two committed batches with equal
`target_rows_after` (`docs/evidence/runs/airflow_dw_counts_after_test_c.csv`,
`docs/evidence/runs/airflow_etl_batch_log.csv`, and
`docs/evidence/runs/safe_rerun_run1_counts.csv` +
`docs/evidence/runs/safe_rerun_run2_counts.csv`).

## 15. Dashboard and analytical outputs

[`docs/powerbi_dashboard.md`](docs/powerbi_dashboard.md) — Power BI (PostgreSQL
`music_dw`), 4 pages for AR1–AR4, DAX measures and star-schema relationships.
Pipeline-generated artifacts (7 KPI CSVs + 4 PNG charts) live in
`docs/evidence/kpis/`; every KPI has a `-- ARn` tag in `sql/kpi_queries.sql`.

## 16. Setup and execution

### 16.1 Requirements

* Nix with flakes: `nix develop` provides Python 3.12, `uv`, PostgreSQL client
  and Podman (`flake.nix`)
* **Podman ≥ 4** (rootless) + `podman compose` / `podman-compose` — the compose
  file is adapted from the official Airflow 3.1.8 file: LocalExecutor, no
  Redis/Celery (Docker + Compose also work if you set `AIRFLOW_UID=$(id -u)`)
* optional Python ≥ 3.11 venv for local runs (`requirements.txt`)

### 16.2 Start the environment

```bash
cp .env.example .env            # review AIRFLOW_UID, ports, credentials
podman compose -f docker-compose.yaml up -d --build   # or: docker compose up -d --build
curl -s http://localhost:8080/api/v2/monitor/health    # API healthy
```

Services: `airflow-apiserver` (UI/API on **http://localhost:8080**, user
`airflow`/`airflow`), `airflow-scheduler`, `airflow-dag-processor`,
`airflow-triggerer`, `postgres` (Airflow metadata), `music-postgres`
(`music_source` + `music_dw`, host port 5432).

> Rootless Podman note: `.env` sets `AIRFLOW_UID=0` (container root maps to the
> invoking host user) and the compose file sets `HOME=/home/airflow`, so
> bind-mounted evidence stays owned by you. On Docker Desktop use
> `AIRFLOW_UID=$(id -u)` instead.

### 16.3 Source preparation (Grammy CSV → PostgreSQL)

```bash
podman compose --profile debug run --rm airflow-cli bash -c \
  'cd /opt/airflow && python -m scripts.prepare_source_db'
```

(or on the host: `MUSIC_SOURCE_DB_URL=postgresql+psycopg2://music:music@localhost:5432/music_source PYTHONPATH=. python -m scripts.prepare_source_db`)

Evidence: `docs/evidence/runs/source_preparation.json` (row-count
reconciliation 4,810 = 4,810).

### 16.4 Run the DAG

```bash
# UI: DAGs -> reliable_music_pipeline -> unpause -> Trigger DAG (Test A)
# API equivalent:
curl -s -X POST http://localhost:8080/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"airflow","password":"airflow"}'   # -> access_token
# create a run with conf {} (Test A) or {"spotify_source_file":"spotify_bad.csv"} (Test B)
podman compose --profile debug run --rm airflow-cli bash -c \
  'cd /opt/airflow && airflow dags trigger reliable_music_pipeline'
```

Expected: Test A `success` (all 8 tasks); Test B `failed` at
`validate_spotify_raw` with 4 tasks `upstream_failed`.

### 16.5 Local (host) run without Airflow

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=. MUSIC_DATA_DIR="$PWD/data" MUSIC_GX_DIR="$PWD/gx" \
       MUSIC_EVIDENCE_DIR="$PWD/docs/evidence" \
       MUSIC_SOURCE_DB_URL=postgresql+psycopg2://music:music@localhost:5432/music_source \
       MUSIC_DW_DB_URL=postgresql+psycopg2://music:music@localhost:5432/music_dw
python -m scripts.smoke_test                 # Test A: extract→gates→transform→load→KPIs
python -m scripts.make_bad_data              # create data/bad/spotify_bad.csv
python -m scripts.smoke_test --source spotify_bad.csv   # Test B: expected BLOCKED exit code 2
python -m src.validation init                # (re)build gx/ assets
python -m src.validation rules               # print the rule catalogue
```

### 16.6 Useful commands

```bash
podman compose logs -f airflow-scheduler           # scheduler logs
podman exec -it 2_music-postgres_1 psql -U music -d music_dw   # explore the DW
podman compose --profile debug run --rm airflow-cli airflow version  # 3.1.8
podman compose -f docker-compose.yaml down                     # stop (add -v to reset volumes)
```

### 16.7 Nix shell, Podman and exposed ports (Windows 11 VM → Power BI)

```bash
nix develop        # Python 3.12 + uv + postgresql + podman/podman-compose
```

The runtime is **rootless Podman** (no Docker daemon): `docker-compose.yaml` is
the official Airflow 3.1.8 file adapted for this project and is driven with
`podman compose …` (built into Podman ≥ 4) or `podman-compose`.

Both service ports are published on **`0.0.0.0`**, so a guest machine can reach
them through the host address:

| Port | Service | Typical consumer |
| --- | --- | --- |
| `5432` | `music-postgres` — `music_source` + `music_dw` | Power BI Desktop |
| `8080` | `airflow-apiserver` — UI / REST API | browser |

The host firewall must allow them: the list
`services.network.firewall.allowedTCPPorts = [ 5432 8080 ]` sits in the machine
configuration `/etc/nixos/env.nix` and is rendered by
`/etc/nixos/modules/system/networking.nix` into the nftables ruleset
(`tcp dport { 5432, 8080 } accept`). After editing that file, rebuild:

```bash
doas nixos-rebuild switch
```

Power BI Desktop inside the **Windows 11 VM** (libvirt `default` NAT, host
gateway `192.168.122.1`; on the LAN the host is `192.168.1.14`):

| Setting | Value |
| --- | --- |
| Server | `192.168.122.1,5432` (LAN: `192.168.1.14,5432`) |
| Database | `music_dw` |
| Authentication | Database — user `music`, password `music` |
| Airflow UI | `http://192.168.122.1:8080` (`airflow` / `airflow`) |

Connectivity check from the VM: `Test-NetConnection 192.168.122.1 -Port 5432`.

## 17. Repository structure

```
workshop-2/
|-- dags/reliable_music_pipeline.py     # TaskFlow DAG (workflow + policy only)
|-- src/                                # reusable logic
|   |-- config.py  extract.py  transform.py  validation.py  load.py  analytics.py
|-- gx/                                 # Great Expectations project (suites/validations/checkpoints)
|-- notebooks/data_profiling.ipynb      # executed profiling notebook
|-- sql/source_setup.sql                # Grammy source table DDL
|-- sql/dw_schema.sql                   # star schema DDL
|-- sql/db_init/01_create_dw.sql        # auto-created on container start
|-- sql/kpi_queries.sql                 # 7 KPI queries (-- ARn tags)
|-- scripts/                            # prepare_source_db, make_bad_data, smoke_test
|-- docs/                               # analytical_requirements, architecture, quality_rules,
|   |                                   # gx_design, transformation_integration, dimensional_model,
|   |                                   # failure_retry_policy, traceability_matrix,
|   |                                   # powerbi_dashboard, evidence_register
|   `-- evidence/                       # gx/, kpis/, runs/, profiling_summary.json
|-- data/{raw,work,output,bad}/         # inputs (raw committed) / generated
|-- requirements.txt  Dockerfile  docker-compose.yaml  flake.nix  .env.example  .gitignore
```

## 18. Assumptions and limitations

1. **Name-based integration**: there is no shared artist identifier; matching
   relies on normalization of display names. 1,575 award rows with a credit
   remain unmatched, and 1,840 rows have no credit at all (38.25%).
2. **Winners only**: `winner` is `True` for 4,810/4,810 rows — nomination history
   is out of scope (documented, gated by DQ-G3 domain check).
3. **Group credits** (`"A & B"`, `"(Various Artists)"`) are single keys; the
   aggregate credit is excluded from KPI-4 rankings.
4. **No value repair** (T5): out-of-range source values (603 long durations,
   1 zero duration, …) are reported, never corrected.
5. **Contract columns**: `key`, `mode`, `instrumentalness`, `time_signature`
   are profiled but not extracted — audio metadata beyond the AR1/AR3 features
   is out of scope.
6. **Batch strategy**: full replace per run (no incremental/SCD loading); safe
   for 157k-row volumes, would need partitioning at larger scale.
7. **Dashboard**: Power BI Desktop on Windows/macOS connects to PostgreSQL
   `music_dw`; the repository ships the query layer, DAX design and rendered
   charts as reproducible evidence.
