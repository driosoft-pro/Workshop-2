# Dimensional Model Design

Workshop-2, section 6.4 and 6.10. Executable DDL: [`sql/dw_schema.sql`](../sql/dw_schema.sql)
(target database `music_dw`, PostgreSQL 16). Load implementation: `src/load.py`.

## 1. Business process

**Commercial performance of Spotify track listings and the Grammy Award
recognition obtained by their artists.** Two fact tables describe the same
business process from its Spotify side and its Grammy side, joined through the
conformed `dim_artist` (and `dim_year` for the temporal context).

## 2. Fact tables and grain

| Fact | Grain (one row = …) | Rows in this batch | Key measures |
| --- | --- | --- | --- |
| `fact_track_artist` | one Spotify **track listing** (`track_id` × `track_genre`) **× one performing artist** | **157,530** | `popularity`, `duration_ms`/`duration_ms→duration_min`, `explicit`, `danceability`, `energy`, `valence`, `acousticness`, `speechiness`, `liveness`, `loudness`, `tempo`, `artist_position`, `artist_total`, `is_grammy_artist`, `artist_grammy_awards` (degenerate/repeated measures, not additive across artists — see §6) |
| `fact_grammy_award` | one **Grammy award record** (`year` × `category` × `nominee` × `artist`) | **4,810** | `winner`, `winner_flag`, `is_matched_spotify`, `is_matched_strict`, `is_song_confirmed`, `artist_source`, `match_method`, `credit_artist_count`, `spotify_track_count`, `award_count` |
| `bridge_award_artist` | one **matched artist of a Grammy credit** (`award_bk` × `artist_key`) | **2,757** | `artist_position`, `match_method` (T12 collaborative credits) |

Grain justification: a Spotify track may be attributed to several genres *and*
several artists; the finest level at which all R1-R4 measures are consistent is
*(listing, artist)*. Awards are atomic per source row (the award business key
has 0 duplicates).

## 3. Dimensions

| Dimension | Grain / business key | Surrogate key | Columns | Attributes used by |
| --- | --- | --- | --- | --- |
| `dim_artist` | **`artist_bk`** = normalized `artist_key` (TEXT, UNIQUE) | `artist_sk` BIGSERIAL (1-based, rebuilt each load) | `artist_display_name`, `from_spotify`, `from_grammy`, `grammy_award_count`, `spotify_track_count`, **`dominant_genre`, `dominant_genre_family`, `n_genres`, `genre_tie`** (T16, primary-song rows only) | R1 (recognition flag), R2 (dominant genre family), R4 (award rank + catalogue coverage) |
| `dim_genre` | `genre` = Spotify `track_genre` (114 values, UNIQUE) | `genre_sk` BIGSERIAL | **`genre_family`** (T14, 12 families) | R2 (genre split), R1 per-genre view |
| `dim_year` | `year` (natural key = `year_sk`, INTEGER) | *none needed* — year is already a stable integer key | `decade` (derived `year/10*10`) | R3 (decade + per-year series) |
| `dim_award_category` | `category` (638 values, UNIQUE) | `category_sk` BIGSERIAL | **`category_clean`** (T13: parentheses removed, 8 Producer variants merged into 2), **`category_family`** (T13) | R4 award analysis, drill-down |

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

```
                         dim_genre
                            |  (genre_sk)
                            |
dim_artist ---|<== fact_track_artist  |  fact_grammy_award  |==> dim_year (year_sk)
(artist_sk)   |                       |  (artist_sk)        |-----> dim_award_category (category_sk)
   (artist_sk)|                       |
              +-----------------------+
        conformed dimension (both facts)
```

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
  `dim_award_category.category`, `fact_track_artist (track_id, track_genre,
  artist_sk)` — **the prepared grain, enforced by the database** — and
  `fact_grammy_award.award_bk`.
* CHECK: `is_grammy_artist IN (0,1)`, `winner_flag IN (0,1)`,
  `is_matched_spotify IN (0,1)`, plus the T15/T12 flags
  (`is_primary_song`, `is_zero_popularity`, `is_outlier_*`,
  `is_matched_strict`, `is_song_confirmed`) (mirrors GX rules DQ-P5/P8/DQ-G*).
* FKs as in §4 (all `REFERENCES` clauses in `sql/dw_schema.sql`).
* Indexes on every FK plus `batch_id` and the R1 segmentation flag.

## 6. Measures and aggregation guidance

| Measure | Additive? | Notes |
| --- | --- | --- |
| award counts (`COUNT(*)`, `award_count`) | additive | over `fact_grammy_award` |
| `popularity`, audio features | **average, not sum** | fact grain is artist-expanded: KPIs use `AVG` or `COUNT(DISTINCT track_id)` to avoid weighting a 3-artist track three times |
| `spotify_track_count`, `grammy_award_count` | semi-additive (dimension attributes) | read from `dim_artist`, not summed across facts |
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
