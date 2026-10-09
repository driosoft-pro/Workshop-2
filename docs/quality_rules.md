# Data Quality Rules and Validation Design

Workshop-2, sections 6.3, 6.5 and 6.6.
Single source of truth for the catalogue: `RULES` in `src/validation.py`
(38 rule IDs, 45 GX expectations over 6 stages). The profiling evidence behind
each risk is reproducible in [`notebooks/data_profiling.ipynb`](../notebooks/data_profiling.ipynb)
(machine summary: `docs/evidence/profiling_summary.json`).

## 1. Severity policy (as implemented)

| Severity | Meaning | Pipeline action (`validation.enforce_policy`) | Retry |
| --- | --- | --- | --- |
| **critical** | The violation makes continued processing/loading unsafe | Raise `ValidationGateError` → the gate task fails → all downstream tasks are `upstream_failed` (blocked). Evidence JSON is written **before** raising. | never (deterministic) |
| **warning** | Requires visibility but does not invalidate the batch | Logged, returned in the payload (`failed_warning_rules`) and persisted in the evidence JSON; processing continues under this documented policy | n/a |
| **informational** | Monitoring context / trend signal | Recorded in the evidence JSON statistics only | n/a |

No rule currently uses informational severity: every rule either protects a
declared requirement (critical) or documents a known, accepted source defect
(warning). Rules are never added or relaxed to make a batch pass — thresholds
are justified in section 4.

## 2. Quality risk analysis (evidence → risk → requirement)

| Dataset / attribute | Profiling evidence (this batch) | Potential quality risk | Dimension | Related requirement |
| --- | --- | --- | --- | --- |
| Spotify `track_id` | 0 nulls; 24,259 repeated ids (same track in several genres) | null id destroys the fact grain and deduplication | Completeness / Uniqueness | R1 |
| Spotify `artists` | 1 null row (0.0009%); 450 repeated `(track_id, track_genre)` rows | rows without an artist credit cannot be integrated → `artist_key` would be null; duplicate grain would double-count tracks | Completeness / Uniqueness | R1, R2, R3 |
| Spotify `popularity` | 0 values outside [0,100] in the good batch; injected `150` in `spotify_bad.csv` | impossible popularity corrupts every popularity KPI | Validity | R1 |
| Spotify `duration_ms` | 1 row = 0 ms; 603 rows (0.529%) > 10 min; 16 rows > 1 h | zero/near-infinite durations skew average-track metrics | Validity | R1 |
| Spotify `danceability/energy/valence` | 0 values outside [0,1] | out-of-range audio features make R3 profile comparisons meaningless | Validity | R3 |
| Spotify `track_genre` | 0 nulls; exactly 1,000 rows for each of 114 genres | missing genre removes awardees from the genre analysis | Completeness | R2 |
| Spotify `loudness`, `tempo`, `time_signature` | 90 rows loudness > 0 dB; 157 rows tempo ≤ 0; 163 rows time_signature = 0 | suspicious audio metadata — **outside the extract contract**, reported but not gated | Validity | – (scope note) |
| Grammy `year` | 0 nulls; 1958–2019, 62 distinct years, no gaps; `published_at` parseable in 4,810/4,810 rows | invalid years break the decade/year analysis and the `dim_year` join | Validity | R3, R4 |
| Grammy `category` | 0 nulls; 638 distinct values | null category breaks the award dimension grain | Completeness | R4 |
| Grammy `winner` | only the literal `True` (4,810 rows) | non-boolean tokens would silently break the derived `winner_flag`; the dataset contains winners only (documented limitation) | Validity | R3 |
| Grammy `nominee` | 6 nulls (0.1247%) | missing nominee weakens the award business key | Completeness | R4 |
| Grammy `artist` | 1,840 nulls (38.2536%); 1,658 distinct raw credits → 1,636 normalized keys | **the integration key is missing for >1/3 of awards**; name-based matching, no artist ids → unmatched rows | Completeness / Consistency | R1, R2, R3 |
| Cross-source | 531 keys match; 1,395/4,810 award rows matched (29.0021%); 90 normalized keys carry >1 display name | weak or regressed matching would silently empty the joined KPIs; ambiguous display names could double-count artists | Consistency / Uniqueness | R1, R2, R3 |

## 3. Quality rule catalogue

### 3.1 Raw Spotify gate — suite `spotify_raw_suite` (9 expectations)

