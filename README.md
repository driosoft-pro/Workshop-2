# Workshop-2 — Pipeline (Spotify × Grammy Awards)

A production-style, **reliability-first** batch pipeline: Spotify CSV + Grammy
Awards (PostgreSQL source) → two Great Expectations validation gates →
harmonization/integration → trusted dimensional Data Warehouse (PostgreSQL) →
KPIs and an **Apache Superset dashboard** (Power BI as an alternative),
orchestrated by **Apache Airflow 3.1.8** with the TaskFlow API.

> Reliable does not mean that nothing fails. Reliable means that failures are
> anticipated, controlled and observable — and that a rerun never corrupts the
> analytical target.

---

## 1. General and specific objectives

**General objective:** build a trusted Data Warehouse that integrates the Spotify
catalogue with the Grammy Awards record and delivers verifiable KPIs and a
dashboard, with measured quality, validation gates and evidence on every batch.

**Specific objectives:**

1. Extract and harmonize two incompatible sources (CSV + PostgreSQL table)
   under an explicit column contract (16 and 9 columns).
2. Validate every stage with declarative quality rules (23 rules → 28 Great
   Expectations) and **gates that block** the batch on critical severity.
3. Transform and integrate **without repairing values**: deduplicate, normalize
   keys, explode multi-valued fields and measure integration coverage instead
   of hiding it.
4. Load a **controlled transactional replace** into a dimensional model
   (4 dimensions + 2 facts + batch log), repeatable across reruns.
5. Orchestrate the flow with Airflow (dependencies, failure-class retries, logs
   and evidence) and deliver KPIs + dashboard per analytical requirement.
6. Prove it with a reproducible test suite (`tests/`, pytest).

## 2. Granularity of the analytical deliverables

The level at which each requirement is read (every KPI only aggregates
**upwards**, never downwards):

| Requirement | Reading granularity | Aggregation |
| --- | --- | --- |
| **R1** | track × genre, grouped by `is_grammy_artist` | mean (`popularity`, `energy`, `valence`), count |
| **R2** | artist's dominant Spotify genre × Grammy category | award counts, % of total |
| **R3** | decade (primary) and year (secondary) | mean popularity/energy, award and artist counts |
| **R4** | artist | sum of awards, Spotify track count, top-N=10 |
| Coverage (KPI-0) | 1 row (whole batch) | % of award rows matched and without credit |

## 3. Expected results

* `music_dw`: 4 dimensions, 2 facts, 1 bridge table and `etl_batch_log` with per-batch audit
  (before/after counts).
* **13 KPIs** (`sql/kpi_queries.sql`) exported as CSV + **4 PNG charts** in
  `docs/evidence/kpis/`, one per requirement.
* **Superset** dashboard with 21 charts across 5 requirement tabs + header row and,
  as an alternative, the Power BI pages/DAX design.
* Per-run evidence: Great Expectations JSON per stage, Airflow run summary and
  task logs, load counts, task-state matrix and retry policy.
* Current warehouse state (committed batches): `fact_track_artist` 157,530 ·
  `fact_grammy_award` 4,810 · `bridge_award_artist` 2,841 · `dim_artist` 30,989 ·
  `dim_genre` 114 · `dim_year` 62 · `dim_award_category` 638.

## 4. Problem

Award recognition (Grammy) and streaming catalogue performance (Spotify) live in
two incompatible sources: a file and a relational table, with no shared
identifier. Neither can answer alone questions like *do Grammy-recognized
artists behave differently on Spotify?* or *which genres dominate among award
winners?*. On top of that, the integration joins on **names**, with 38.25% of
award rows carrying no artist credit: quality is not a detail, it is the
condition for interpreting any number. This pipeline turns that problem into a
Data Warehouse whose quality is **measured, gated and documented**.

## 5. Analytical objective and requirements (R1–R4)

Full table with questions, expected answers and outputs:
[`docs/analytical_requirements.md`](docs/analytical_requirements.md).

