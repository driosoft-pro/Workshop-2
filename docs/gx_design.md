# Great Expectations Design (Automated Data Validation)

Workshop-2, section 6.6. Implementation: `src/validation.py`; project files:
`gx/` (GX **1.23.1**, file-mode data context, `MUSIC_GX_DIR`).

## 1. Design elements

| Element | What it is in this project | Artefact |
| --- | --- | --- |
| **Expectation** | one GX check implementing a declared quality rule; carries `meta.rule_id`, `meta.severity`, `meta.quality_dimension`, `meta.requirement` so every result can be traced back | `gx/expectations/<suite>.json` |
| **Expectation Suite** | the coherent group of checks for one data layer (5 suites: 2 raw, 3 prepared) | same file |
| **Data asset / batch** | CSV read through the `music_pipeline` datasource (pandas asset) with one batch definition per stage | `gx/validation_definitions/*.json` |
| **Validation Definition** | explicit association *suite ↔ asset/batch* (`spotify_raw_validation` = `spotify_raw_suite` on `spotify_raw_asset`) | `gx/validation_definitions/*.json` |
| **Checkpoint / execution** | controlled execution of one validation definition with `result_format: SUMMARY`; run by `validation.run_stage()` / `validate_gate()` | `gx/checkpoints/*_checkpoint.json` |
| **Validation result** | overall `success`, `statistics`, per-rule evidence (expected/unexpected counts, sample values), failed rule ids, run context → written as JSON | `docs/evidence/gx/<stage>/<timestamp>_<run_id>.json` |
| **Policy** | `validation.enforce_policy(payload)`: critical → `ValidationGateError` (gate task fails), warning → recorded + logged | `src/validation.py` |

Suites, validations and checkpoints are created idempotently by
`python -m src.validation init` (development) and are read-only during a DAG
run — a run never rewrites the rule catalogue.

## 2. Layer → suite → validation definition → checkpoint → gate task

| Layer | Suite (expectations) | Validation definition | Checkpoint | Gate task | Data validated |
| --- | --- | --- | --- | --- | --- |
| raw Spotify | `spotify_raw_suite` (8) | `spotify_raw_validation` | `raw_spotify_checkpoint` | `validate_spotify_raw` | `data/work/spotify_raw.csv` (16 contract columns) |
| raw Grammys | `grammy_raw_suite` (6) | `grammy_raw_validation` | `raw_grammy_checkpoint` | `validate_grammys_raw` | `data/work/grammys_raw.csv` |
| prepared tracks | `prepared_tracks_suite` (7) | `prepared_tracks_validation` | `prepared_tracks_checkpoint` | `validate_prepared` | `data/work/prepared_tracks.csv` (157,530 rows) |
| prepared Grammys | `prepared_grammys_suite` (4) | `prepared_grammys_validation` | `prepared_grammy_checkpoint` | `validate_prepared` | `data/work/prepared_grammys.csv` (4,810 rows) |
| prepared metrics | `prepared_metrics_suite` (3) | `prepared_metrics_validation` | `prepared_metrics_checkpoint` | `validate_prepared` | `data/work/prepared_metrics.csv` (integration summary) |

Total: **24 rule IDs → 28 expectations** across 5 checkpoints.

## 3. Rule ID ↔ Expectation mapping

### Raw Spotify — `spotify_raw_suite`

| Rule ID | GX Expectation | Key kwargs | Severity |
| --- | --- | --- | --- |
| DQ-S1 | `expect_column_values_to_not_be_null` | `column=track_id`, `mostly=1.0` | critical |
| DQ-S2 | `expect_column_values_to_not_be_null` | `column=artists`, `mostly=0.999` | critical |
| DQ-S3 | `expect_column_values_to_be_between` | `column=popularity`, `min_value=0`, `max_value=100` | critical |
| DQ-S4 | `expect_column_values_to_be_between` | `column=duration_ms`, `min_value=1`, `max_value=600000`, `mostly=0.99` | warning |
| DQ-S5 (×3) | `expect_column_values_to_be_between` | `column ∈ {danceability, energy, valence}`, `min_value=0`, `max_value=1` | critical |
| DQ-S6 | `expect_column_values_to_not_be_null` | `column=track_genre`, `mostly=0.999` | critical |

### Raw Grammys — `grammy_raw_suite`

| Rule ID | GX Expectation | Key kwargs | Severity |
| --- | --- | --- | --- |
| DQ-G1 (×2) | `expect_column_values_to_not_be_null` / `expect_column_values_to_be_between` | `column=year`; `min_value=1958`, `max_value=<current year>` | critical |
| DQ-G2 | `expect_column_values_to_not_be_null` | `column=category`, `mostly=1.0` | critical |
| DQ-G3 | `expect_column_values_to_be_in_set` | `column=winner`, `value_set=["True","False"]` | critical |
| DQ-G4 | `expect_column_values_to_not_be_null` | `column=nominee`, `mostly=0.995` | warning |
| DQ-G5 | `expect_column_values_to_not_be_null` | `column=artist`, `mostly=0.60` | warning |

