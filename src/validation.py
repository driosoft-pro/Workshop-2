"""Great Expectations validation gates for the reliable music pipeline.

Design (Workshop-2, section 6.6):

* Expectation          -> a GX check that implements one documented quality rule
                          (RULES catalog below maps Rule ID -> expectation).
* Expectation Suite    -> coherent group of checks for one dataset/layer.
* Validation Definition-> explicit association between a batch definition and a suite.
* Checkpoint           -> controlled execution that produces a Validation Result.
* Evidence             -> every run is serialized to docs/evidence/gx/<stage>/.

Stages:
    raw_spotify      - raw gate for the Spotify CSV branch
    raw_grammys      - raw gate for the Grammy source-database branch
    prepared_tracks  - prepared gate: transformed Spotify track facts
    prepared_grammys - prepared gate: transformed Grammy award facts
    prepared_metrics - prepared gate: integration integrity metrics
    prepared_bridge  - prepared gate: award-artist bridge grain

Severity policy (identical for every stage):
    CRITICAL -> the calling Airflow task fails and the downstream path is blocked.
    WARNING  -> logged and reported, execution continues (documented policy).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import great_expectations as gx
from great_expectations.checkpoint.checkpoint import CheckpointResult
from great_expectations.expectations.metadata_types import FailureSeverity

from src import config
from src.mappings import AGGREGATE_CREDITS, CATEGORY_FAMILIES, GENRE_FAMILIES

CRITICAL = FailureSeverity.CRITICAL
WARNING = FailureSeverity.WARNING
INFO = FailureSeverity.INFO

# ---------------------------------------------------------------------------
# Quality rule catalog - full justification lives in docs/quality_rules.md
# ---------------------------------------------------------------------------
RULES: dict[str, dict] = {
    "DQ-S1": {"layer": "raw_spotify", "attribute": "track_id", "dimension": "Completeness",
              "rule": "track_id must never be null", "threshold": "100%",
              "severity": "critical", "requirement": "R1,R2,R3"},
    "DQ-S2": {"layer": "raw_spotify", "attribute": "artists", "dimension": "Completeness",
              "rule": "artists (integration key) must be present in >= 99.9% of rows",
              "threshold": "99.9%", "severity": "critical", "requirement": "R1,R2,R3"},
    "DQ-S3": {"layer": "raw_spotify", "attribute": "popularity", "dimension": "Validity",
              "rule": "popularity must be an integer between 0 and 100",
              "threshold": "100%", "severity": "critical", "requirement": "R1"},
    "DQ-S4": {"layer": "raw_spotify", "attribute": "duration_ms", "dimension": "Validity",
              "rule": "duration_ms must be between 1 ms and 600000 ms (10 min) in >= 99% of rows",
              "threshold": "99%", "severity": "warning", "requirement": "R1"},
    "DQ-S5": {"layer": "raw_spotify", "attribute": "danceability,energy,valence",
              "dimension": "Validity",
              "rule": "audio features used by R3 must lie in [0, 1]",
              "threshold": "100%", "severity": "critical", "requirement": "R3"},
    "DQ-S6": {"layer": "raw_spotify", "attribute": "track_genre", "dimension": "Completeness",
              "rule": "track_genre must be present in >= 99.9% of rows",
              "threshold": "99.9%", "severity": "critical", "requirement": "R2"},
    "DQ-G1": {"layer": "raw_grammys", "attribute": "year", "dimension": "Validity",
              "rule": "year must not be null and must lie between 1958 and the current year",
              "threshold": "100%", "severity": "critical", "requirement": "R3,R4"},
    "DQ-G2": {"layer": "raw_grammys", "attribute": "category", "dimension": "Completeness",
              "rule": "category must never be null", "threshold": "100%",
              "severity": "critical", "requirement": "R4"},
    "DQ-G3": {"layer": "raw_grammys", "attribute": "winner", "dimension": "Validity",
              "rule": "winner must contain only the boolean literals True/False",
              "threshold": "100%", "severity": "critical", "requirement": "R3,R4"},
    "DQ-G4": {"layer": "raw_grammys", "attribute": "nominee", "dimension": "Completeness",
              "rule": "nominee must be present in >= 99.5% of rows",
              "threshold": "99.5%", "severity": "warning", "requirement": "R4"},
    "DQ-G5": {"layer": "raw_grammys", "attribute": "artist", "dimension": "Completeness",
              "rule": "artist (integration key) must be present in >= 60% of rows",
              "threshold": "60%", "severity": "warning", "requirement": "R1,R2,R3"},
    "DQ-P1": {"layer": "prepared_tracks", "attribute": "track_id", "dimension": "Uniqueness",
              "rule": "prepared track rows must carry a non-null track_id",
              "threshold": "100%", "severity": "critical", "requirement": "R1"},
    "DQ-P2": {"layer": "prepared_tracks", "attribute": "artist_key", "dimension": "Completeness",
              "rule": "every prepared track row must carry a normalized artist key",
              "threshold": "100%", "severity": "critical", "requirement": "R1,R2"},
    "DQ-P3": {"layer": "prepared_tracks", "attribute": "popularity", "dimension": "Validity",
              "rule": "popularity must remain within [0, 100] after transformation",
              "threshold": "100%", "severity": "critical", "requirement": "R1"},
    "DQ-P4": {"layer": "prepared_tracks", "attribute": "danceability,energy,valence",
              "dimension": "Validity",
              "rule": "audio features must remain within [0, 1] after transformation",
              "threshold": "100%", "severity": "critical", "requirement": "R3"},
    "DQ-P5": {"layer": "prepared_tracks", "attribute": "is_grammy_artist",
              "dimension": "Validity",
              "rule": "is_grammy_artist must be 0 or 1", "threshold": "100%",
              "severity": "critical", "requirement": "R1,R2"},
    "DQ-P6": {"layer": "prepared_grammys", "attribute": "year", "dimension": "Validity",
              "rule": "award year must lie between 1958 and the current year after transformation",
              "threshold": "100%", "severity": "critical", "requirement": "R3,R4"},
    "DQ-P7": {"layer": "prepared_grammys", "attribute": "category", "dimension": "Completeness",
              "rule": "category must never be null after transformation", "threshold": "100%",
              "severity": "critical", "requirement": "R4"},
    "DQ-P8": {"layer": "prepared_grammys", "attribute": "winner_flag",
              "dimension": "Validity",
              "rule": "winner_flag (derived from winner) must be 0 or 1",
              "threshold": "100%", "severity": "critical", "requirement": "R3"},
    "DQ-P9": {"layer": "prepared_grammys", "attribute": "artist_key",
              "dimension": "Completeness",
              "rule": "at least 60% of prepared award rows must carry an artist key",
              "threshold": "60%", "severity": "warning", "requirement": "R1,R2"},
    "DQ-P10": {"layer": "prepared_metrics", "attribute": "duplicate_grain_rows",
               "dimension": "Uniqueness",
               "rule": "prepared fact grain (track_id, track_genre, artist_key) must be unique",
               "threshold": "0 duplicate rows", "severity": "critical", "requirement": "R1"},
    "DQ-P11": {"layer": "prepared_metrics", "attribute": "grammy_match_rate_pct",
               "dimension": "Consistency",
               "rule": ">= 25% of award rows must resolve to a Spotify artist (integration coverage)",
               "threshold": "25%", "severity": "warning", "requirement": "R1,R2,R3"},
    "DQ-P12": {"layer": "prepared_metrics", "attribute": "fact_track_rows",
               "dimension": "Completeness",
               "rule": "the prepared track fact must contain at least 100000 rows",
               "threshold": "100000 rows", "severity": "critical", "requirement": "R1"},
    # --- upgrade: raw contract, derived families, integration gates --------
    "DQ-S7": {"layer": "raw_spotify", "attribute": "extract column set",
              "dimension": "Completeness",
              "rule": "the raw extract must expose the full 22-column contract "
                      "(20 source columns + source_row_index + duration_min)",
              "threshold": "22 columns", "severity": "critical", "requirement": "R1,R2,R3"},
    "DQ-G6": {"layer": "prepared_grammys", "attribute": "match_method",
              "dimension": "Validity",
              "rule": "match_method must be one of exact, split, workers, nominee, fuzzy, none",
              "threshold": "100% in set", "severity": "critical", "requirement": "R2,R3,R4"},
    "DQ-G7": {"layer": "prepared_grammys", "attribute": "artist_source",
              "dimension": "Validity",
              "rule": "artist_source must be one of credit, workers, nominee, none",
              "threshold": "100% in set", "severity": "critical", "requirement": "R4"},
    "DQ-G8": {"layer": "prepared_tracks", "attribute": "genre_family",
              "dimension": "Completeness",
              "rule": "every prepared row must carry a mapped T14 genre family "
                      "(all 114 source genres are in the dictionary)",
              "threshold": "100% in set", "severity": "critical", "requirement": "R2"},
    "DQ-G9": {"layer": "prepared_grammys", "attribute": "category_family",
              "dimension": "Completeness",
              "rule": "category_family must never be null and at least 90% of rows "
                      "must resolve to a real family (not the Other fallback)",
              "threshold": "100% non-null, >= 90% non-Other",
              "severity": "critical", "requirement": "R4"},
    "DQ-G10": {"layer": "prepared_tracks", "attribute": "song_key,artist_key",
               "dimension": "Uniqueness",
               "rule": "exactly one primary song row per (song_key, artist_key) grain",
               "threshold": "0 duplicates", "severity": "critical", "requirement": "R1"},
    "DQ-G11": {"layer": "prepared_bridge", "attribute": "award_bk,artist_key",
               "dimension": "Uniqueness",
               "rule": "the award-artist bridge grain (award_bk, artist_key) must be unique",
               "threshold": "0 duplicates", "severity": "critical", "requirement": "R1,R2"},
    "DQ-G12": {"layer": "prepared_bridge", "attribute": "artist_key",
               "dimension": "Validity",
               "rule": "no aggregate credit key (various artists, original cast, ...) in bridge",
               "threshold": "0 aggregate keys", "severity": "critical", "requirement": "R1,R2,R3,R4"},
    "DQ-G13": {"layer": "prepared_grammys", "attribute": "recognition_tier",
               "dimension": "Validity",
               "rule": "recognition_tier must be one of A, B, C, none",
               "threshold": "100% in set", "severity": "critical", "requirement": "R1,R2,R3,R4"},
    "DQ-G14": {"layer": "prepared_grammys", "attribute": "recognition_tier,match_method",
               "dimension": "Consistency",
               "rule": "tier consistency: award is unmatched if and only if tier is none",
               "threshold": "100% consistent", "severity": "critical", "requirement": "R1,R2,R3,R4"},
    "DQ-P13": {"layer": "prepared_tracks", "attribute": "is_zero_popularity",
               "dimension": "Validity",
               "rule": "at most 20% of prepared rows may carry popularity == 0",
               "threshold": "<= 20%", "severity": "warning", "requirement": "R1"},
    "DQ-P14": {"layer": "prepared_metrics", "attribute": "grammy_match_rate_pct",
               "dimension": "Consistency",
               "rule": "award-to-Spotify match rate must stay >= 40% and within 2pp of previous batch",
               "threshold": ">= 40% and drop <= 2pp", "severity": "warning", "requirement": "R1,R2"},
    "DQ-P15": {"layer": "prepared_metrics", "attribute": "song_confirmation_rate_pct",
               "dimension": "Consistency",
               "rule": "song confirmation rate (lower bound of precision; Spotify is a sample, most awarded songs are absent)",
               "threshold": "no threshold", "severity": "info", "requirement": "R1"},
    "DQ-P16": {"layer": "prepared_metrics", "attribute": "genre_tie_share_pct",
               "dimension": "Consistency",
               "rule": "artists with an ambiguous (tied) dominant genre must stay at or below 15%",
               "threshold": "<= 15%", "severity": "warning", "requirement": "R2"},
    "DQ-P17": {"layer": "prepared_metrics", "attribute": "tier_c_share_pct",
               "dimension": "Validity",
               "rule": "share of Tier C (Production & Technical craft) among matched awards must stay <= 17.1% (observed + 5pp)",
               "threshold": "<= 17.1%", "severity": "warning", "requirement": "R2"},
}

STAGES = (
    "raw_spotify",
    "raw_grammys",
    "prepared_tracks",
    "prepared_grammys",
    "prepared_metrics",
    "prepared_bridge",
)

DATASOURCE_NAME = "music_pipeline"

STAGE_SPEC: dict[str, dict[str, str]] = {
    "raw_spotify": {
        "asset": "spotify_raw_asset", "batch": "spotify_raw_batch",
        "suite": "spotify_raw_suite", "vd": "spotify_raw_validation",
        "checkpoint": "raw_spotify_checkpoint",
    },
    "raw_grammys": {
        "asset": "grammy_raw_asset", "batch": "grammy_raw_batch",
        "suite": "grammy_raw_suite", "vd": "grammy_raw_validation",
        "checkpoint": "raw_grammy_checkpoint",
    },
    "prepared_tracks": {
        "asset": "prepared_tracks_asset", "batch": "prepared_tracks_batch",
        "suite": "prepared_tracks_suite", "vd": "prepared_tracks_validation",
        "checkpoint": "prepared_tracks_checkpoint",
    },
    "prepared_grammys": {
        "asset": "prepared_grammys_asset", "batch": "prepared_grammys_batch",
        "suite": "prepared_grammys_suite", "vd": "prepared_grammys_validation",
        "checkpoint": "prepared_grammy_checkpoint",
    },
    "prepared_metrics": {
        "asset": "prepared_metrics_asset", "batch": "prepared_metrics_batch",
        "suite": "prepared_metrics_suite", "vd": "prepared_metrics_validation",
        "checkpoint": "prepared_metrics_checkpoint",
    },
    "prepared_bridge": {
        "asset": "prepared_bridge_asset", "batch": "prepared_bridge_batch",
        "suite": "prepared_bridge_suite", "vd": "prepared_bridge_validation",
        "checkpoint": "prepared_bridge_checkpoint",
    },
}


class ValidationGateError(RuntimeError):
    """Raised when a Critical GX expectation fails inside a validation gate."""

    def __init__(self, stage: str, failed_rules: list[dict]):
        self.stage = stage
        self.failed_rules = failed_rules
        details = "; ".join(
            f"{item['rule_id']}({item['expectation']} column={item.get('column')} "
            f"unexpected_count={item['result'].get('unexpected_count')} "
            f"unexpected_percent={item['result'].get('unexpected_percent')})"
            for item in failed_rules
        )
        super().__init__(
            f"[{stage}] CRITICAL data-quality failure - downstream processing blocked. {details}"
        )


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and value != value:
        return None
    return value


def get_last_committed_match_rate(engine=None) -> float | None:
    """Read the last committed batch match rate from etl_batch_log."""
    if engine is None:
        try:
            from src.load import get_engine
            engine = get_engine()
        except Exception:
            return None
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT notes FROM etl_batch_log WHERE status = 'success' ORDER BY finished_at DESC LIMIT 1")
            ).fetchone()
            if row and row[0]:
                data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                if isinstance(data, dict):
                    val = data.get("match_rate_pct", data.get("grammy_match_rate_pct"))
                    if val is not None:
                        fval = float(val)
                        return fval / 100.0 if fval > 1.0 else fval
    except Exception:
        return None
    return None


def evaluate_match_rate_threshold(
    current_rate: float,
    previous_rate: float | None = None,
    min_rate: float = 0.40,
    max_drop: float = 0.02,
) -> dict:
    """
    DQ-P14 check:
    warning if rate < 0.40 OR drops > 2pp vs previous committed batch.
    If previous_rate is None -> pass (if >= min_rate).
    Accepts rates either as fractions (0.0-1.0) or percentages (0-100).
    """
    curr = current_rate / 100.0 if current_rate > 1.0 else current_rate
    prev = (previous_rate / 100.0 if previous_rate > 1.0 else previous_rate) if previous_rate is not None else None

    passed = True
    reasons = []

    if curr < min_rate:
        passed = False
        reasons.append(f"match rate {curr:.4f} is below minimum {min_rate:.4f}")

    if prev is not None:
        drop = prev - curr
        if drop > max_drop:
            passed = False
            reasons.append(
                f"match rate dropped by {drop*100:.2f}pp vs previous batch ({prev:.4f} -> {curr:.4f}), "
                f"exceeding {max_drop*100:.1f}pp limit"
            )

    return {
        "success": passed,
        "current_rate": curr,
        "previous_rate": prev,
        "drop": (prev - curr) if prev is not None else None,
        "reasons": reasons,
        "severity": "warning" if not passed else "pass",
    }


def get_context():

    project_root = str(config.GX_PROJECT_ROOT)
    context = gx.get_context(mode="file", project_root_dir=project_root)
    actual = Path(getattr(context, "root_directory", config.GX_DIR))
    if actual != config.GX_DIR:
        print(f"[gx] context root {actual} differs from configured {config.GX_DIR}")
    return context


def _get_or_add(add_callable, get_callable, name: str):
    try:
        return get_callable(name)
    except Exception:
        return add_callable()


def _expected_rule_signatures(stage: str) -> list[tuple]:
    """Rule signatures (rule_id, severity, requirement) ``_add_expectations`` would register for ``stage``."""
    probe = gx.ExpectationSuite(name="__coverage_probe__")
    _add_expectations(probe, stage)
    return [
        (item.meta.get("rule_id"), item.meta.get("severity"), item.meta.get("requirement"))
        for item in probe.expectations
    ]


def _rebuild_stage(context, spec: dict, stage: str) -> None:
    """Delete and recreate one stage's suite, validation definition and checkpoint."""
    for store, name in (
        (context.checkpoints, spec["checkpoint"]),
        (context.validation_definitions, spec["vd"]),
        (context.suites, spec["suite"]),
    ):
        try:
            store.delete(name)
        except Exception:  # noqa: BLE001 - absent asset, nothing to rebuild
            pass
    suite = context.suites.add(gx.ExpectationSuite(name=spec["suite"]))
    _add_expectations(suite, stage)