| ID | Question | Both sources needed because |
| --- | --- | --- |
| **R1** | Do Grammy-recognized artists perform differently on Spotify than the rest of the catalogue? | recognition flag comes from Grammys, popularity/audio profile from Spotify |
| **R2** | Which Spotify genres dominate among Grammy-recognized artists? | genre from Spotify, award signal from Grammys |
| **R3** | How has the profile of recognized artists evolved by decade? | timeline from Grammys, artist profile from Spotify |
| **R4** | Which artists accumulate the most awards, and how are they represented in the Spotify catalogue? | award rank from Grammys, catalogue coverage from Spotify |

Requirements are the **traceability tag** across all layers:
`RULES[*].requirement` (`src/validation.py`), `meta.requirement` on every GX
expectation, the `-- Rn` comment on each KPI SQL and the `[Rn]` label on each
dashboard chart.

## 6. Alignment

| Course dimension | How it is met here |
| --- | --- |
| Batch pipeline | 8 TaskFlow tasks, manual/UI-triggered run, `dagrun_timeout=2h` |
| Quality as a measured property | 34 rules with metric/threshold/severity → 40 GX expectations → 2 blocking gates |
| Delivery confidence | failure-class retries, per-task logs, transactional `etl_batch_log`, safe rerun |
| Dimensional modelling | star schema with declared grains, bridge table, and unique business keys |
| Analytics and BI | 13 KPIs tied to R1–R4 + Superset dashboard (21 charts) and Power BI (alternative) |
| Reproducibility | Nix environment + compose (Podman/Docker), `run.sh`/`run.bat`, pytest suite (79 tests), versioned evidence |

## 7. Data sources

| Source | Form used by the pipeline | Rows | Notes |
| --- | --- | --- | --- |
| Spotify tracks | `data/raw/spotify_dataset.csv` (CSV) | 114,000 | 21 raw columns → **22 contract columns** extracted (`danceability, acousticness, speechiness, loudness, tempo, explicit` added to contract; unnamed index excluded) |
| Grammy Awards | PostgreSQL `music_source.grammy_awards` | 4,810 | **Source preparation**: `scripts/prepare_source_db.py` imports the provided CSV (evidence `docs/evidence/runs/source_preparation.json`, 4,810 = 4,810). This is *not* the ETL Load — the Load writes `music_dw` |

NA policy: `keep_default_na=False, na_values=[""]` — the file contains literal
artist components `N/A` (2 rows) that default pandas parsing would turn into
NaN. The column contract is asserted by tests (`tests/test_extract_contract.py`).

## 8. Profiling and quality matrices (Python + GX + Airflow)

**Profiling** (executed):
[`notebooks/data_profiling.ipynb`](notebooks/data_profiling.ipynb) — machine
summary in `docs/evidence/profiling_summary.json`.

| Dimension | Key findings |
| --- | --- |
| Structure | Spotify 114,000×21 (22 in contract); Grammy 4,810×10 (9 in contract) |
| Completeness | 1 Spotify row without artist credit (0.0009%); Grammy `artist` missing in **1,840 rows (38.25%)**, `nominee` missing in 6 (0.12%), `workers` 45.5% |
| Uniqueness | 24,259 repeated `track_id`; **450 duplicate `(track_id, track_genre)`** grains; 0 fully duplicated rows; Grammy award business key unique (0 dupes) |
| Categorical | 114 genres × exactly 1,000 rows (100% mapped into 12 genre families); 638 raw award categories (579 cleaned, 14 standard families); `winner` = `True` in all 4,810 rows |
| Numerical | `popularity` 0–100 clean (14.1% zero-popularity flagged); 1 row `duration_ms=0`, 603 rows >10 min, 16 rows >1 h; 90 rows loudness >0 dB; 157 rows tempo ≤0; 163 `time_signature=0` |
| Temporal | awards 1958–2019, 62 distinct years, **no gaps**; `published_at` parseable 4,810/4,810 |
| Cross-source | T12 Matching cascade: **52.49% overall match rate** (2,525/4,810 award rows); **29.42% strict** (1,415 exact); 704 recovered via workers; 344 via credit split; 62 via nominee; **2,841 bridge rows**; 26.13% song confirmation rate |

**Risk → rule → expectation → gate matrix** (four layers):

1. **Risks** with observed metric and justification:
   [`docs/quality_rules.md`](docs/quality_rules.md) (profiling → risk → severity
   → requirement).
