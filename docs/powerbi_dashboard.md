# Analytical Product: KPIs, Visualizations and Power BI Dashboard

> **Alternative BI layer.** The primary BI tool of the project is
> **Apache Superset** (automated inside the repository, see
> [`superset_dashboard.md`](superset_dashboard.md)). This document keeps the
> Power BI Desktop design over the same `music_dw` connection for workstations
> where Power BI is the standard client.

Workshop-2, sections 8.1 and 9.1 (deliverable 5).
**All queries read the dimensional Data Warehouse (`music_dw`) in PostgreSQL —
no direct CSV connection is used.**

## 1. KPI inventory (7 SQL queries, `sql/kpi_queries.sql`)

| ID | Req. | Query name | Grain / rows | Headline numbers (this batch) |
| --- | --- | --- | --- | --- |
| **KPI-0** | R1, R2, R3 (coverage qualifier) | `kpi_0_integration_coverage` | 1 row | 4,810 award rows → 1,395 matched (29.0%); 38.25% rows have no artist credit |
| **KPI-1a** | R1 | `kpi_1_popularity_by_grammy_recognition` | 2 groups | Grammy-recognized: 10,430 listings, avg popularity **31.55**, energy 0.5935 · Other: 147,100 listings, avg popularity **33.58**, energy 0.6404 |
| **KPI-1b** | R1 | `kpi_1_genre_split` | top-12 genres by volume | e.g. `edm` 49.93 vs 34.94, `house` 53.90 vs 34.23, `opera` 26.03 vs 23.52 (recognition premium per genre) |
| **KPI-2** | R2 | `kpi_2_awards_by_dominant_genre` | top-15 genres | blues 103 awards (7.38%), country 99 (7.10%), club 87 (6.24%), disco 81 (5.81%), soul 75 (5.38%) |
| **KPI-3a** | R3 | `kpi_3_awards_and_profile_by_decade` | 7 decades | 1950s: 63 awards, 27 artists, avg popularity 18.01 → 2010s: 1,210 awards, 535 artists, avg popularity 35.67 |
| **KPI-3b** | R3 | `kpi_3_awards_per_year` | 62 years | 1958–2019 trend line (no gaps) |
| **KPI-4** | R4 | `kpi_4_top_awarded_artists_on_spotify` | top-10 artists | Aretha Franklin 16 awards/15 tracks, Bruce Springsteen 13/6 (avg 75.33), Beyoncé 13/6 (68.17), Ella Fitzgerald 13/262, Stevie Wonder 13/238, … (aggregate credit `(Various Artists)` excluded, artists absent from Spotify excluded) |

Query results are exported as machine-readable evidence by `build_kpis`:

```
docs/evidence/kpis/kpi_*.csv          (7 result sets)
docs/evidence/kpis/kpi_summary.json   (row counts + file index)
docs/evidence/kpis/ar1..ar4_*.png     (4 charts rendered from the DW results)
```

## 2. Visualizations (minimum 3 → 4 provided)

| Chart file | Req. | Visual | Reading |
| --- | --- | --- | --- |
| `ar1_popularity_by_genre.png` | R1 | grouped bars: avg popularity of Grammy-recognized vs other artists, top-12 genres | recognition premium is positive in EDM/house/reggaeton, negative in funk/classical |
| `ar2_awards_by_dominant_genre.png` | R2 | bars: awards by the awardee's dominant Spotify genre | where recognition concentrates |
| `ar3_awards_and_profile_by_decade.png` | R3 | combo: awards per decade (bars) + avg popularity/energy of recognized artists (lines) | award volume and artist profile both rise over time |
| `ar4_top_awarded_artists.png` | R4 | horizontal bars: top-10 awarded artists with Spotify track counts | award rank vs catalogue coverage |

## 3. Power BI dashboard design

Connection: **PostgreSQL** server `localhost:5432` (container `music-postgres`),
database `music_dw`, credentials from `.env` (`music` / `music` — never commit
real credentials). Mode: **Import** (refresh after each DAG run) with DirectQuery
as an alternative for ad-hoc exploration.

### Page 1 — "Recognition & Catalogue" (R1)

| Visual | Source |
| --- | --- |
| Scorecards: avg popularity, avg energy, listings (2 values) | `kpi_1_popularity_by_grammy_recognition` |
| Clustered bar: recognition vs other by genre | `kpi_1_genre_split` |
| Card: matched award rows / % (context for the page) | `kpi_0_integration_coverage` |

### Page 2 — "Genres & Awards" (R2)

| Visual | Source |
| --- | --- |
| Bar: awards by dominant genre (top 15) | `kpi_2_awards_by_dominant_genre` |
| Table: genre, awards, recognized artists, share % | same |

### Page 3 — "Evolution" (R3)

| Visual | Source |
| --- | --- |
| Line: awards per year | `kpi_3_awards_per_year` |
| Combo: awards per decade + avg popularity/energy | `kpi_3_awards_and_profile_by_decade` |

### Page 4 — "Artists" (R4)

| Visual | Source |
| --- | --- |
| Bar: top-10 awarded artists (awards) | `kpi_4_top_awarded_artists_on_spotify` |
| Table: artist, awards, first/last award year, Spotify tracks, avg popularity | same |

### DAX measures (Import mode, table `kpi_1_popularity_by_grammy_recognition`
etc. — or a star-schema model built on the DW tables):

```dax
Awards Total      := SUM ( kpi_2_awards_by_dominant_genre[grammy_awards] )
Award Share %     := DIVIDE ( [Awards Total], CALCULATE ( [Awards Total ], ALL ( kpi_2_awards_by_dominant_genre ) ) )
Avg Popularity    := AVERAGE ( fact_track_artist[popularity] )
Recognition Rate  := DIVIDE ( [Matched Award Rows], [Award Rows] )
Matched Award Rows:= SUM ( kpi_0_integration_coverage[matched_award_rows] )
Award Rows        := SUM ( kpi_0_integration_coverage[award_rows] )
```

Star-schema alternative (recommended for exploration): load the six DW tables,
relate `fact_track_artist[artist_sk] → dim_artist[artist_sk]`,
`fact_grammy_award[artist_sk] → dim_artist[artist_sk]`, `…[year_sk] → dim_year[year_sk]`,
`…[category_sk] → dim_award_category[category_sk]`, `fact_track_artist[genre_sk] → dim_genre[genre_sk]`,
then build the same four pages with slicers for `dim_year.decade` and `dim_genre.genre`.

### Refresh / governance

* Refresh order: run the DAG first, then **Transform → Refresh** in Power BI
  (the dashboard never reads `data/*.csv`).
* Every visual's claim is traceable through `docs/traceability_matrix.md`.
* The four PNGs produced by `build_kpis` are the pipeline's own rendering of the
  same queries and serve as review evidence when Power BI is not available.
