"""Transformation, harmonization and cross-source integration.

Every rule applied here is documented in docs/transformation_integration.md
and is justified independently of the current validation result:

    T1  Drop Spotify rows whose `artists` value is null/blank.
        Evidence: 1 of 114,000 rows (profiling notebook, completeness table).
        Rationale: the integration contract cannot be satisfied without an
        integration key; the row cannot contribute to AR1-AR3.
    T2  Remove duplicate rows at the source grain (track_id, track_genre),
        keeping the first occurrence (sorted deterministically).
        Evidence: 450 repeated (track_id, track_genre) pairs (0.39%).
    T3  Split `artists` on ';' and explode, so the prepared grain becomes
        (track_id, track_genre, artist_key).
    T4  Normalize artist names to an artist_key: NFKD accent folding,
        lowercase, whitespace collapse, surrounding quotes/periods removed,
        "(Various Artists)" canonicalised to "various artists".
    T5  No value repair: out-of-range values are source-quality problems and
        are reported by the raw gate, never silently corrected here.
    T6  Derive is_grammy_artist and artist_grammy_awards by joining the
        Grammy artist_key population to the prepared track rows.
    T7  Derive duration_min from duration_ms (presentation measure).
    T8  Grammy side: normalize artist -> artist_key (null stays null).
    T9  Derive winner_flag (1/0) from the boolean winner column.
    T10 Derive is_matched_spotify and spotify_track_count for every award row.
    T11 Emit integration metrics used by the prepared gate (DQ-P10..DQ-P12).

Integration contract summary
    Key            : artist_key (normalized artist name)
    Cardinality    : Spotify track row -> 1..n artists (one-to-many);
                     Grammy award row -> 0..1 artist_key (nullable);
                     artist <-> track rows: one-to-many;
                     artist <-> award rows: one-to-many;
                     cross-source row relation: many-to-many.
    Unmatched      : measured (counts and percentages in prepared_metrics),
                     retained with is_matched_spotify = 0.
    Duplicate keys : different display names that normalize to the same key are
                     merged on purpose; the merge count is reported as
                     normalized_display_name_conflicts.
    Limitations    : matching is name-based (no ISRC/artist identifiers exist in
                     the provided sources); collaborative Grammy credits stored
                     as a single string ("A & B") frequently remain unmatched.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src import config

QUOTE_CHARS = "\"'`."


def normalize_artist_name(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = " ".join(folded.lower().split())
    folded = folded.strip(QUOTE_CHARS)
    if not folded:
        return None
    if "various artists" in folded:
        return "various artists"
    return folded


def _split_artists(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    parts = [part for part in str(value).split(";")]
    cleaned = []
    for part in parts:
        key = normalize_artist_name(part)
        display = " ".join(str(part).split()).strip(QUOTE_CHARS)
        if key and display:
            cleaned.append((display, key))
    return cleaned


def transform_and_integrate(
    spotify_raw_path: Path | None = None,
    grammy_raw_path: Path | None = None,
) -> dict:
    config.ensure_directories()
    spotify_raw_path = Path(spotify_raw_path or config.SPOTIFY_RAW_PATH)
    grammy_raw_path = Path(grammy_raw_path or config.GRAMMY_RAW_PATH)

    tracks = config.read_csv(spotify_raw_path)
    awards = config.read_csv(grammy_raw_path, dtype={"winner": "string"})
    rows_spotify_raw = len(tracks)
    rows_grammy_raw = len(awards)

    artists_present = tracks["artists"].notna() & (tracks["artists"].astype("string").str.strip() != "")
    rows_dropped_missing_artist = int((~artists_present).sum())
    tracks = tracks[artists_present].copy()

    tracks = tracks.sort_values(["track_id", "track_genre"]).reset_index(drop=True)
    before_dedupe = len(tracks)
    tracks = tracks.drop_duplicates(subset=["track_id", "track_genre"], keep="first")
    rows_dropped_duplicate_grain = before_dedupe - len(tracks)

    tracks["artist_pairs"] = tracks["artists"].map(_split_artists)
    tracks = tracks[tracks["artist_pairs"].map(len) > 0].copy()
    exploded = tracks.explode("artist_pairs").reset_index(drop=True)
    exploded["artist_pair"] = exploded["artist_pairs"]
    exploded["artist_display_name"] = exploded["artist_pair"].map(lambda pair: pair[0])
    exploded["artist_key"] = exploded["artist_pair"].map(lambda pair: pair[1])
    exploded = exploded.drop(columns=["artist_pairs", "artist_pair"])

    exploded["artist_position"] = (
        exploded.groupby(["track_id", "track_genre"]).cumcount() + 1
    )
    exploded["artist_total"] = exploded.groupby(["track_id", "track_genre"])[
        "artist_key"
    ].transform("size")

    exploded["duration_min"] = (exploded["duration_ms"] / 60000).round(2)

    awards["artist_key"] = awards["artist"].map(normalize_artist_name)
    awards["winner_flag"] = (
        awards["winner"].astype("string").str.strip().str.lower().eq("true").astype(int)
    )
    awards["award_bk"] = (
        awards["year"].astype("int64").astype(str)
        + "|"
        + awards["category"].fillna("").astype(str)
        + "|"
        + awards["nominee"].fillna("").astype(str)
        + "|"
        + awards["artist"].fillna("").astype(str)
    )
    awards = awards.drop(columns=["img"], errors="ignore")

    spotify_artist_keys = set(exploded["artist_key"].dropna().unique())
    grammy_artist_keys = set(awards["artist_key"].dropna().unique())
    matched_artist_keys = spotify_artist_keys & grammy_artist_keys

    grammy_awards_per_key = (
        awards.dropna(subset=["artist_key"])
        .groupby("artist_key")
        .size()
        .rename("artist_grammy_awards")
    )
    exploded = exploded.join(grammy_awards_per_key, on="artist_key")
    exploded["artist_grammy_awards"] = (
        exploded["artist_grammy_awards"].fillna(0).astype("int64")
    )
    exploded["is_grammy_artist"] = (
        exploded["artist_key"].isin(grammy_artist_keys).astype("int64")
    )

    spotify_track_count = (
        exploded.drop_duplicates(subset=["artist_key", "track_id", "track_genre"])
        .groupby("artist_key")
        .size()
        .rename("spotify_track_count")
    )
    awards = awards.join(spotify_track_count, on="artist_key")
    awards["spotify_track_count"] = awards["spotify_track_count"].fillna(0).astype("int64")
    awards["is_matched_spotify"] = (
        awards["artist_key"].isin(spotify_artist_keys).astype("int64")
    )

    prepared_tracks = exploded.sort_values(
        ["track_id", "track_genre", "artist_position"]
    ).reset_index(drop=True)
    prepared_grammys = awards.sort_values(["year", "category", "nominee"]).reset_index(
        drop=True
    )

    duplicate_grain_rows = int(
        prepared_tracks.duplicated(
            subset=["track_id", "track_genre", "artist_key"]
        ).sum()
    )
    grammy_rows_with_key = int(prepared_grammys["artist_key"].notna().sum())
    grammy_rows_matched = int(prepared_grammys["is_matched_spotify"].sum())
    grammy_match_rate_pct = round(
        100.0 * grammy_rows_matched / rows_grammy_raw, 4
    )
    grammy_rows_without_artist_pct = round(
        100.0 * (rows_grammy_raw - grammy_rows_with_key) / rows_grammy_raw, 4
    )
    unmatched_artist_rows = int(
        (
            prepared_grammys["artist_key"].notna()
            & (prepared_grammys["is_matched_spotify"] == 0)
        ).sum()
    )

    display_per_key = pd.concat(
        [
            exploded[["artist_key", "artist_display_name"]].rename(
                columns={"artist_display_name": "display_name"}
            ),
            awards.dropna(subset=["artist_key"])[["artist_key", "artist"]].rename(
                columns={"artist": "display_name"}
            ),
        ],
        ignore_index=True,
    ).dropna()
    normalized_display_name_conflicts = int(
        display_per_key.groupby("artist_key")["display_name"].nunique().gt(1).sum()
    )

    metrics = pd.DataFrame(
        [
            {
                "rows_spotify_raw": rows_spotify_raw,
                "rows_grammy_raw": rows_grammy_raw,
                "rows_dropped_missing_artist": rows_dropped_missing_artist,
                "rows_dropped_duplicate_grain": rows_dropped_duplicate_grain,
                "fact_track_rows": len(prepared_tracks),
                "prepared_grammy_rows": len(prepared_grammys),
                "duplicate_grain_rows": duplicate_grain_rows,
                "grammy_rows_with_artist_key": grammy_rows_with_key,
                "grammy_rows_matched": grammy_rows_matched,
                "grammy_match_rate_pct": grammy_match_rate_pct,
                "grammy_rows_without_artist_pct": grammy_rows_without_artist_pct,
                "unmatched_artist_rows": unmatched_artist_rows,
                "spotify_artist_keys": len(spotify_artist_keys),
                "grammy_artist_keys": len(grammy_artist_keys),
                "matched_artist_keys": len(matched_artist_keys),
                "normalized_display_name_conflicts": normalized_display_name_conflicts,
            }
        ]
    )

    prepared_tracks.to_csv(config.PREPARED_TRACKS_PATH, index=False)
    prepared_grammys.to_csv(config.PREPARED_GRAMMYS_PATH, index=False)
    metrics.to_csv(config.PREPARED_METRICS_PATH, index=False)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "spotify_raw": str(spotify_raw_path),
            "grammy_raw": str(grammy_raw_path),
            "rows_spotify_raw": rows_spotify_raw,
            "rows_grammy_raw": rows_grammy_raw,
        },
        "decisions": {
            "T1_rows_dropped_missing_artist": rows_dropped_missing_artist,
            "T2_rows_dropped_duplicate_grain": rows_dropped_duplicate_grain,
            "T3_exploded_to_track_artist_rows": len(prepared_tracks),
            "T4_normalized_artist_keys": len(spotify_artist_keys | grammy_artist_keys),
            "T6_is_grammy_artist_rows": int(prepared_tracks["is_grammy_artist"].sum()),
            "T9_award_rows_with_winner_flag_1": int(prepared_grammys["winner_flag"].sum()),
            "T10_award_rows_matched_to_spotify": grammy_rows_matched,
        },
        "reconciliation": {
            "prepared_tracks_rows": len(prepared_tracks),
            "prepared_grammys_rows": len(prepared_grammys),
            "grammy_row_balance": (
                f"{rows_grammy_raw} source rows -> {len(prepared_grammys)} prepared rows "
                "(no Grammy row is dropped by design)"
            ),
        },
        "outputs": {
            "prepared_tracks": str(config.PREPARED_TRACKS_PATH),
            "prepared_grammys": str(config.PREPARED_GRAMMYS_PATH),
            "prepared_metrics": str(config.PREPARED_METRICS_PATH),
        },
        "metrics": metrics.to_dict(orient="records")[0],
    }
    config.TRANSFORM_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[transform] {json.dumps(summary['decisions'], indent=2)}")
    print(f"[transform] metrics: {summary['metrics']}")
    return summary


def main() -> int:
    summary = transform_and_integrate()
    print(json.dumps(summary["reconciliation"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