2. **Executable rules** in Python (`RULES` in `src/validation.py`, **34 rules**: DQ-S1…S7
   schema/contract, DQ-G1…G11 business integrity/cascade/bridge/families, DQ-P1…P16 profiling/thresholds),
   consumed by the `enforce_policy`.
3. **Great Expectations**: 6 suites ↔ 6 validation definitions ↔ 6 checkpoints,
   **40 expectations** carrying
   `meta.rule_id/severity/dimension/requirement`
   ([`docs/gx_design.md`](docs/gx_design.md)).
4. **Airflow gates**: `validate_spotify_raw` and `validate_grammys_raw` (*can
   these data enter transformation?*) and `validate_prepared` (*can it be
   loaded?*). Critical severity → `ValidationGateError` → downstream
   `upstream_failed`; warning → recorded, batch continues.

## 9. Traceability

End-to-end chain (requirement → risk → rule → expectation → transformation →
DW → KPI → dashboard) materialized in
[`docs/traceability_matrix.md`](docs/traceability_matrix.md):

* `RULES[*].requirement` in `src/validation.py` → `R1`–`R4` tags
* `meta.rule_id` / `meta.severity` per GX expectation → `docs/evidence/gx/…`
* `T1..T11` with a rationale column → `docs/transformation_integration.md`
* `-- Rn` comments in `sql/kpi_queries.sql` → CSVs in `docs/evidence/kpis/`
* `[Rn]` label per chart → `docs/superset_dashboard.md` (Power BI:
  `docs/powerbi_dashboard.md`)

## 10. Preparation strategy and structural corrections

[`docs/transformation_integration.md`](docs/transformation_integration.md) —
rules **T1…T11**: drop keyless rows (−1), dedupe grain (−450), explode `artists`
on `;`, normalize the artist key (case, spacing, punctuation), **no value repair
(T5)**, derive recognition flags, `winner_flag` and match flags, emit
integration metrics.

Structural corrections applied (metrics are never “fixed”, data shape is):

| Correction | Effect |
| --- | --- |
| Deduplication `(track_id, track_genre)` | 450 redundant rows out of the fact |
| Explode of `artists` | track↔artists cardinality 1..n (157,530 listings) |
| Artist name normalization | stable integration key `artist_key` (90 display names merged) |
| Explicit `winner_flag` | a winners-only dataset is never read as “candidates” |
| Surrogate keys generated inside the transaction | no cross-run leaks; sequences realigned with `setval` |

Integration contract: key `artist_key` (name-based — no shared ID exists),
award↔artist cardinality 0..1, unmatched rows **measured and retained**
(`is_matched_spotify=0`), documented limitations (38.25% with no credit;
winners-only dataset).

## 11. Declared grain

| Object | Declared grain | Business key |
| --- | --- | --- |
| `fact_track_artist` | track listing × genre × performing artist | `(track_id, track_genre, artist_sk)` (UNIQUE) |
| `fact_grammy_award` | year × category × nominee × artist | `award_bk` (UNIQUE, normalized) |
| `dim_artist` | artist | `artist_bk` |
| `dim_genre` | Spotify genre | `genre` |
| `dim_year` | year (natural PK) + derived `decade` | `year` |
| `dim_award_category` | award category | `category` |
| `etl_batch_log` | one row per committed batch | `batch_id = <dag_id>__<run_id>` |

The finest level at which R1–R4 measures are consistent is track × genre ×
artist; every KPI aggregates upward from there.

## 12. Dimensional model

[`docs/dimensional_model.md`](docs/dimensional_model.md) ·
DDL [`sql/dw_schema.sql`](sql/dw_schema.sql) · auto-created by
`sql/db_init/01_create_dw.sql` when `music-postgres` starts.

