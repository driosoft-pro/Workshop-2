# Pipeline Validation Report

| ID | Status | Value | Expected |
|---|---|---|---|
| V1 | **SKIP** | DB unreachable | equal; 0 |
| V2 | **SKIP** | DB unreachable | 0 |
| V3 | **SKIP** | DB unreachable | 0 |
| V4 | **PASS** | overall=51.1019%, strict=28.0457% | tier consistency |
| V5 | **PASS** | rows=4810, bridge=2772 | exact |
| V6 | **SKIP** | DB unreachable | 0 |
| V7 | **SKIP** | DB unreachable | equal |
| V8 | **SKIP** | DB unreachable | diff < 1e-6 |
| V9 | **PASS** | core: delta=1.0, CI=[15.0,45.0], p=7.937e-03 | informational |
| V10 | **WARN** | kpi_1_dedupe_impact.csv missing | informational |
| V11 | **PASS** | genres=114/114 mapped | 114; <= 0.10 |
| V12 | **PASS** | zero_pop~0.146, genre_tie=4.6628% | 0.141 / known / <= 0.15 |
| V13 | **PASS** | AUDIT PENDING | informational |
| V14 | **WARN** | 8 mismatches: L53: claims 13 KPIs (actual: 14); L96: claims 34 rules (actual: 38); L99: claims 13 KPIs (actual: 14) | 0 mismatches |
| V15 | **SKIP** | flag --superset not provided | all OK |
| V16 | **PASS** | all present | present |

### Summary
- Total checks: 16
- PASS: 7
- WARN: 2
- FAIL: 0
- SKIP: 7