def ensure_assets(context=None):
    context = context or get_context()

    datasource = _get_or_add(
        lambda: context.data_sources.add_pandas(DATASOURCE_NAME),
        lambda n: context.data_sources.get(n),
        DATASOURCE_NAME,
    )

    handles: dict[str, dict] = {}
    for stage, spec in STAGE_SPEC.items():
        asset = _get_or_add(
            lambda a=spec["asset"]: datasource.add_dataframe_asset(a),
            lambda n: datasource.get_asset(n),
            spec["asset"],
        )
        batch_definition = _get_or_add(
            lambda a=asset, b=spec["batch"]: a.add_batch_definition_whole_dataframe(b),
            lambda n, a=asset: a.get_batch_definition(n),
            spec["batch"],
        )
        suite = _get_or_add(
            lambda s=spec["suite"]: context.suites.add(gx.ExpectationSuite(name=s)),
            lambda n: context.suites.get(n),
            spec["suite"],
        )
        current_signatures = [
            (item.meta.get("rule_id"), item.meta.get("severity"), item.meta.get("requirement"))
            for item in suite.expectations
        ]
        if current_signatures != _expected_rule_signatures(stage):
            # The stored suite predates the current RULES catalogue (a rule or
            # metadata was added or modified): rebuild this stage's assets so
            # the store and the code can never drift apart. Configuration only -
            # evidence files are never touched.
            _rebuild_stage(context, spec, stage)
            suite = context.suites.get(spec["suite"])

        validation_definition = _get_or_add(
            lambda v=spec["vd"], b=batch_definition, s=suite: context.validation_definitions.add(
                gx.ValidationDefinition(name=v, data=b, suite=s)
            ),
            lambda n: context.validation_definitions.get(n),
            spec["vd"],
        )
        checkpoint = _get_or_add(
            lambda c=spec["checkpoint"], v=validation_definition: context.checkpoints.add(
                gx.Checkpoint(
                    name=c,
                    validation_definitions=[v],
                    result_format={"result_format": "SUMMARY"},
                )
            ),
            lambda n: context.checkpoints.get(n),
            spec["checkpoint"],
        )
        handles[stage] = {
            "batch_definition": batch_definition,
            "suite": suite,
            "validation_definition": validation_definition,
            "checkpoint": checkpoint,
        }
    return handles