```mermaid
erDiagram
    dim_artist ||--o{ fact_track_artist : "artist_sk"
    dim_genre ||--o{ fact_track_artist : "genre_sk"
    dim_artist ||--o{ fact_grammy_award : "artist_sk primary, nullable"
    fact_grammy_award ||--o{ bridge_award_artist : grammy_award_sk
    dim_artist ||--o{ bridge_award_artist : artist_sk
    dim_year ||--o{ fact_grammy_award : "year_sk"
    dim_award_category ||--o{ fact_grammy_award : "category_sk"

    dim_artist {
        bigint artist_sk PK
        text artist_bk UK "normalized name key"
        text artist_display_name
        bool from_spotify
        bool from_grammy
        int grammy_award_count
        int spotify_track_count
        text dominant_genre "NEW T16"
        text dominant_genre_family "NEW T16"
        int n_genres "NEW T16"
        bool genre_tie "NEW T16"
    }
    dim_genre {
        bigint genre_sk PK
        text genre UK
        text genre_family "NEW T14"
    }
    dim_year {
        int year_sk PK
        int year UK
        int decade
    }
    dim_award_category {
        bigint category_sk PK
        text category UK
        text category_clean "NEW T13"
        text category_family "NEW T13"
    }
    fact_track_artist {
        bigint track_artist_sk PK
        text track_id
        text track_genre
        bigint artist_sk FK
        bigint genre_sk FK
        text track_name
        text album_name
        int popularity
        bigint duration_ms
        float energy
        float valence
        int artist_position
        int artist_total
        int is_grammy_artist "0/1"
        int artist_grammy_awards
        text song_key "NEW T15"
        int is_primary_song "NEW T15"
        int is_zero_popularity "NEW T15"
        int is_outlier_duration "NEW T15"
        int is_outlier_loudness "NEW T15"
        int is_outlier_tempo "NEW T15"
        float danceability "audio feature (raw contract 22)"
        float acousticness "audio feature (raw contract 22)"
        float speechiness "audio feature (raw contract 22)"
        float loudness "audio feature (raw contract 22)"
        float tempo "audio feature (raw contract 22)"
        bool explicit "raw contract 22"
        text batch_id
        timestamptz loaded_at
    }
    fact_grammy_award {
        bigint grammy_award_sk PK
        text award_bk UK "year x category x nominee x artist"
        bigint artist_sk FK "NULL when unmatched"
        int year_sk FK
        bigint category_sk FK
        text title
        text nominee
        text artist_credit
        text workers
        bool winner
        int winner_flag "0/1"
        int is_matched_spotify "0/1"
        int is_matched_strict "NEW T12"
        int is_song_confirmed "NEW T12"
        text artist_source "NEW T12"
        text match_method "NEW T12"
        int credit_artist_count "NEW T12"
        int spotify_track_count
        int award_count
        text batch_id
        timestamptz loaded_at
    }
    bridge_award_artist {
        bigint grammy_award_sk FK
        bigint artist_sk FK
        int artist_position
        text match_method
        text batch_id
        timestamptz loaded_at
    }
    etl_batch_log {
        text batch_id PK
        text dag_id
        text run_id
        text strategy
        jsonb target_rows_before
        jsonb target_rows_after
        text status
        timestamptz started_at
        timestamptz finished_at
        text notes
    }
```

Row counts: `fact_track_artist` 157,530 · `fact_grammy_award` 4,810 ·
`bridge_award_artist` 2,841 · `dim_artist` 30,989 · `dim_genre` 114 ·
`dim_year` 62 · `dim_award_category` 638. Surrogate keys are generated inside the load
transaction; business keys are UNIQUE-constrained; unmatched awards keep
`artist_sk NULL` by design.

## 13. ETL pipeline, gates and orchestration

[`docs/architecture.md`](docs/architecture.md) ·
[`dags/reliable_music_pipeline.py`](dags/reliable_music_pipeline.py)

```
spotify CSV ─ extract_spotify ─ validate_spotify_raw ─┐
                                                      ├─ transform_and_integrate ─ validate_prepared ─ load_dw ─ build_kpis
postgres   ─ extract_grammys ─ validate_grammys_raw ──┘                                     (music_dw)    (KPIs/PNG)
             transform_and_integrate: +bridge, flags, match report   validate_prepared: +DQ-G6… rules
```

![Implemented DAG structure](docs/dag_structure.png)

* 8 TaskFlow tasks (`from airflow.sdk import dag, task, get_current_context`),
  `schedule=None`, `max_active_runs=1`, `catchup=False`, `dagrun_timeout=2h`.
