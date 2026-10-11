# Dimensional Model Design

Workshop-2, section 6.4 and 6.10. Executable DDL: [`sql/dw_schema.sql`](../sql/dw_schema.sql)
(target database `music_dw`, PostgreSQL 16). Load implementation: `src/load.py`.
Detailed table and field rationale: [`docs/data_dictionary_and_rationale.md`](data_dictionary_and_rationale.md).

## 1. Business process

**Commercial performance of Spotify track listings and the Grammy Award
recognition obtained by their artists.** Two fact tables describe the same
business process from its Spotify side and its Grammy side, joined through the
conformed `dim_artist` (and `dim_year` for the temporal context).

## 2. Fact tables and grain

| Fact | Grain (one row = …) | Rows in this batch | Key measures |
| --- | --- | --- | --- |
| `fact_track_artist` | one Spotify **track listing** (`track_id` × `genre_sk`) **× one performing artist** | **157,530** | `popularity`, `danceability`, `energy`, `valence`, `acousticness`, `speechiness`, `is_grammy_artist`, `is_grammy_artist_strict`, `is_zero_popularity`, `is_primary_song`, `song_key` (repeated measures, not additive across artists — see §6) |
| `fact_grammy_award` | one **Grammy award record** (`year` × `category` × `nominee` × `artist`) | **4,810** | `winner_flag`, `is_matched_spotify`, `is_matched_strict`, `is_song_confirmed`, `match_method`, `recognition_tier` (count awards with `COUNT(*)`) |
| `bridge_award_artist` | one **matched artist of a Grammy credit** (`grammy_award_sk` × `artist_sk`) | **2,772** | `artist_position`, `match_method`, `recognition_tier` (collaborative credits, recognition tiers) |
 
 Grain justification: a Spotify track may be attributed to several genres *and*
 several artists; the finest level at which all R1-R4 measures are consistent is
 *(listing, artist)*. Awards are atomic per source row (the award business key
 has 0 duplicates).
 
 ## 3. Dimensions
 
 | Dimension | Grain / business key | Surrogate key | Columns | Attributes used by |
 | --- | --- | --- | --- | --- |
| `dim_artist` | **`artist_bk`** = normalized `artist_key` (TEXT, UNIQUE) | `artist_sk` BIGSERIAL (1-based, rebuilt each load) | `artist_display_name`, `from_spotify`, `grammy_award_count`, `spotify_track_count`, **`dominant_genre`, `dominant_genre_family`, `n_genres`, `genre_tie`** (primary-song rows only) | R1 (recognition flag), R2 (dominant genre family), R4 (award rank + catalogue coverage) |
| `dim_genre` | `genre` = Spotify `track_genre` (114 values, UNIQUE) | `genre_sk` BIGSERIAL | **`genre_family`** (12 macro-families) | R2 (genre split), R1 per-genre view |
 | `dim_year` | `year` (natural key = `year_sk`, INTEGER) | *none needed* — year is already a stable integer key | `decade` (derived `year/10*10`) | R3 (decade + per-year series) |