def _expect(suite, expectation_type, rule_id: str, severity: str, **kwargs):
    rule = RULES[rule_id]
    meta = {
        "rule_id": rule_id,
        "severity": severity,
        "quality_dimension": rule["dimension"],
        "requirement": rule["requirement"],
    }
    expectation = expectation_type(meta=meta, severity=severity, **kwargs)
    suite.add_expectation(expectation)
    return expectation


def _add_expectations(suite, stage: str) -> None:
    if stage == "raw_spotify":
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-S1", "critical", column="track_id", mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-S2", "critical", column="artists", mostly=0.999)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-S3", "critical", column="popularity", min_value=0, max_value=100)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-S4", "warning", column="duration_ms", min_value=1, max_value=600000,
                mostly=0.99)
        for column in ("danceability", "energy", "valence"):
            _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                    "DQ-S5", "critical", column=column, min_value=0, max_value=1)
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-S6", "critical", column="track_genre", mostly=0.999)
        _expect(suite, gx.expectations.ExpectTableColumnsToMatchSet,
                "DQ-S7", "critical",
                column_set=list(config.SPOTIFY_REQUIRED_COLUMNS), exact_match=True)

    elif stage == "raw_grammys":
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-G1", "critical", column="year", mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-G1", "critical", column="year", min_value=1958,
                max_value=datetime.now(timezone.utc).year)
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-G2", "critical", column="category", mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-G3", "critical", column="winner", value_set=["True", "False"])
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-G4", "warning", column="nominee", mostly=0.995)
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-G5", "warning", column="artist", mostly=0.60)

    elif stage == "prepared_tracks":
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-P1", "critical", column="track_id", mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-P2", "critical", column="artist_key", mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P3", "critical", column="popularity", min_value=0, max_value=100)
        for column in ("danceability", "energy", "valence"):
            _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                    "DQ-P4", "critical", column=column, min_value=0, max_value=1)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-P5", "critical", column="is_grammy_artist", value_set=[0, 1])
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-G8", "critical", column="genre_family", value_set=GENRE_FAMILIES,
                mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnMeanToBeBetween,
                "DQ-P13", "warning", column="is_zero_popularity",
                min_value=0.0, max_value=0.20)
        _expect(suite, gx.expectations.ExpectCompoundColumnsToBeUnique,
                "DQ-G10", "critical", column_list=["song_key", "artist_key"],
                row_condition="is_primary_song == 1", condition_parser="pandas")

    elif stage == "prepared_grammys":
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P6", "critical", column="year", min_value=1958,
                max_value=datetime.now(timezone.utc).year)
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-P7", "critical", column="category", mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-P8", "critical", column="winner_flag", value_set=[0, 1])
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-P9", "warning", column="artist_key", mostly=0.60)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-G6", "critical", column="match_method",
                value_set=["exact", "split", "workers", "nominee", "fuzzy", "none"])
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-G7", "critical", column="artist_source",
                value_set=["credit", "workers", "nominee", "none"])
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeNull,
                "DQ-G9", "critical", column="category_family", mostly=1.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-G9", "critical", column="category_family",
                value_set=CATEGORY_FAMILIES, mostly=0.90)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-G13", "critical", column="recognition_tier",
                value_set=["A", "B", "C", "none"])
        _expect(suite, gx.expectations.ExpectColumnValuesToBeInSet,
                "DQ-G14", "critical", column="recognition_tier",
                value_set=["none"],
                row_condition="match_method == 'none'", condition_parser="pandas")
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeInSet,
                "DQ-G14", "critical", column="recognition_tier",
                value_set=["none"],
                row_condition="match_method != 'none'", condition_parser="pandas")

    elif stage == "prepared_metrics":
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P10", "critical", column="duplicate_grain_rows",
                min_value=0, max_value=0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P11", "warning", column="grammy_match_rate_pct",
                min_value=25.0, max_value=100.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P12", "critical", column="fact_track_rows",
                min_value=100000, max_value=10_000_000)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P14", "warning", column="grammy_match_rate_pct",
                min_value=40.0, max_value=100.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P15", "info", column="song_confirmation_rate_pct",
                min_value=0.0, max_value=100.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P16", "warning", column="genre_tie_share_pct",
                min_value=0.0, max_value=15.0)
        _expect(suite, gx.expectations.ExpectColumnValuesToBeBetween,
                "DQ-P17", "warning", column="tier_c_share_pct",
                min_value=0.0, max_value=17.1)

    elif stage == "prepared_bridge":
        _expect(suite, gx.expectations.ExpectCompoundColumnsToBeUnique,
                "DQ-G11", "critical", column_list=["award_bk", "artist_key"])
        _expect(suite, gx.expectations.ExpectColumnValuesToNotBeInSet,
                "DQ-G12", "critical", column="artist_key",
                value_set=sorted(AGGREGATE_CREDITS))

    else:
        raise ValueError(f"Unknown validation stage: {stage}")