* Dependencies **encode the policy**: transformation requires **both** raw
  gates; load requires the prepared gate. Interfaces exchange paths/compact
  metadata only (no DataFrames in XCom).
* Reusable logic lives in `src/` (extract, transform, validation, load,
  analytics): the DAG only orchestrates.

**Failures and retries**
([`docs/failure_retry_policy.md`](docs/failure_retry_policy.md)):

| Class | Tasks | Retry |
| --- | --- | --- |
| Transient operational (FS/DB) | `extract_spotify`, `extract_grammys`, `load_dw` | 2 attempts, 1 min exponential, 10 min cap |
| Deterministic data/contract | both raw gates, `transform_and_integrate`, `validate_prepared` | **0** — surface evidence instead |
| Post-load analytics | `build_kpis` | 1 attempt |

No blanket `retries=3`; every retry is justified by its failure class.

**Repeatability** — controlled replace: one transaction per batch (`DELETE` +
`INSERT` over the six tables, business-key UNIQUE constraints as backstop,
`etl_batch_log` upsert keyed by `batch_id = <dag_id>__<run_id>`, sequences
realigned with `setval`). A crash rolls back completely; the target keeps its
previous state.

## 14. Requirements → model → KPIs

| Req. | Model tables | KPI SQL (`sql/kpi_queries.sql`) | Superset chart |
| --- | --- | --- | --- |
| coverage | both facts + `etl_batch_log` | `kpi_0_integration_coverage`, `kpi_0_coverage_by_method`, `kpi_0_coverage_by_decade` | Header + Quality tabs |
| **R1** | `fact_track_artist` (+ `dim_genre`, `dim_year`) | `kpi_1_popularity_by_grammy_recognition`, `kpi_1_artist_level`, `kpi_1_within_genre_diff` | R1 – Popularity (4 charts) |
| **R2** | `fact_grammy_award` + `fact_track_artist` + bridge | `kpi_2_awards_by_dominant_genre`, `kpi_2_heatmap` | R2 – Awards by genre & family heatmap |
| **R3** | `fact_grammy_award` + `dim_year` + `fact_track_artist` | `kpi_3_awards_and_profile_by_decade`, `kpi_3_awards_per_year`, `kpi_3_awards_by_family_decade` | R3 – Decades, series and audio trends |
| **R4** | `fact_grammy_award` + `dim_artist` + bridge | `kpi_4_top_awarded_artists_on_spotify`, `kpi_4_top_awarded_all` | R4 – Top awarded artists on Spotify and all |

The queries also run outside Airflow (`python -m scripts.smoke_test`);
`tests/test_sql_and_schema.py` asserts each query name, its `-- Rn` tag and the
existence of every DDL object.

## 15. Quality rules, Great Expectations and validation summary

**34 rules** (DQ-S1…S7 schema/contract · DQ-G1…G11 business integrity/cascade/bridge · DQ-P1…P16
profiling/rates) with metric, threshold, severity, justification and requirement tag:
[`docs/quality_rules.md`](docs/quality_rules.md).

GX design ([`docs/gx_design.md`](docs/gx_design.md)): a 1.23.1 file-mode project
in `gx/` — 6 suites ↔ 6 validation definitions ↔ 6 checkpoints, **40
expectations** with `meta.rule_id/severity/dimension/requirement`. Results are
written as machine-readable JSON to
`docs/evidence/gx/<stage>/<stamp>_<run_id>.json` (per-rule counts, sample
unexpected values, failed rule ids).

**Validation summary per run:**

| Run | Result |
| --- | --- |
| Test A (`test_a_success`) | 8/8 tasks `success`, try=1, 61.3 s; counts `157,530 / 4,810 / 30,989 / 114 / 62 / 638 / 2,841 bridge` (`docs/evidence/runs/`) |
| Test B (`test_b_critical_failure`) | `extract_spotify` success → `validate_spotify_raw` **failed** (`ValidationGateError … DQ-S3 … unexpected_count=1`); 4 tasks `upstream_failed`; warehouse untouched (no `etl_batch_log` row) |
| Test C (`test_c_safe_rerun`) | same input as Test A: identical counts before/after, two committed batches with equal `target_rows_after` |