### Prepared layers

| Rule ID | GX Expectation | Key kwargs | Severity |
| --- | --- | --- | --- |
| DQ-P1 | `expect_column_values_to_not_be_null` | `column=track_id`, `mostly=1.0` | critical |
| DQ-P2 | `expect_column_values_to_not_be_null` | `column=artist_key`, `mostly=1.0` | critical |
| DQ-P3 | `expect_column_values_to_be_between` | `column=popularity`, 0..100 | critical |
| DQ-P4 (×3) | `expect_column_values_to_be_between` | `column ∈ {danceability, energy, valence}`, 0..1 | critical |
| DQ-P5 | `expect_column_values_to_be_in_set` | `column=is_grammy_artist`, `value_set=[0,1]` | critical |
| DQ-P6 | `expect_column_values_to_be_between` | `column=year`, 1958..current year | critical |
| DQ-P7 | `expect_column_values_to_not_be_null` | `column=category`, `mostly=1.0` | critical |
| DQ-P8 | `expect_column_values_to_be_in_set` | `column=winner_flag`, `value_set=[0,1]` | critical |
| DQ-P9 | `expect_column_values_to_not_be_null` | `column=artist_key`, `mostly=0.60` | warning |
| DQ-P10 | `expect_column_values_to_be_between` | `column=duplicate_grain_rows`, `min_value=0`, `max_value=0` | critical |
| DQ-P11 | `expect_column_values_to_be_between` | `column=grammy_match_rate_pct`, `min_value=25.0`, `max_value=100.0` | warning |
| DQ-P12 | `expect_column_values_to_be_between` | `column=fact_track_rows`, `min_value=100000`, `max_value=10000000` | critical |

## 4. Execution flow inside a gate task

```
validate_gate(stage, frame, run_context) / run_stage(stage, frame, run_context)
    ├─ read the checkpoint (validation definition + suite)      [read-only]
    ├─ run the checkpoint against the in-memory pandas batch
    ├─ enrich each result with rule_id / severity / dimension / requirement
    ├─ write docs/evidence/gx/<stage>/<UTC-stamp>_<run_id>.json
    └─ return payload {success, statistics, expectations[],
                       failed_critical_rules, failed_warning_rules, evidence_path}
enforce_policy(payload)
    ├─ critical failure → raise ValidationGateError(rule ids + counts) → task failed
    └─ otherwise        → log warnings, continue
```

The prepared gate runs all three prepared checkpoints **first** and applies the
policy afterwards, so one run always produces complete diagnostic evidence even
when a later stage would block the load.

## 5. Evidence: successful and failed executions

| Execution | Evidence file | Result |
| --- | --- | --- |
| Test A success | `docs/evidence/gx/raw_spotify/20261003T032258323783_test_a_success.json` + `raw_grammys/…_test_a_success.json` | `success=true`, 8/8 and 6/6 expectations |
| Test A success (prepared) | `prepared_tracks|prepared_grammys|prepared_metrics/*_test_a_success.json` | all 14 prepared expectations pass |
| **Test B controlled failure** | `docs/evidence/gx/raw_spotify/20261003T032430534472_test_b_critical_failure.json` | `success=false`, `max_failure_severity=critical`, `failed_critical_rules=["DQ-S3"]`, `result.partial_unexpected_list=[150]` |
| Test B Grammy gate (control) | `docs/evidence/gx/raw_grammys/20261003T032429936261_test_b_critical_failure.json` | unaffected: `success=true` (the defect is isolated to the Spotify branch) |
| Test C rerun | `…/*_test_c_safe_rerun.json` | identical statistics to Test A |

Evidence JSON schema (machine-readable, one file per run and stage):

```jsonc
{
  "stage": "raw_spotify",
  "generated_at": "…",
  "run_context": {"run_id": "test_b_critical_failure", "dag_id": "reliable_music_pipeline",
                  "task_id": "validate_spotify_raw", "stage": "raw_spotify"},
  "checkpoint": "raw_spotify_checkpoint",
  "suite": "spotify_raw_suite",
  "success": false,
  "max_failure_severity": "critical",
  "statistics": {"evaluated_expectations": 8, "successful_expectations": 7,
                 "unsuccessful_expectations": 1, "success_percent": 87.5},
  "failed_critical_rules": ["DQ-S3"],
  "failed_warning_rules": [],
  "expectations": [
    {"rule_id": "DQ-S3", "expectation": "expect_column_values_to_be_between",
     "column": "popularity", "thresholds": {"min_value": 0.0, "max_value": 100.0},
     "severity": "critical", "success": false,
     "result": {"element_count": 114000, "unexpected_count": 1,
                "unexpected_percent": 0.000877…, "partial_unexpected_list": [150]}}
  ],
  "evidence_path": "docs/evidence/gx/raw_spotify/…json"
}
```

GX's own store (`gx/uncommitted/validations/`) is kept as raw by-product
(git-ignored); the curated copies above are the assessed evidence.
