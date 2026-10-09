# Analytical Product: KPIs and Apache Superset Dashboard

Workshop-2, section on *inteligencia de negocios*. **Apache Superset is the
primary BI layer** of this project: it connects directly to the analytical
Data Warehouse (`music_dw`) and renders one chart per analytical requirement
(R1–R4) plus a data-quality coverage panel. Power BI remains supported as an
alternative client ([`powerbi_dashboard.md`](powerbi_dashboard.md)).

## 1. Connection

| Setting | Value |
| --- | --- |
| URL | `http://localhost:8088` (published on `0.0.0.0`, so the Windows 11 VM can use `http://192.168.1.14:8088`) |
| Login | `admin` / `admin` (`SUPERSET_ADMIN_USER` / `SUPERSET_ADMIN_PASSWORD` in `.env`) |
| Database connection | `music_dw` → `postgresql+psycopg2://music:music@music-postgres:5432/music_dw` |
| Metadata database | PostgreSQL `superset` (same server, `music-postgres`) |
| Configuration | `config/superset_config.py` mounted at `/app/pythonpath/superset_config.py` |
| Image | `Dockerfile.superset` (`apache/superset:4.1.4` + `psycopg2-binary`) |

Services in [`docker-compose.yaml`](../docker-compose.yaml):

* `superset-init` (one-shot): creates the metadata DB → `superset db upgrade`
  → admin user → `superset init`
* `superset`: UI/API on port 8088, health endpoint `/health`
* `superset-bootstrap` (profile `debug`): runs `scripts/superset_bootstrap.py`

## 2. Bootstrap (datasets + charts + dashboard)

```bash
./run.sh superset
# equivalent:
podman compose exec -T superset python /app/scripts/superset_bootstrap.py
```

The script is **idempotent**: it creates or updates every object and then
executes each chart query through the Superset API as a smoke test (a KPI SQL
that fails makes the script exit non-zero).

Objects created:

| Kind | Name | Source |
| --- | --- | --- |
| Database | `music_dw` | `config/superset_config.py` / `SUPERSET_DW_SQLALCHEMY_URI` |
| Datasets (15, virtual) | `kpi_0_integration_coverage`, `kpi_0_coverage_by_method`, `kpi_0_coverage_by_tier`, `kpi_0_coverage_by_decade`, `kpi_1_popularity_by_grammy_recognition`, `kpi_1_artist_level`, `kpi_1_within_genre_diff`, `kpi_2_awards_by_dominant_genre`, `kpi_2_heatmap`, `kpi_3_awards_and_profile_by_decade`, `kpi_3_awards_per_year`, `kpi_3_awards_by_family_decade`, `kpi_4_top_awarded_artists_on_spotify`, `kpi_4_top_awarded_all`, `etl_batch_log` | SQL extracted from [`sql/kpi_queries.sql`](../sql/kpi_queries.sql) by the `-- @name:` markers + `etl_batch_log` |
| Metrics | one aggregate per charted column (`SUM`/`AVG`/`MAX`/`MIN`) | `DATASET_SPECS` in `scripts/superset_bootstrap.py` |
| Charts (22) | see §3 | `CHART_SPECS` in `scripts/superset_bootstrap.py` |
| Dashboard | `Workshop-2 - KPIs (R1-R4)` | published, contains all 22 charts across Header and 5 Tabs |

## 3. Charts per requirement and dashboard layout