![Task states across the three reliability tests](docs/evidence/runs/airflow_task_states.png)

**Automated tests** (`tests/`, `pytest.ini`, `integration` marker):
**79 tests** — 75 offline (rule catalogue, GX consistency, transform over
synthetic CSVs, extraction contract, KPI/DDL, validation gate, DAG DagBag,
cascade match, mappings, flags/primary song, dominant genre,
Superset bootstrap contract) + 4 integration tests that skip automatically when
no database is reachable.

```bash
./run.sh test     # or: nix develop -c python -m pytest
```

## 16. Business intelligence: Superset (primary) and Power BI (alternative)

**Apache Superset is the primary BI layer** and it is automated in the repo:

| Element | Value |
| --- | --- |
| URL / login | `http://localhost:8088` — `admin` / `admin` |
| Connection | virtual datasets, SQL over `music_dw` (PostgreSQL on `music-postgres:5432`) |
| Objects | 1 database, **14 datasets** (built from `sql/kpi_queries.sql` + `etl_batch_log`), **21 charts**, **1 dashboard** (`Workshop-2 – KPIs (R1-R4)`, published) across 5 requirement tabs + Header row |
| Bootstrap | `./run.sh superset` → `scripts/superset_bootstrap.py` (idempotent; validates every query through the Superset API) |
| Documentation | [`docs/superset_dashboard.md`](docs/superset_dashboard.md) |

Because the datasets are *virtual*, each chart reflects the warehouse state
after the latest DAG run: refreshing means rerunning the pipeline — there is no
extract to refresh. Chart-by-chart detail (type, requirement, validated rows)
and the analytical reading live in the document above.

**Power BI as an alternative**
([`docs/powerbi_dashboard.md`](docs/powerbi_dashboard.md)): the same 4 pages
(one per requirement), DAX measures and relationships over the same `music_dw`;
connected from the Windows 11 VM (§18.3). Both layers are interchangeable since
they consume the same KPIs.

Pipeline-generated artifacts (13 CSVs + 4 PNGs) live in `docs/evidence/kpis/`.

## 17. Architecture, outputs and evidence

| Layer | Implementation | Location |
| --- | --- | --- |
| Orchestration | Airflow 3.1.8, TaskFlow, LocalExecutor | `dags/reliable_music_pipeline.py`, `docker-compose.yaml` |
| Logic | extract / transform / validation / load / analytics | `src/*.py` |
| Validation | Great Expectations 1.23.1, 6 suites / 40 expectations, 2 gates | `gx/`, `src/validation.py` |
| Grammy source | PostgreSQL 16 `music_source` | `sql/source_setup.sql`, `scripts/prepare_source_db.py` |
| Warehouse | PostgreSQL 16 `music_dw` (star schema + bridge) | `sql/dw_schema.sql`, `src/load.py` |
| Analytics | 13 KPI queries + pandas/matplotlib | `sql/kpi_queries.sql`, `src/analytics.py` |
| BI | **Apache Superset 4.1.4** (primary) · Power BI (alternative) | `scripts/superset_bootstrap.py`, `docs/superset_dashboard.md`, `docs/powerbi_dashboard.md` |
| Evidence | GX JSON, run summaries, KPI CSV/PNG, task logs | `docs/evidence/` |
| Verification | pytest (79) + `scripts/smoke_test.py` | `tests/`, `pytest.ini` |

Registered evidence: [`docs/evidence_register.md`](docs/evidence_register.md)
(IDs E1–E21 → artefact → claim → report section).

## 18. How to use the repository

### 18.1 Requirements

* Nix with flakes: `nix develop` provides Python 3.12, `uv`, PostgreSQL client
  and Podman (`flake.nix`); `requirements.txt` (+ `requirements-dev.txt` for
  pytest)
* **Podman ≥ 4** (rootless) with `podman compose`/`podman-compose`, or Docker +
  Compose; the compose file is adapted from the official Airflow 3.1.8 file
  (LocalExecutor, no Redis/Celery)

### 18.2 Clone and start the project

