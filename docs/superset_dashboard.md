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
| Datasets (7, virtual) | `kpi_0_integration_coverage`, `kpi_1_popularity_by_grammy_recognition`, `kpi_1_genre_split`, `kpi_2_awards_by_dominant_genre`, `kpi_3_awards_and_profile_by_decade`, `kpi_3_awards_per_year`, `kpi_4_top_awarded_artists_on_spotify` | SQL extracted from [`sql/kpi_queries.sql`](../sql/kpi_queries.sql) by the `-- @name:` markers |
| Metrics | one aggregate per charted column (`SUM`/`AVG`/`MAX`/`MIN`) | `DATASET_SPECS` in `scripts/superset_bootstrap.py` |
| Charts (7) | see §3 | `CHART_SPECS` in `scripts/superset_bootstrap.py` |
| Dashboard | `Workshop-2 - KPIs (R1-R4)` | published, contains all 7 charts |

## 3. Charts per requirement

| Chart | Req. | Viz type (fallback) | Dataset | Query verified rows |
| --- | --- | --- | --- | --- |
| R1 – Popularidad: artistas Grammy vs resto del catálogo | R1 | `dist_bar` (`table`) | `kpi_1_popularity_by_grammy_recognition` | 2 |
| R1 – Popularidad por género (top volumen) | R1, R2 | `table` | `kpi_1_genre_split` | 12 |
| R2 – Premios Grammy por género Spotify dominante | R2 | `pie` (`table`) | `kpi_2_awards_by_dominant_genre` | 15 |
| R3 – Premios y perfil de artistas por década | R3 | `echarts_timeseries_line` (`table`) | `kpi_3_awards_and_profile_by_decade` | 7 |
| R3 – Serie anual de premios Grammy | R3 | `echarts_timeseries_line` (`table`) | `kpi_3_awards_per_year` | 62 |
| R4 – Top artistas premiados presentes en Spotify | R4 | `table` | `kpi_4_top_awarded_artists_on_spotify` | 10 |
| Calidad – Cobertura de integración (KPI-0) | R1, R2, R3 | `table` | `kpi_0_integration_coverage` | 1 |

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
