# Transformation and Integration Decision Record

Workshop-2, section 6.8. Implementation: `src/transform.py`
(`transform_and_integrate`), executed by the `transform_and_integrate` task
**after both raw gates** and **before the prepared gate**.

> Transformation is a single engineering phase. It is defensible
> independently of the current validation result: **no value is ever repaired
> to make a check pass (rule T5)** — out-of-range source values are *reported*
> by the raw gate and carried forward unchanged.

## 1. Transformation rules T1–T11

| ID | Rule (what changes) | Evidence / requirement that justifies it | Affected fields / records | Before → after | Exception handling | Analytical impact |
| --- | --- | --- | --- | --- | --- | --- |
| **T1** | Drop Spotify rows whose `artists` value is null/blank | Profiling: **1 of 114,000 rows** (0.0009%); DQ-S2 critical tolerance; an integration key is mandatory for AR1–AR3 | `artists` null rows (also the row with null `album_name`/`track_name`) | 114,000 → 113,999 rows | Row is *dropped*, never imputed; count reported as `rows_dropped_missing_artist` | guarantees `artist_key` can be built (feeds DQ-P2 = 100%) |
| **T2** | Remove duplicate rows at the source grain `(track_id, track_genre)`, keeping the first row after a deterministic sort | Profiling: **450 repeated (track_id, track_genre) pairs** (0.39%); the declared fact grain must be unique (DQ-P10 = 0) | duplicate grain rows | 113,999 → 113,549 rows | deterministic order (`track_id`,`track_genre`) so reruns drop the *same* row; count reported | prevents double-counted tracks in every popularity KPI |
| **T3** | Split `artists` on `;` and explode → grain becomes `(track_id, track_genre, artist_key)` | Collaboration credits are stored as one string; AR1/AR4 need *artist-level* facts | `artists` → `artist_key`, `artist_display_name`, `artist_position`, `artist_total` | 113,549 track rows → **157,530 track-artist rows** | parts that normalize to nothing are skipped (never produces an empty key) | enables `dim_artist` fan-out and `artist_track_count` |
| **T4** | Normalize artist name → `artist_key` (NFKD accent folding, lowercase, whitespace collapse, surrounding quotes/periods stripped, `(Various Artists)` → `various artists`) | Profiling: **90 keys** produced by >1 display name (`André Previn`/`Andre Previn`, `AURORA`/`Aura`, …); name-based matching needs one canonical key (no artist IDs exist in either source) | every artist credit on both sides | `André Previn` → `andre previn` | values that normalize to empty → `None` (Grammy side keeps null, tracked by DQ-P9) | the integration key used by the join, `is_grammy_artist`, `dim_artist` |
| **T5** | **No value repair**: out-of-range values are reported, never modified | Workshop principle: *"Do not modify data only to make a validation pass"*; e.g. 603 durations >10 min stay as they are | none (read-only rule) | unchanged | n/a — the raw gate decides whether the batch is safe | keeps AR1 averages honest and auditable (DQ-S4 stays a visible warning) |
| **T6** | Derive `is_grammy_artist` (0/1) and `artist_grammy_awards` per track-artist row by joining the Grammy key population | AR1 segmentation needs a recognition flag per row | new columns | row with `artist_key='adele'` → `is_grammy_artist=1`, `artist_grammy_awards=11` | key absent from Grammys → flag 0, awards 0 | powers KPI-1 (`Grammy-recognized` vs `other`) |
| **T7** | Derive `duration_min = round(duration_ms/60000, 2)` | presentation measure for dashboards | new column | `210000` → `3.5` | n/a | dashboard readability |
| **T8** | Grammy side: `artist_key = normalize_artist_name(artist)` (null stays null) | 1,840 rows (38.25%) have no artist credit — a known structural gap (DQ-G5 warning), not an error to hide | `artist` → `artist_key` | `Beyoncé` → `beyonce`, `NaN` → `None` | null preserved and measured (never dropped) | keeps the 4,810-row award balance (see reconciliation) |
| **T9** | Derive `winner_flag = 1/0` from the boolean text `winner` | DQ-G3 guarantees the literal domain; the DW stores an int | `winner` → `winner_flag` | `True` → `1` | value outside `{True,False}` → 0 (would already be blocked by DQ-G3 critical) | AR3/AR4 measures over winners |
| **T10** | Derive `is_matched_spotify` and `spotify_track_count` per award row | AR4 needs catalogue coverage per awardee; unmatched rows must be *measured* | new columns | matched → `1` + count; unmatched → `0`, count 0 | rows without artist → not matched, retained | KPI-0, KPI-4, DQ-P11 |
| **T11** | Emit integration metrics consumed by the prepared gate | DQ-P10/P11/P12 operate on measured outcomes, not assumptions | `prepared_metrics.csv` | 1-row metric file | n/a | closes the quality loop |