```bash
git clone git@github.com:driosoft-pro/Workshop-2.git   # or HTTPS
cd Workshop-2
cp .env.example .env                # review AIRFLOW_UID, ports, credentials
./run.sh up                         # frees ports + stack + source prep + Superset
./run.sh test                       # 79 tests (unit + integration)
./run.sh trigger                    # DAG Test A → 8/8 success
```

`./run.sh up` first runs `./run.sh ports`: it frees the ports this project
needs (5432, 8080, 8088) if another project holds them, and only then starts
the stack. Quick verification:

```bash
./run.sh status    # containers + URLs
./run.sh urls      # URLs only
# Airflow     http://localhost:8080  (airflow / airflow)
# Superset    http://localhost:8088  (admin / admin)
# PostgreSQL  localhost:5432         (music / music)
```

Optional (only if you do not use Nix): `python -m venv .venv && pip install -r
requirements.txt`.

### 18.3 `run.sh` / `run.bat` (single entry point)

```bash
./run.sh up            # frees ports + compose up -d --build + source prep + Superset bootstrap
./run.sh ports         # checks active containers/ports and stops foreign ones
./run.sh down          # stops ALL project services (volumes intact)
./run.sh stop          # alias of down
./run.sh trigger       # DAG Test A (8/8 success)
./run.sh trigger-bad   # creates data/bad/spotify_bad.csv and runs Test B
./run.sh test          # pytest (unit + integration)
./run.sh status        # containers and URLs
./run.sh superset      # rerun the Superset bootstrap (idempotent)
./run.sh logs          # scheduler logs
./run.sh reset         # down + drops volumes (full reset)
./run.sh smoke         # local pipeline without Airflow
```

`ports` walks the running containers of **podman or docker**, finds who
publishes 5432/8080/8088, **automatically stops** the ones that do not belong
to this project and warns when the port is held by a non-container process
(that one must be freed manually). Add extra ports with `EXTRA_PORTS="9000"`.

On Windows: `run.bat up`, `run.bat ports`, `run.bat test`, `run.bat trigger`, …
(`run.bat help`). Commands use `podman compose` when available and fall back to
`docker compose`.

### 18.4 Services, ports and clients (Windows 11 VM)

| Port | Service | Typical consumer |
| --- | --- | --- |
| `8080` | `airflow-apiserver` — UI/API (`airflow`/`airflow`) | browser |
| `8088` | `superset` — UI (`admin`/`admin`) | browser (primary BI) |
| `5432` | `music-postgres` — `music_source` + `music_dw` | Superset / Power BI Desktop |

Ports are published on **`0.0.0.0`**, so a guest machine reaches them through
the host address. Firewall list in the NixOS machine configuration
(`/etc/nixos/env.nix`, `allowedTCPPorts = [ 5432 8080 8088 ]`; rebuild with
`doas nixos-rebuild switch`).

Power BI Desktop inside the **Windows 11 VM** (libvirt `default` NAT, host
gateway `192.168.122.1`; on the LAN `192.168.1.14`):

| Setting | Value |
| --- | --- |
| Server | `192.168.122.1,5432` (LAN: `192.168.1.14,5432`) |
| Database | `music_dw` · user `music` / password `music` |
| Superset | `http://192.168.122.1:8088` (`admin`/`admin`) |
| Airflow | `http://192.168.122.1:8080` (`airflow`/`airflow`) |

Connectivity check from the VM: `Test-NetConnection 192.168.122.1 -Port 5432`.

### 18.5 Connecting with DBeaver (browsing `music_dw`)

