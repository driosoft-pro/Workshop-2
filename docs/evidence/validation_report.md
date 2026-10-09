# Pipeline Validation Report

| ID | Status | Value | Expected |
|---|---|---|---|
| V1 | **PASS** | bridge=2458, fact=2458, without_bridge=0 | equal; 0 |
| V2 | **PASS** | 0 | 0 |
| V3 | **PASS** | 0 | 0 |
| V4 | **PASS** | overall=51.1%, strict=28.05%, unmatched_credit=1278, tier_inconsistencies=0 | tier consistency |
| V5 | **PASS** | rows=4810, matched=2458, bridge=2772 | exact |
| V6 | **PASS** | 0 | 0 |
| V7 | **PASS** | all equal | equal |
| V8 | **PASS** | diff=0.000000 | diff < 1e-6 |
| V9 | **PASS** | core: delta=1.0, CI=[24.68,28.66], p=7.066e-18 | informational |
| V10 | **PASS** | 4 dedupe groups analyzed | informational |
| V11 | **PASS** | genres=114/114, Other_share=0.0000 | 114; <= 0.10 |
| V12 | **PASS** | zero_pop=0.146, genre_tie=0.047 | 0.141 / known / <= 0.15 |
| V13 | **PASS** | AUDIT PENDING | informational |
| V14 | **PASS** | 0 mismatches | 0 mismatches |
| V15 | **PASS** | dashboard found, 22 charts present, filters OK | all OK |
| V16 | **PASS** | all present | present |

### Summary
- Total checks: 16
- PASS: 16
- WARN: 0
- FAIL: 0
- SKIP: 0
