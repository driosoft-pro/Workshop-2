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
| **R1** | *Do Grammy-recognized artists perform differently on Spotify than the rest of the catalog?* — decides whether "award recognition" is a useful segmentation for catalogue/editorial decisions. | `artists`, `artist_key`, `popularity`, `danceability`, `energy`, `valence`, `is_grammy_artist` / `is_matched_spotify` | Spotify (audio + popularity) **and** Grammy (`artist`, `winner`) — the recognition flag cannot exist without both | **KPI-1a** average popularity/audio profile of *Grammy-recognized* vs *other* tracks; **KPI-1b** same comparison per genre; **KPI-0** integration coverage that qualifies both | Track row (114,000) → artist (30,894) → 2 comparison groups; per-genre cut for the top-12 volume genres |
| **R2** | *Which Spotify genres dominate among Grammy-recognized artists?* — decides where award recognition and catalogue volume coexist (genre strategy, catalogue gaps). | `track_genre`, `artist_key`, Grammy `year` + `category` | Spotify (`track_genre`) **and** Grammy (awards) — a genre with no awards cannot be ranked by recognition | **KPI-2** award count and share by the awardee's dominant Spotify genre (top 15) | Genre (114) aggregated from the artist×track fact joined to the award fact through `dim_artist` |
| **R3** | *How has the profile of recognized artists evolved over time?* — decides whether the recognised artist population is ageing/renewing (catalogue planning by decade). | Grammy `year`, award counts, Spotify `popularity`/audio features of the matched artists | Grammy (timeline) **and** Spotify (profile) — a timeline without profiles (or profiles without a timeline) cannot answer it | **KPI-3a** awards per decade + recognized artists + avg popularity/energy by decade; **KPI-3b** awards per year trend line | Decade (7 buckets, 1950s–2010s) and year (62 years, 1958–2019) |
| **R4** | *Which artists accumulate the most Grammy awards, and how are they represented in the Spotify catalog?* — decides partnership/priority artist lists and exposes catalogue coverage gaps. | Grammy `artist`, award counts, first/last award year, Spotify `spotify_track_count`, `avg_track_popularity` | Grammy (award counts) **and** Spotify (catalogue presence) — award rank alone is Grammy-only, catalogue rank alone is Spotify-only | **KPI-4** top-10 awarded artists inside the Spotify catalog with track count and average popularity | Artist (top 10 by awards, restricted to artists present in Spotify, aggregate credit `(Various Artists)` excluded) |

## Why both sources are necessary (summary)

| Requirement | Without Spotify | Without Grammy |
| --- | --- | --- |
| R1 | no recognition flag exists | no popularity/audio profile to compare |
| R2 | no genre attribute for awardees | no award signal to rank genres by recognition |
| R3 | no artist profile per period | no award timeline |
| R4 | no catalogue coverage per artist | no award counts, first/last award year |

## Expected outputs per requirement

| Requirement | KPI query (`sql/kpi_queries.sql`) | Output artifact | DW elements |
| --- | --- | --- | --- |
| R1 | `kpi_1_popularity_by_grammy_recognition`, `kpi_1_artist_level`, `kpi_1_within_genre_diff`, `kpi_0_integration_coverage`, `kpi_0_coverage_by_tier` | `docs/evidence/kpis/kpi_1_*.csv`, `kpi_1_stats.csv`, `kpi_1_dedupe_impact.csv`, `ar1_popularity_by_genre.png` | `fact_track_artist`, `dim_artist`, `dim_genre`, `bridge_award_artist` |
| R2 | `kpi_2_awards_by_dominant_genre`, `kpi_2_heatmap` | `kpi_2_awards_by_dominant_genre.csv`, `kpi_2_heatmap.csv`, `ar2_awards_by_dominant_genre.png` | `fact_grammy_award`, `dim_artist`, `dim_genre`, `bridge_award_artist` |
| R3 | `kpi_3_awards_and_profile_by_decade`, `kpi_3_awards_per_year`, `kpi_3_awards_by_family_decade` | `kpi_3_*.csv`, `ar3_awards_and_profile_by_decade.png` | `fact_grammy_award`, `fact_track_artist`, `dim_year`, `bridge_award_artist` |
| R4 | `kpi_4_top_awarded_artists_on_spotify`, `kpi_4_top_awarded_all` | `kpi_4_*.csv`, `ar4_top_awarded_artists.png` | `fact_grammy_award`, `dim_artist`, `bridge_award_artist` |

## Traceability

End-to-end chains (requirement → risk → rule → expectation → transformation →
DW → KPI) are materialized in [`traceability_matrix.md`](traceability_matrix.md).
The requirement tags carried inside the code are the single source of truth:
`RULES[*].requirement` in `src/validation.py` and the `-- Rn` comments in
`sql/kpi_queries.sql`.

## Analytical Limitations and Methodological Caveats

1. **Popularity is Current, Not Historical**: Spotify `popularity` represents real-time stream volume at the time of extract, not historical popularity when awards were won. Comparing 1960s Grammy winners with modern non-Grammy tracks reflects enduring contemporary streaming demand, not historical impact.
2. **Coverage Inequity by Decade**: Integration coverage varies dramatically across decades (under 15% in the 1950s–1960s vs ~50% in the 2000s–2010s). Decade-level trends in R3 must be interpreted in conjunction with `matched_share_pct` (KPI-0 / KPI-3).
3. **Selection Bias in Control Group**: Because cross-source matching is strictly name-based without value repair (Rule T5), unmatched awardees fall into the non-Grammy control group. The measured popularity differences in R1 represent conservative lower bounds of the true effect.
4. **Winners-Only Dataset**: The Grammy source records award recipients without non-winning nominees (4,810 winners), precluding win-rate probability modeling.
