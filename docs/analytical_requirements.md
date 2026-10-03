# Analytical Requirements and Solution Scope

Workshop-2, section 6.1. Every downstream decision in this repository
(profiling scope, quality rules, transformations, dimensional model, KPIs)
is traced back to one of the four requirements below.

## Scope statement

The pipeline produces **one trusted, requirements-driven analytical Data
Warehouse** that joins two heterogeneous sources:

| Source | Provided form | Operational source used by the pipeline |
| --- | --- | --- |
| Spotify tracks | CSV file | `data/raw/spotify_dataset.csv` (114,000 rows) |
| Grammy Awards | CSV file | PostgreSQL `music_source.grammy_awards` (4,810 rows) — loaded by `scripts/prepare_source_db.py` (**source preparation**, not the ETL Load) |

In scope: extraction, two validation gates, harmonization/integration,
dimensional load, KPI queries and dashboard design, reliability controls
(retries, controlled failure, safe rerun) and evidence production.
Out of scope: streaming ingestion, incremental/SCD loading, ML models, and any
repair of source values (rule **T5** — never modify data to make a check pass).

## Requirement table

| ID | Analytical requirement (decision it supports) | Required data | Source(s) | Expected KPI / visualization | Level of detail |
| --- | --- | --- | --- | --- | --- |
| **AR1** | *Do Grammy-recognized artists perform differently on Spotify than the rest of the catalog?* — decides whether "award recognition" is a useful segmentation for catalogue/editorial decisions. | `artists`, `artist_key`, `popularity`, `danceability`, `energy`, `valence`, `is_grammy_artist` / `is_matched_spotify` | Spotify (audio + popularity) **and** Grammy (`artist`, `winner`) — the recognition flag cannot exist without both | **KPI-1a** average popularity/audio profile of *Grammy-recognized* vs *other* tracks; **KPI-1b** same comparison per genre; **KPI-0** integration coverage that qualifies both | Track row (114,000) → artist (30,894) → 2 comparison groups; per-genre cut for the top-12 volume genres |
| **AR2** | *Which Spotify genres dominate among Grammy-recognized artists?* — decides where award recognition and catalogue volume coexist (genre strategy, catalogue gaps). | `track_genre`, `artist_key`, Grammy `year` + `category` | Spotify (`track_genre`) **and** Grammy (awards) — a genre with no awards cannot be ranked by recognition | **KPI-2** award count and share by the awardee's dominant Spotify genre (top 15) | Genre (114) aggregated from the artist×track fact joined to the award fact through `dim_artist` |
| **AR3** | *How has the profile of recognized artists evolved over time?* — decides whether the recognised artist population is ageing/renewing (catalogue planning by decade). | Grammy `year`, award counts, Spotify `popularity`/audio features of the matched artists | Grammy (timeline) **and** Spotify (profile) — a timeline without profiles (or profiles without a timeline) cannot answer it | **KPI-3a** awards per decade + recognized artists + avg popularity/energy by decade; **KPI-3b** awards per year trend line | Decade (7 buckets, 1950s–2010s) and year (62 years, 1958–2019) |
| **AR4** | *Which artists accumulate the most Grammy awards, and how are they represented in the Spotify catalog?* — decides partnership/priority artist lists and exposes catalogue coverage gaps. | Grammy `artist`, award counts, first/last award year, Spotify `spotify_track_count`, `avg_track_popularity` | Grammy (award counts) **and** Spotify (catalogue presence) — award rank alone is Grammy-only, catalogue rank alone is Spotify-only | **KPI-4** top-10 awarded artists inside the Spotify catalog with track count and average popularity | Artist (top 10 by awards, restricted to artists present in Spotify, aggregate credit `(Various Artists)` excluded) |

## Why both sources are necessary (summary)

| Requirement | Without Spotify | Without Grammy |
| --- | --- | --- |
| AR1 | no recognition flag exists | no popularity/audio profile to compare |
| AR2 | no genre attribute for awardees | no award signal to rank genres by recognition |
| AR3 | no artist profile per period | no award timeline |
| AR4 | no catalogue coverage per artist | no award counts, first/last award year |

## Expected outputs per requirement

| Requirement | KPI query (`sql/kpi_queries.sql`) | Output artifact | DW elements |
| --- | --- | --- | --- |
| AR1 | `kpi_1_popularity_by_grammy_recognition`, `kpi_1_genre_split`, `kpi_0_integration_coverage` | `docs/evidence/kpis/*.csv`, chart `ar1_popularity_by_genre.png` | `fact_track_artist`, `dim_artist`, `dim_genre` |
| AR2 | `kpi_2_awards_by_dominant_genre` | `kpi_2_awards_by_dominant_genre.csv`, `ar2_awards_by_dominant_genre.png` | `fact_grammy_award`, `dim_artist`, `dim_genre` |
| AR3 | `kpi_3_awards_and_profile_by_decade`, `kpi_3_awards_per_year` | `kpi_3_*.csv`, `ar3_awards_and_profile_by_decade.png` | `fact_grammy_award`, `fact_track_artist`, `dim_year` |
| AR4 | `kpi_4_top_awarded_artists_on_spotify` | `kpi_4_top_awarded_artists_on_spotify.csv`, `ar4_top_awarded_artists.png` | `fact_grammy_award`, `dim_artist` |

## Traceability

End-to-end chains (requirement → risk → rule → expectation → transformation →
DW → KPI) are materialized in [`traceability_matrix.md`](traceability_matrix.md).
The requirement tags carried inside the code are the single source of truth:
`RULES[*].requirement` in `src/validation.py` and the `-- ARn` comments in
`sql/kpi_queries.sql`.