def _result_payload(result, stage: str, run_context: dict) -> dict:
    expectations = []
    for item in result.results:
        config_ = item.expectation_config
        meta = dict(config_.meta or {})
        expectations.append({
            "rule_id": meta.get("rule_id"),
            "quality_dimension": meta.get("quality_dimension"),
            "requirement": meta.get("requirement"),
            "expectation": config_.type,
            "column": config_.kwargs.get("column"),
            "thresholds": {
                key: config_.kwargs.get(key)
                for key in ("mostly", "min_value", "max_value", "value_set")
                if config_.kwargs.get(key) is not None
            },
            "severity": meta.get("severity"),
            "success": bool(item.success),
            "result": {
                key: item.result.get(key)
                for key in (
                    "element_count", "unexpected_count", "unexpected_percent",
                    "partial_unexpected_list", "missing_count", "missing_percent",
                )
                if key in item.result
            },
        })

    max_severity = result.get_max_severity_failure()
    severity_value = None if max_severity is None else max_severity.value

    failed_critical = [
        item for item in expectations
        if not item["success"] and item["severity"] == "critical"
    ]
    failed_warning = [
        item for item in expectations
        if not item["success"] and item["severity"] == "warning"
    ]

    payload = {
        "stage": stage,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_context": run_context,
        "checkpoint": STAGE_SPEC[stage]["checkpoint"],
        "suite": STAGE_SPEC[stage]["suite"],
        "success": bool(result.success),
        "max_failure_severity": severity_value,
        "statistics": result.statistics,
        "failed_critical_rules": [item["rule_id"] for item in failed_critical],
        "failed_warning_rules": [item["rule_id"] for item in failed_warning],
        "expectations": expectations,
    }

    payload = _json_safe(payload)

    directory = config.GX_RESULTS_DIR / stage
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    run_id = str(run_context.get("run_id", "manual")).replace("/", "_")
    evidence_path = directory / f"{stamp}_{run_id}.json"
    evidence_path.write_text(json.dumps(payload, indent=2, default=str))
    payload["evidence_path"] = str(evidence_path)
    return payload