| Chart | Req. | Viz type (fallback) | Dataset | Tab / Location |
| --- | --- | --- | --- | --- |
| [Header] Coverage Enriched % | R1, R2, R3 | `big_number_total` (`table`) | `kpi_0_integration_coverage` | Header |
| [Header] Coverage Strict % | R1, R2, R3 | `big_number_total` (`table`) | `kpi_0_integration_coverage` | Header |
| [Header] Grammy Artists Matched | R3 | `big_number_total` (`table`) | `kpi_3_awards_and_profile_by_decade` | Header |
| [Header] Awards Loaded | R4 | `big_number_total` (`table`) | `etl_batch_log` | Header |
| [R1] Artist Popularity Distribution | R1 | `box_plot` (`table`) | `kpi_1_artist_level` | Tab R1 |
| [R1] Audio Features: Grammy vs Non-Grammy | R1 | `radar` (`table`) | `kpi_1_popularity_by_grammy_recognition` | Tab R1 |
| [R1] Popularity Difference within Genre Family | R1, R2 | `dist_bar` (`table`) | `kpi_1_within_genre_diff` | Tab R1 |
| [R1] Popularity Summary Table | R1 | `table` | `kpi_1_popularity_by_grammy_recognition` | Tab R1 |
| [R2] Genre Family vs Category Family Heatmap | R2 | `heatmap` (`table`) | `kpi_2_heatmap` | Tab R2 |
| [R2] Awards per 100 Artists by Dominant Genre Family | R2 | `dist_bar` (`table`) | `kpi_2_awards_by_dominant_genre` | Tab R2 |
| [R3] Energy Trend by Decade | R3 | `echarts_timeseries_line` (`table`) | `kpi_3_awards_and_profile_by_decade` | Tab R3 |
| [R3] Valence Trend by Decade | R3 | `echarts_timeseries_line` (`table`) | `kpi_3_awards_and_profile_by_decade` | Tab R3 |
| [R3] Danceability Trend by Decade | R3 | `echarts_timeseries_line` (`table`) | `kpi_3_awards_and_profile_by_decade` | Tab R3 |
| [R3] Awards by Category Family per Decade | R3 | `dist_bar` (`table`) | `kpi_3_awards_by_family_decade` | Tab R3 |
| [R3] Matched Share by Decade | R3 | `echarts_timeseries_line` (`table`) | `kpi_3_awards_and_profile_by_decade` | Tab R3 |
| [R4] Top-10 Awarded Artists on Spotify | R4 | `dist_bar` (`table`) | `kpi_4_top_awarded_artists_on_spotify` | Tab R4 |
| [R4] Top Awarded Artists Overall | R4 | `table` | `kpi_4_top_awarded_all` | Tab R4 |
| [R4] Top Artists Absent from Spotify | R4 | `table` | `kpi_4_top_awarded_all` | Tab R4 |
| [Quality] Awards by recognition tier | R1, R2, R3 | `echarts_timeseries_bar` (`table`) | `kpi_0_coverage_by_tier` | Tab Quality |
| [Quality] Match Method Distribution | R1, R2, R3 | `pie` (`table`) | `kpi_0_coverage_by_method` | Tab Quality |
| [Quality] Coverage Trend by Decade | R1, R2, R3 | `echarts_timeseries_line` (`table`) | `kpi_0_coverage_by_decade` | Tab Quality |
| [Quality] Last ETL Batches | R4 | `table` | `etl_batch_log` | Tab Quality |

Each chart carries the requirement tag in its description (`[R1] …`), the same
tag used by `sql/kpi_queries.sql` (`-- Rn`) and by `RULES[*].requirement` in
`src/validation.py`.

## 4. Load options and analytical interpretation

* **Load mode**: the datasets are *virtual* (SQL over `music_dw`) — Superset
  never copies data, so every chart reflects the state of the warehouse
  **after the latest DAG run**. Refresh = re-run the DAG (`./run.sh trigger`),
  no extract/refresh step exists in Superset.
* **Row limits**: charts cap at 10–100 rows by design (top-N views); the full
  result of every KPI is also exported as CSV in `docs/evidence/kpis/`.
* **Interpretation** (summary of the executed batch):
  * R1 — average popularity *Grammy-recognized* ≈ 31.6 vs *other* ≈ 33.6:
    recognition does not imply higher current popularity; the audio profile
    (energy/valence) is the differentiator.
  * R2 — genres such as `blues` (103 awards) and `country` (99) dominate the
    recognized population; award share is concentrated in few genres.
  * R3 — award volume grows from 63 (1950s) to 1,210 (2010s) while average
    artist popularity rises from ~18 to ~36: the recognized population is
    renewed and increasingly present on Spotify.
  * R4 — top awarded artists inside the catalogue (e.g. Aretha Franklin,
    16 awards / 15 Spotify tracks) expose coverage gaps between award depth
    and catalogue size.
  * KPI-0 — only **29.0%** of award rows resolve to a Spotify artist and
    **38.25%** carry no artist credit at all: every R1–R4 view must be read as
    a *lower bound* of the true relationship.
* **Caveats**: winners-only dataset (no nomination history), name-based
  integration, no value repair (rule T5).

## 5. Alternative: Power BI

[`powerbi_dashboard.md`](powerbi_dashboard.md) documents the same four
requirements as Power BI pages over the same `music_dw` connection, including
the DAX measures. It consumes identical KPI queries, so both BI layers are
interchangeable; Superset is the one automated inside the repository
(`run.sh superset`).