## 2. Integration contract

| Contract item | Decision and evidence |
| --- | --- |
| **Integration key(s)** | `artist_key = normalize_artist_name(credit)`; Spotify side splits on `;` (1..n credits per track), Grammy side uses the whole `artist` string (0..1 key per award). No shared identifier (ISRC/artist id) exists in either source → the contract is **name-based by necessity**. |
| **Cardinality** | Spotify track row → 1..n artists (one-to-many, verified: 113,549 track rows → 157,530 track-artist rows, avg 1.39); Grammy award row → 0..1 artist_key; artist ↔ track rows one-to-many; artist ↔ award rows one-to-many; **cross-source relation is many-to-many** (one key can own both many tracks and many awards). |
| **Preprocessing before matching** | T4 only: NFKD accent folding, case folding, whitespace collapse, quote/period stripping, `(Various Artists)` canonicalisation. No fuzzy matching, no transliteration tables, no manual alias lists — every transformation is deterministic and reversible from the key. |
| **Unmatched records** | Never dropped. Every award row carries `is_matched_spotify ∈ {0,1}`; counts are measured (`grammy_rows_matched=1,395`, `unmatched_artist_rows=1,575` with a credit, 1,840 without) and gated as a *trend* by DQ-P11 (≥25%, observed 29.0021%). Unmatched rows still load, so the DW can report coverage. |
| **Duplicate / ambiguous matches** | Detected as `normalized_display_name_conflicts` — **90 keys** where >1 raw display name collapses to one key (e.g. `7 MinutoZ`/`7 MinutoZ`, `AURORA`/`Aurora`, `André Previn`/`Andre Previn`). Merging is intended (they are spelling variants of the same artist) and reported instead of silently ignored; `dim_artist` keeps *one* row per key with the display name seen first, so facts cannot fan out. Award business key `year\|category\|nominee\|artist` has **0 duplicates** (null-safe), so awards never merge with each other. |
| **Assumptions and limitations** | (1) Matching is name-based: identical spelling ⇒ same artist, different spelling ⇒ different artist (1,575 award rows with a credit remain unmatched). (2) Group credits written as a single string (`"A & B"`, `"(Various Artists)"`) are one key. (3) The Grammy CSV contains **only winners** (`winner` = True in 4,810/4,810 rows) — no nomination history. (4) 38.25% of award rows have no artist credit and can never be matched. (5) The Spotify extract keeps the 16 contract columns; `key`, `mode`, `instrumentalness`, `time_signature` are profiled but not loaded. |

## 3. Reconciliation evidence (this batch)

| Check | Source | Prepared | Result |
| --- | --- | --- | --- |
| Spotify rows | 114,000 | 113,549 after T1 (−1) + T2 (−450) → 157,530 exploded | balance explained by T1/T2/T3, no silent loss |
| Grammy rows | 4,810 | **4,810** (no Grammy row is dropped by design) | 4,810 → 4,810 ✔ |
| Prepared grain duplicates | – | `duplicate_grain_rows = 0` | DQ-P10 ✔ |
| Integration | 29,789 Spotify keys, 1,636 Grammy keys | 531 matched keys; 1,395 matched award rows (29.0021%) | DQ-P11 ✔ (≥25%) |
| Artist key completeness | 61.75% of award rows have a credit | `artist_key` present on 61.75% | DQ-P9 ✔ (≥60%) |

Machine-readable outputs: `data/work/transform_summary.json`,
`data/work/prepared_metrics.csv`, and the `transform_and_integrate` task log in
`docs/evidence/runs/airflow_test_a_success_log_transform_and_integrate.txt`.