def run_stage(
    stage: str,
    dataframe: pd.DataFrame,
    run_context: dict | None = None,
) -> dict:
    if stage not in STAGES:
        raise ValueError(f"Unknown validation stage: {stage}")

    handles = ensure_assets()
    checkpoint = handles[stage]["checkpoint"]
    run_context = run_context or {"run_id": "manual"}

    result: CheckpointResult = checkpoint.run(
        batch_parameters={"dataframe": dataframe}
    )

    validation_results = list(result.run_results.values())
    if len(validation_results) != 1:
        raise RuntimeError(
            f"[{stage}] expected exactly one validation result, got {len(validation_results)}"
        )

    payload = _result_payload(validation_results[0], stage, run_context)

    print(f"[gx] stage={stage} success={payload['success']} "
          f"max_severity={payload['max_failure_severity']} stats={payload['statistics']}")
    print(f"[gx] failed critical rules: {payload['failed_critical_rules'] or 'none'}")
    print(f"[gx] failed warning rules:  {payload['failed_warning_rules'] or 'none'}")
    print(f"[gx] evidence: {payload['evidence_path']}")
    return payload


def enforce_policy(payload: dict) -> dict:
    """Apply the documented severity policy to a validation payload."""
    if payload["max_failure_severity"] == CRITICAL.value:
        failed = [
            item for item in payload["expectations"]
            if not item["success"] and item["severity"] == "critical"
        ]
        raise ValidationGateError(payload["stage"], failed)

    if payload["max_failure_severity"] == WARNING.value:
        print(
            f"[policy:{payload['stage']}] WARNING-level failures "
            f"{payload['failed_warning_rules']} - documented policy allows continuation."
        )

    print(f"[policy:{payload['stage']}] gate passed according to policy.")
    return payload