| Rule | Attribute | Dimension | Rule statement | Metric / threshold | Severity | Justification (evidence / requirement) | Req. |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DQ-S1 | `track_id` | Completeness | `track_id` must never be null | 100% non-null | critical | 0 nulls observed; id anchors the fact grain (R1) | R1,R2,R3 |
| DQ-S2 | `artists` | Completeness | integration key present in ≥ 99.9% of rows | 99.9% (≤114 null rows) | critical | observed 1 null (0.0009%); without a key T1 must drop the row → any large rise means the source contract is broken | R1,R2,R3 |
| DQ-S3 | `popularity` | Validity | integer 0–100 | 100% in range | critical | Spotify API contract; 0 violations in the good batch; **Test B injects 150** and the gate blocks | R1 |
| DQ-S4 | `duration_ms` | Validity | 1 ms ≤ x ≤ 600,000 ms (10 min) | 99% in range | warning | observed 603 rows (0.529%) >10 min and 1 row = 0 ms: real but rare, affects averages not validity → visible, non-blocking (T5: never silently repaired) | R1 |
| DQ-S5 | `danceability`, `energy`, `valence` (3 expectations) | Validity | each in [0,1] | 100% in range | critical | 0 violations observed; R3 profile comparison depends on them | R3 |
| DQ-S6 | `track_genre` | Completeness | genre present in ≥ 99.9% of rows | 99.9% | critical | 0 nulls; 114 genres × 1,000 rows; genre is the R2 dimension | R2 |
| DQ-S7 | extract column set | Completeness | 22-column contract present (20 source cols + source_row_index + duration_min) | 22 columns match set | critical | downstream transforms depend on extended audio features and explicit flag | R1,R2,R3 |

### 3.2 Raw Grammy gate — suite `grammy_raw_suite` (6 expectations)

| Rule | Attribute | Dimension | Rule statement | Metric / threshold | Severity | Justification | Req. |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DQ-G1 | `year` (2 expectations) | Validity | non-null **and** 1958 ≤ year ≤ current year | 100% | critical | observed 1958–2019 with no gaps; lower bound is the first ceremony year, upper bound the current year (can never be exceeded by valid data) | R3,R4 |
| DQ-G2 | `category` | Completeness | never null | 100% | critical | 0 nulls, 638 distinct; grain of `dim_award_category` | R4 |
| DQ-G3 | `winner` | Validity | only boolean literals `True`/`False` | 100% in set | critical | the derived `winner_flag` parses exactly these tokens; the current batch contains only `True` (winners-only dataset — documented limitation, not a passing-by-accident rule) | R3,R4 |
| DQ-G4 | `nominee` | Completeness | present in ≥ 99.5% of rows | 99.5% | warning | observed 6 nulls (0.1247%): the award business key tolerates them (`fillna('')`) → monitor, do not block | R4 |
| DQ-G5 | `artist` | Completeness | present in ≥ 60% of rows | 60% | warning | observed 61.75% present (1,840 nulls = 38.25%): a **critical** rule here would always fail; the defect is real, documented and measured through DQ-P11 instead | R1,R2,R3 |

### 3.3 Prepared-data gates (25 expectations across 4 suites)