| `dim_award_category` | `category` (638 values, UNIQUE) | `category_sk` BIGSERIAL | **`category_clean`** (parentheses removed, 8 Producer variants merged into 2), **`category_family`** | R4 award analysis, drill-down |
 
 **Surrogate/business-key strategy**
 
 * Business keys are *natural, meaningful* keys: `artist_key`, `genre`, `year`,
   `year|category|nominee|artist` (`award_bk`, UNIQUE on the fact).
 * Surrogate keys (`artist_sk`, `genre_sk`, `category_sk`) are BIGSERIAL values
   generated **inside the load transaction** (explicit 1-based values + `setval`
   so sequences stay aligned); they are rebuilt every run and never exposed to
   the dashboard, only used as FKs.
 * `dim_year` uses the natural key as PK (a calendar year cannot be redefined
   between batches), which keeps both facts joinable across reruns.
 * Unmatched Grammy rows keep `artist_sk NULL` (`fact_grammy_award.artist_sk` is
   nullable **by design**) so award coverage gaps remain measurable instead of
   forcing a fake dimension member.
 
 ## 4. Relationships (star schema)
 
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
         int grammy_award_count
         int spotify_track_count
         text dominant_genre "most frequent genre"
         text dominant_genre_family "macro-family of dominant genre"
         int n_genres "total distinct genres"
         bool genre_tie "true if tie in dominant genre"
         timestamptz loaded_at
     }
     dim_genre {
         bigint genre_sk PK
         text genre UK
         text genre_family "genre macro-family (12 groups)"
         timestamptz loaded_at
     }
     dim_year {
         int year_sk PK
         int year UK
         int decade
         timestamptz loaded_at
     }
     dim_award_category {
         bigint category_sk PK
         text category UK
         text category_clean "standardized category name"
         text category_family "award field or family"
         timestamptz loaded_at
     }
     fact_track_artist {
         bigint track_artist_sk PK
         text track_id
         bigint artist_sk FK
         bigint genre_sk FK
         int popularity "popularity 0..100"
         float danceability "danceability 0.0..1.0"
         float energy "energy 0.0..1.0"
         float valence "valence 0.0..1.0"
         float acousticness "acousticness 0.0..1.0"
         float speechiness "speechiness 0.0..1.0"
         smallint is_grammy_artist "1 if artist has Grammy (0/1)"
         smallint is_grammy_artist_strict "1 if strict match (0/1)"
         text song_key "canonical key (artist + track)"
         smallint is_zero_popularity "1 if zero popularity (0/1)"
         smallint is_primary_song "1 canonical row for dedup (0/1)"
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
         smallint winner_flag "1 if winner (0/1)"
         smallint is_matched_spotify "1 if matched to Spotify (0/1)"
         smallint is_matched_strict "1 if strict match (0/1)"
         smallint is_song_confirmed "1 if song verified (0/1)"
         text match_method "matching method (exact, fuzzy)"
         text recognition_tier "recognition tier (solo, collab)"
         text batch_id
         timestamptz loaded_at
     }
     bridge_award_artist {
         bigint grammy_award_sk PK,FK
         bigint artist_sk PK,FK
         int artist_position "credit order position"
         text match_method "artist-level match method"
         text recognition_tier "artist-level recognition tier"
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

Current structure: 8 physical tables (4 conformed dimensions, 2 facts, 1 bridge, 1 batch audit log). Backward compatibility views (`vw_fact_track_artist`, `vw_fact_grammy_award`) are provided in [`sql/compatibility_views.sql`](../sql/compatibility_views.sql).

| Relationship | Type | Enforced by |
| --- | --- | --- |
| `dim_artist` 1 → n `fact_track_artist` | one-to-many | FK `artist_sk NOT NULL` + UNIQUE(bk) |
| `dim_artist` 1 → n `fact_grammy_award` | one-to-many (nullable) | FK `artist_sk NULL` allowed |
| `dim_genre` 1 → n `fact_track_artist` | one-to-many | FK `genre_sk NOT NULL` |
| `dim_year` 1 → n `fact_grammy_award` | one-to-many | FK `year_sk NOT NULL` |
| `dim_award_category` 1 → n `fact_grammy_award` | one-to-many | FK `category_sk NOT NULL` |
| `fact_grammy_award` 1 → n `bridge_award_artist` | one-to-many | FK `grammy_award_sk NOT NULL` + `ON DELETE CASCADE` |
| `dim_artist` 1 → n `bridge_award_artist` | one-to-many | FK `artist_sk NOT NULL` |
| fact ↔ fact | conformed through `dim_artist` (many-to-many at source level) | modelled, not FK'd (facts never reference each other) |

## 5. Keys and integrity constraints (DDL)

* PK: `artist_sk`, `genre_sk`, `year_sk`, `category_sk`, `track_artist_sk`,
  `grammy_award_sk`, `etl_batch_log.batch_id`. The bridge has no surrogate key
  of its own: `(grammy_award_sk, artist_sk)` is UNIQUE by design.
* UNIQUE: `dim_artist.artist_bk`, `dim_genre.genre`, `dim_year.year`,
  `dim_award_category.category`, `fact_track_artist (track_id, genre_sk,
  artist_sk)` — **the prepared grain, enforced by the database** — and
  `fact_grammy_award.award_bk`.
* CHECK: `is_grammy_artist IN (0,1)`, `winner_flag IN (0,1)`,
  `is_matched_spotify IN (0,1)`, plus the flags
  (`is_primary_song`, `is_zero_popularity`,
  `is_matched_strict`, `is_song_confirmed`) (mirrors GX rules DQ-P5/P8/DQ-G*).
* FKs as in §4 (all `REFERENCES` clauses in `sql/dw_schema.sql`).
* Indexes on every FK plus `batch_id` and the R1 segmentation flag.

## 6. Measures and aggregation guidance

| Measure | Additive? | Notes |
| --- | --- | --- |
| award counts (`COUNT(*)`) | additive | over `fact_grammy_award` |
| `popularity`, audio features | **average, not sum** | fact grain is artist-expanded: KPIs use `AVG` or `COUNT(DISTINCT track_id)` to avoid weighting a 3-artist track three times |
| `spotify_track_count`, `grammy_award_count` | semi-additive (dimension attributes) | read from `dim_artist`, not summed across facts. `spotify_track_count` counts **track listings** (track × genre), not distinct songs: use `COUNT(DISTINCT track_id)` or `is_primary_song = 1` for distinct songs |
| `is_grammy_artist` / `is_matched_spotify` | additive as 0/1 flags | used for coverage/ratio KPIs |

## 7. Load strategy (idempotence)

1. `build_dimensional_frames()` derives all seven frames from the prepared
   CSVs plus `bridge_award_artist.csv` (deterministic ordering; surrogate keys
   1..n assigned explicitly).
2. Inside **one transaction**: `DELETE` existing rows starting with the bridge
   (it references facts and dimensions), then the facts and dimensions
   (strategy `replace`), `INSERT` dims → facts → bridge (the bridge resolves
   `award_bk → grammy_award_sk` inside the same transaction), `setval` the
   three sequences to `MAX(sk)`, upsert `etl_batch_log`
   (`batch_id = <dag_id>__<run_id>`) with before/after counts for all seven
   tables.
3. Any failure rolls the whole batch back → the target keeps the previous
   consistent state (never a half-loaded warehouse).
4. Consequences for reruns: a rerun of the same batch replaces rows instead of
   appending (verified: Test A and Test C both loaded `157,530 / 4,810 / 30,894 /
   114 / 62 / 638` rows with **no growth** — `docs/evidence/runs/airflow_etl_batch_log.csv`).

## 8. How each requirement is supported

| Requirement | Facts/dimensions used | Query |
| --- | --- | --- |
| R1 | `fact_track_artist` + `dim_artist.is_grammy_artist` + `dim_genre` | `kpi_1_popularity_by_grammy_recognition`, `kpi_1_genre_split` |
| R2 | `fact_grammy_award` × `dim_artist` × `dim_genre` (dominant genre per artist) | `kpi_2_awards_by_dominant_genre` |
| R3 | `fact_grammy_award` + `dim_year` (+ profile from `fact_track_artist`) | `kpi_3_awards_and_profile_by_decade`, `kpi_3_awards_per_year` |
| R4 | `fact_grammy_award` + `dim_artist` | `kpi_4_top_awarded_artists_on_spotify` |

## 9. Model audit and optimisation (applied)

An audit of the schema against R1–R4 and KPI-0 traced every column through `src/`,
`sql/kpi_queries.sql`, `scripts/` (including the Superset dashboard builders), `dags/`,
`tests/`, `gx/` and the Power BI/Superset docs, and profiled `data/output`. The result:
the **structure is justified** (2 facts, 4 dimensions, 1 bridge, 1 control table) and the
**width is not**. The optimisation therefore removes columns that no KPI, dashboard,
script or DAG reads from the warehouse, and adds no objects (no views, no tables).

### 9.1 Why the structure stays

| Object | Decision | Reason |
| --- | --- | --- |
| `fact_track_artist` (157,530) and `fact_grammy_award` (4,810) | **keep both** | Different business processes with incompatible grains (track × genre × artist vs. one award record). Merging them would repeat each award once per catalogue row and drop the 465 awards without an artist that KPI-0 needs. |
| `bridge_award_artist` (2,772) | **keep** | 246 awards have more than one matched artist. The fact stores only the first in `artist_sk`, so without the bridge R2/R4 would under-count awards per artist. |
| `is_primary_song`, `song_key` | keep | Deduplicate songs repeated per genre (157,530 rows → 111,206 distinct songs). |
| `is_grammy_artist`, `is_grammy_artist_strict`, `recognition_tier`, `match_method`, `is_matched_*`, `is_song_confirmed` | keep | Stored matching decisions that cannot be recomputed without re-running the matcher. They drive R1 and KPI-0. |
| `dominant_genre`, `dominant_genre_family`, `n_genres`, `genre_tie` | keep | R2 classification with a documented tie-break rule. |

### 9.2 Columns removed from the warehouse

All of them stay in the staging CSVs (`data/work/prepared_*.csv`), so traceability and
the Great Expectations / validation gates (which run on staging) are untouched.

| Table | Removed columns | Why |
| --- | --- | --- |
| `dim_artist` | `from_grammy`, `grammy_award_count_core` | `from_grammy` is `grammy_award_count > 0`. The core count has no consumer (tiers are read from the bridge and the fact). |
| `fact_track_artist` | `track_name`, `album_name` | Text repeated per genre/artist row. Identity is carried by `track_id` and `song_key`. |
| | `duration_ms`, `explicit`, `liveness`, `loudness`, `tempo` | No KPI or dashboard uses them. `duration_ms`, `loudness` and `tempo` only fed the outlier flags. |
| | `is_outlier_duration`, `is_outlier_loudness`, `is_outlier_tempo` | Quality flags computed and validated in staging, not read by any warehouse query. |
| | `artist_position`, `artist_total` | Not used. Duplicate-safe aggregation uses `is_primary_song` and `COUNT(DISTINCT track_id)`. |
| | `artist_grammy_awards` | Per-artist attribute repeated on every track row and not read by any query. |
| | `track_genre` | Duplicates `genre_sk` (`dim_genre.genre` is UNIQUE). The grain key becomes `(track_id, genre_sk, artist_sk)`. |
| `fact_grammy_award` | `winner` | Duplicate of `winner_flag` (the loaded source contains only winners). |
| | `award_count` | Constant 1, equals `COUNT(*)`. |
| | `spotify_track_count` | Identical to `dim_artist.spotify_track_count` in all 4,810 rows. |
| | `artist_source`, `is_aggregate_credit`, `credit_artist_count` | Matching trace fields not read by the warehouse. The match decision itself is kept in `match_method` and `recognition_tier`. |

### 9.3 Before / after (counted from `sql/dw_schema.sql`)

| Table | Columns before | Columns after |
| --- | --- | --- |
| `dim_artist` | 13 | 11 |
| `dim_genre` | 4 | 4 |
| `dim_year` | 4 | 4 |
| `dim_award_category` | 5 | 5 |
| `fact_track_artist` | 32 | 17 |
| `fact_grammy_award` | 23 | 17 |
| `bridge_award_artist` | 7 | 7 |
| `etl_batch_log` | 10 | 10 |
| **Total (8 tables)** | **98** | **75** |

Tables and relationships are unchanged. Dashboards are unaffected because no column
they read was removed. `sql/dw_schema.sql` drops the columns with
`ALTER TABLE ... DROP COLUMN IF EXISTS`, so an existing database upgrades in place on
the next load, and creates the new grain key `uq_track_artist`.

### 9.4 Findings documented but not changed

* `dim_artist.spotify_track_count` counts fact rows (track × genre), so it differs from
  the distinct song count for 6,841 of 29,789 artists with tracks. Changing it would alter
  the R4 figures shown in the dashboards, so it is documented in §6 and left as is.
* `artist_grammy_awards` (staging) and `dim_artist.grammy_award_count_core` differ for 416
  rows because they count different things, which is why neither was turned into a view.
* The Power BI document lists some removed columns (outlier flags, `loudness`, `tempo`,
  `explicit`, `artist_position`, `artist_source`, `credit_artist_count`). Power BI is the
  alternative client and no `.pbix` is in the repository. If a Power BI report or ad-hoc query
  needs them, consume `sql/compatibility_views.sql` (`vw_fact_track_artist`, `vw_fact_grammy_award`)
  or restore the column in `sql/dw_schema.sql` and `src/load.py`.

### 9.5 Regression checks

```sql
SELECT count(*) FROM fact_track_artist;          -- 157530
SELECT count(*) FROM fact_grammy_award;          -- 4810
SELECT count(*) FROM bridge_award_artist;        -- 2772
SELECT count(*) FROM fact_grammy_award WHERE artist_sk IS NULL;  -- 465
SELECT count(DISTINCT song_key) FROM fact_track_artist;          -- see note
SELECT count(*) FROM fact_track_artist WHERE is_primary_song = 1; -- 111206
```

All `sql/kpi_queries.sql` results must match the pre-change baseline.