def validate_gate(stage: str, dataframe: pd.DataFrame, run_context: dict | None = None) -> dict:
    payload = run_stage(stage, dataframe, run_context=run_context)
    return enforce_policy(payload)


def _load_stage_frame(stage: str, path: Path) -> pd.DataFrame:
    if stage == "raw_grammys":
        return config.read_csv(path, dtype={"winner": "string"})
    if stage == "prepared_grammys":
        return config.read_csv(path, dtype={"winner_flag": "int64"})
    return config.read_csv(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Great Expectations gate utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create/refresh GX assets (suites, definitions, checkpoints)")

    run_parser = sub.add_parser("run", help="Run one validation stage against a file")
    run_parser.add_argument("--stage", required=True, choices=list(STAGES))
    run_parser.add_argument("--file", required=True)
    run_parser.add_argument("--enforce", action="store_true",
                            help="Exit non-zero when a Critical expectation fails")

    show_parser = sub.add_parser("rules", help="Print the quality rule catalog")
    show_parser.add_argument("--stage", help="Filter by layer")

    args = parser.parse_args()
    config.ensure_directories()

    if args.command == "init":
        handles = ensure_assets()
        print(f"GX assets ready at {config.GX_DIR}")
        for stage, handle in handles.items():
            suite = handle["suite"]
            print(f"  {stage}: suite={suite.name} expectations={len(suite.expectations)} "
                  f"checkpoint={STAGE_SPEC[stage]['checkpoint']}")
        return 0

    if args.command == "rules":
        for rule_id, rule in RULES.items():
            if args.stage and rule["layer"] != args.stage:
                continue
            print(f"{rule_id:6} {rule['layer']:18} {rule['dimension']:12} "
                  f"{rule['severity']:10} {rule['threshold']:14} {rule['rule']}")
        return 0

    frame = _load_stage_frame(args.stage, Path(args.file))
    payload = run_stage(args.stage, frame, run_context={"run_id": "manual-cli"})
    if args.enforce:
        try:
            enforce_policy(payload)
        except ValidationGateError as error:
            print(f"[gate] {error}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