[DBeaver Community](https://dbeaver.io/download/) (free) with the PostgreSQL
driver it ships. **New connection → PostgreSQL**:

| Setting | Value (NixOS host) | Value (from the Windows 11 VM) |
| --- | --- | --- |
| Server | `localhost` | `192.168.122.1` (LAN: `192.168.1.14`) |
| Port | `5432` | `5432` |
| Database | `music_dw` | same |
| User | `music` | same |
| Password | `music` | same |
| SSL off (optional) | *Main* tab → uncheck *Use SSL* | same |

Additional databases on the same server (same user/port):

| Database | Contents |
| --- | --- |
| `music_dw` | star schema: `dim_*`, `fact_*`, `etl_batch_log` |
| `music_source` | source table `grammy_awards` (4,810 rows) |
| `superset` | Superset metadata (do not modify) |

Verification in the DBeaver SQL console (must return `157530`):

```sql
select count(*) from fact_track_artist;              -- 157530
select count(*) from fact_grammy_award;              -- 4810
select * from etl_batch_log order by started_at desc limit 5;
select track_id, track_name, popularity              -- top R1 (Grammy artists)
  from fact_track_artist
 where is_grammy_artist = 1
 order by popularity desc limit 10;
```

If the connection fails with *Connection refused*: port 5432 is held by another
project — run `./run.sh ports` (or `./run.sh status` to see the mapping) and
retry. From the VM: `Test-NetConnection 192.168.122.1 -Port 5432`.

### 18.6 Manual run (without `run.sh`)

```bash
cp .env.example .env                          # review AIRFLOW_UID, ports, credentials
podman compose -f docker-compose.yaml up -d --build
podman compose exec -T airflow-apiserver python -m scripts.prepare_source_db
podman compose exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline
podman compose exec -T superset python /app/scripts/superset_bootstrap.py
curl -s http://localhost:8080/api/v2/monitor/health
```

### 18.7 Local (host) run without Airflow

```bash
export PYTHONPATH=. MUSIC_DATA_DIR="$PWD/data" MUSIC_GX_DIR="$PWD/gx" \
       MUSIC_EVIDENCE_DIR="$PWD/docs/evidence" \
       MUSIC_SOURCE_DB_URL=postgresql+psycopg2://music:music@localhost:5432/music_source \
       MUSIC_DW_DB_URL=postgresql+psycopg2://music:music@localhost:5432/music_dw
python -m scripts.smoke_test                          # full Test A
python -m scripts.make_bad_data                       # creates data/bad/spotify_bad.csv
python -m scripts.smoke_test --source spotify_bad.csv # Test B: expected BLOCKED exit code 2
python -m src.validation init                         # (re)build gx/ assets
python -m src.validation rules                        # print the 23-rule catalogue
```

### 18.8 Repository structure

```
workshop-2/
|-- run.sh  run.bat                     # single entry point (up/ports/down/test/trigger/superset/…)
|-- dags/reliable_music_pipeline.py     # TaskFlow DAG (workflow + policy only)
|-- src/                                # reusable logic
|   |-- config.py  extract.py  transform.py  validation.py  load.py  analytics.py
|-- tests/                              # pytest: offline unit + integration (marker)
|-- gx/                                 # Great Expectations project (suites/validations/checkpoints)
|-- notebooks/data_profiling.ipynb      # executed profiling notebook
|-- sql/source_setup.sql  dw_schema.sql # source and star schema DDL
|-- sql/db_init/01_create_dw.sql        # auto-created on music-postgres start
|-- sql/db_init/02_create_superset.sql  # Superset metadata database
|-- sql/kpi_queries.sql                 # 7 KPI queries (-- Rn tags)
|-- scripts/                            # prepare_source_db, make_bad_data, smoke_test,
|   |                                   # superset_bootstrap, superset_create_metadata_db
|-- config/superset_config.py  Dockerfile.superset
|-- docs/                               # analytical_requirements, architecture, quality_rules,
|   |                                   # gx_design, transformation_integration, dimensional_model,
|   |                                   # failure_retry_policy, traceability_matrix,
|   |                                   # superset_dashboard, powerbi_dashboard, evidence_register
|   `-- evidence/                       # gx/, kpis/, runs/, profiling_summary.json
|-- data/{raw,work,output,bad}/         # inputs (raw committed) / generated
|-- requirements.txt  requirements-dev.txt  pytest.ini
|-- docker-compose.yaml  flake.nix  .env.example  .gitignore
```

### 18.9 Assumptions and limitations

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
   are profiled but not extracted — audio metadata beyond the R1/R3 features
   is out of scope.
6. **Batch strategy**: full replace per run (no incremental/SCD loading); safe
   for 157k-row volumes, would need partitioning at larger scale.
7. **BI**: Superset is the primary layer (automated); Power BI Desktop remains
   an alternative for the workstation standard.