| Rule | Stage / attribute | Dimension | Rule statement | Metric / threshold | Severity | Justification | Req. |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DQ-P1 | tracks / `track_id` | Uniqueness | prepared rows carry a non-null `track_id` | 100% | critical | post-transform invariant of T1/T2 | R1 |
| DQ-P2 | tracks / `artist_key` | Completeness | every prepared row has a normalized artist key | 100% | critical | the integration key must exist on every exploded row (T3/T4) | R1,R2 |
| DQ-P3 | tracks / `popularity` | Validity | still within [0,100] after transformation | 100% | critical | transformation must not create invalid values | R1 |
| DQ-P4 | tracks / audio features (3) | Validity | still within [0,1] | 100% | critical | as DQ-P3 | R3 |
| DQ-P5 | tracks / `is_grammy_artist` | Validity | ∈ {0,1} | 100% | critical | derived flag must be boolean-coded for the DW bit/int column | R1,R2 |
| DQ-G8 | tracks / `genre_family` | Completeness | genre_family mapped to one of 12 families | 100% in set | critical | all 114 source genres must be categorized under T14 | R2 |
| DQ-P13 | tracks / `is_zero_popularity` | Validity | share of popularity == 0 rows | ≤ 20% (obs 14.1%) | warning | zero-popularity tracks flagged without value repair (T15) | R1 |
| DQ-G10 | tracks / `song_key, artist_key` | Uniqueness | exactly one primary song per (song_key, artist_key) | 0 duplicates | critical | eliminates duplicate song inflation (T15) | R1 |
| DQ-P6 | grammys / `year` | Validity | 1958 ≤ year ≤ current year | 100% | critical | re-check after type conversion (`int64`) | R3,R4 |
| DQ-P7 | grammys / `category` | Completeness | never null after transformation | 100% | critical | feed of `dim_award_category` | R4 |
| DQ-P8 | grammys / `winner_flag` | Validity | ∈ {0,1} | 100% | critical | derived from `winner` (T9) — proves the conversion happened | R3 |
| DQ-P9 | grammys / `artist_key` | Completeness | ≥ 60% of rows carry a key | 60% | warning | mirrors DQ-G5 (observed 61.75%) — transformation must not lose keys | R1,R2 |
| DQ-G6 | grammys / `match_method` | Validity | match_method in {exact, split, workers, nominee, fuzzy, none} | 100% in set | critical | valid cascade methods recorded under T12 | R2-R4 |
| DQ-G7 | grammys / `artist_source` | Validity | artist_source in {credit, workers, nominee, none} | 100% in set | critical | valid origin provenance recorded under T12 | R4 |
| DQ-G9 | grammys / `category_family` (2) | Completeness | not null (100%) and share Other ≤ 10% | 100% not null, ≥ 90% in families | critical | T13 category family classification | R2 |
| DQ-P10 | metrics / `duplicate_grain_rows` | Uniqueness | prepared grain `(track_id, track_genre, artist_key)` unique | = 0 rows | critical | observed 0 after T2 (450 duplicates removed); any value >0 double-counts facts | R1 |
| DQ-P11 | metrics / `grammy_match_rate_pct` | Consistency | ≥ 25% of award rows resolve to a Spotify artist | ≥ 25% | warning | baseline coverage gate | R1,R2,R3 |
| DQ-P12 | metrics / `fact_track_rows` | Completeness | prepared fact has ≥ 100,000 rows | ≥ 100,000 | critical | observed 157,530; a drop below the threshold means rows were lost in explode/dedupe and every KPI would be understated | R1 |
| DQ-P14 | metrics / `grammy_match_rate_pct` | Consistency | match rate ≥ 40% or drops ≤ 2pp vs previous batch | ≥ 40% / Δ ≤ 2pp | warning | match rate regression gate | all |
| DQ-P15 | metrics / `song_confirmation_rate_pct` | Consistency | song confirmation lower bound (Spotify is a sample) | informational (no threshold) | info | lower bound on precision, not precision itself | R1 |
| DQ-P16 | metrics / `genre_tie_share_pct` | Consistency | artist genre tie share ≤ 15% | ≤ 15% (obs 4.7%) | warning | artist dominant genre tie-breaker health | R2 |
| DQ-P17 | metrics / `tier_C_share_pct` | Consistency | share of Tier C technical awards ≤ 35% | ≤ 35% (obs 12.04%) | warning | bounds non-performing awards share | R1-R4 |
| DQ-G11 | bridge / `award_bk, artist_key` | Uniqueness | bridge grain unique | 0 duplicates | critical | prevents duplicate associations in award-artist bridge (T12) | R4 |
| DQ-G12 | bridge / `artist_key` | Validity | no aggregate credit in bridge | 0 rows in blocklist | critical | prevents generic entities in bridge (T17) | R1-R4 |
| DQ-G13 | grammys / `recognition_tier` | Validity | recognition_tier in {A, B, C, none} | 100% in set | critical | valid recognition tier domain (T18) | R1-R4 |
| DQ-G14 | grammys / tier consistency | Consistency | unmatched ⇔ tier none | 0 inconsistencies | critical | ensures consistent tier labeling (T18) | R1-R4 |

## 4. Threshold reasoning (why these numbers)

* **100% / 0-tolerance rules** protect keys and derived domains where any
  violation makes the load incorrect (`track_id`, `artist_key`, `year`,
  `category`, boolean codes, duplicate grain) — observed violations: none.
* **99.9% (DQ-S2, DQ-S6)** — one observed defective row out of 114,000
  (0.0009%). The threshold tolerates that single known defect plus a small
  margin, but trips long before the integration key becomes unreliable.
* **99% (DQ-S4)** — observed pass rate 99.47% (603 slow outliers). Widening to
  100% would make the rule permanently red without protecting a requirement;
  tightening would block the batch on a known cosmetic defect.
* **60% (DQ-G5/DQ-P9)** — observed 61.75% artist coverage. The threshold is a
  *floor* on the integration key, chosen so that a real regression (e.g. a CSV
  export that stops emitting `artist`) fails while the known 38% structural gap
  (works/collections without a single artist credit) does not.
* **25% (DQ-P11)** — observed 29.0021%. A 10-point headroom below the measured
  rate keeps the check meaningful for detecting matching regressions without
  coupling it to batch-to-batch noise.
* **100,000 rows (DQ-P12)** — the prepared fact is 157,530 rows; the floor sits
  ~36% below it to absorb source growth/shrinkage while still catching a
  structural failure (wrong explode, wrong dedupe key, truncated source).

## 5. Great Expectations design

See [`gx_design.md`](gx_design.md) for suites, validation definitions,
checkpoints, the Rule ID ↔ Expectation mapping and evidence handling.
