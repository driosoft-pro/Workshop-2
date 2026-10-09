"""Transformation, harmonization and cross-source integration.

Every rule applied here is documented in docs/transformation_integration.md
and is justified independently of the current validation result:

    T1  Drop Spotify rows whose `artists` value is null/blank.
        Evidence: 1 of 114,000 rows (profiling notebook, completeness table).
        Rationale: the integration contract cannot be satisfied without an
        integration key; the row cannot contribute to R1-R3.
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
    T12 Artist matching cascade (exact -> split -> workers -> nominee -> fuzzy
        -> none) with match_method / artist_source, plus the collaborative
        bridge_award_artist frame (one row per matched artist of a credit).
    T13 Category cleaning: category_clean + category_family (src/mappings.py).
    T14 Genre family: GENRE_FAMILY dictionary, 114/114 genres mapped.
    T15 Spotify quality flags + song_key + exactly one is_primary_song per
        (song_key, artist_key). Flags derive; source values never change.
    T16 Artist dominant genre profile (feeds dim_artist).

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
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src import config
from src.artist_match import (
    SONG_TYPE_CATEGORY_RE,
    SpotifyArtistIndex,
    match_award,
)
from src.mappings import (
    QUOTE_CHARS,
    category_family,
    clean_category,
    genre_family,
    norm_key,
    normalize_artist_name,
)

__all__ = ["normalize_artist_name", "transform_and_integrate"]


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


def build_artist_genre_profile(tracks: pd.DataFrame) -> pd.DataFrame:
    """T16 dominant genre per artist (dim_artist).

    Computed on ``is_primary_song = 1`` rows only, so repeated listings of the
    same song in several genres cannot inflate the genre vote. Tie-break:
    more tracks -> higher mean popularity -> alphabetical genre.
    """
    columns = [
        "artist_key", "dominant_genre", "dominant_genre_family",
        "n_genres", "genre_tie",
    ]
    primary = tracks.loc[tracks["is_primary_song"] == 1]
    if primary.empty:
        return pd.DataFrame(columns=columns)

    frame = primary[["artist_key", "track_genre", "popularity"]].copy()
    stats = (
        frame.groupby(["artist_key", "track_genre"])
        .agg(n_tracks=("track_genre", "size"), mean_popularity=("popularity", "mean"))
        .reset_index()
    )
    stats["n_genres"] = stats.groupby("artist_key")["track_genre"].transform("nunique")
    stats["max_tracks"] = stats.groupby("artist_key")["n_tracks"].transform("max")
    stats = stats.sort_values(
        ["artist_key", "n_tracks", "mean_popularity", "track_genre"],
        ascending=[True, False, False, True],
        kind="mergesort",
    )
    top = stats.groupby("artist_key", sort=True).head(1).set_index("artist_key")
    ties = (
        stats[stats["n_tracks"] == stats["max_tracks"]]
        .groupby("artist_key")
        .size()
        .gt(1)
    )
    profile = pd.DataFrame(index=top.index)
    profile["dominant_genre"] = top["track_genre"]
    profile["n_genres"] = top["n_genres"].astype("int64")
    profile["genre_tie"] = profile.index.map(ties).fillna(False).astype(bool)
    profile["dominant_genre_family"] = profile["dominant_genre"].map(genre_family)
    profile = profile.reset_index()
    return profile[columns]


def transform_and_integrate(
    spotify_raw_path: Path | None = None,
    grammy_raw_path: Path | None = None,
    enable_fuzzy: bool = False,
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

    # --- T15: quality flags, song_key and the primary-song selection ------
    exploded["is_zero_popularity"] = (exploded["popularity"] == 0).astype("int64")
    exploded["is_outlier_duration"] = (
        (exploded["duration_ms"] == 0) | (exploded["duration_ms"] > 600000)
    ).astype("int64")
    exploded["is_outlier_loudness"] = (exploded["loudness"] > 0).astype("int64")
    exploded["is_outlier_tempo"] = (exploded["tempo"] <= 0).astype("int64")
    exploded["song_key"] = (
        exploded["track_name"].map(norm_key).fillna("")
        + "|"
        + exploded["artist_display_name"].map(norm_key).fillna("")
    )
    ranked = exploded.sort_values(
        ["song_key", "artist_key", "popularity", "track_id", "track_genre"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    )
    not_primary = ranked.duplicated(subset=["song_key", "artist_key"], keep="first")
    exploded["is_primary_song"] = (~not_primary.reindex(exploded.index)).astype("int64")

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
    # --- T13: category cleaning (source category column is never rewritten) --
    awards["category_clean"] = awards["category"].map(clean_category)
    awards["category_family"] = awards["category_clean"].map(category_family)

    spotify_artist_keys = set(exploded["artist_key"].dropna().unique())
    artist_index = SpotifyArtistIndex(spotify_artist_keys)

    # song titles published by each matched artist (T12 song confirmation)
    name_keys = exploded[["artist_key", "track_name"]].copy()
    name_keys["song_name_key"] = name_keys["track_name"].map(norm_key)
    song_names = (
        name_keys.dropna(subset=["song_name_key"])
        .drop_duplicates()
        .groupby("artist_key")["song_name_key"]
        .apply(set)
    )

    # --- T12: matching cascade --------------------------------------------
    results = [
        match_award(
            artist=artist,
            workers=workers,
            category=category,
            nominee=nominee,
            index=artist_index,
            enable_fuzzy=enable_fuzzy,
        )
        for artist, workers, category, nominee in zip(
            awards["artist"], awards["workers"], awards["category"], awards["nominee"]
        )
    ]
    awards["artist_key"] = [result.artist_key for result in results]
    awards["match_method"] = [result.match_method for result in results]
    awards["artist_source"] = [result.artist_source for result in results]
    awards["credit_artist_count"] = [result.credit_artist_count for result in results]
    awards["is_matched_strict"] = [int(result.is_strict) for result in results]
    awards["is_matched_spotify"] = [int(result.is_matched) for result in results]
    awards["is_song_confirmed"] = [
        int(
            result.is_matched
            and (name_key := norm_key(nominee)) is not None
            and name_key in song_names.get(result.artist_key, set())
        )
        for result, nominee in zip(results, awards["nominee"])
    ]

    bridge_rows = [
        {
            "award_bk": award_bk,
            "artist_key": key,
            "artist_position": position,
            "match_method": result.match_method,
        }
        for award_bk, result in zip(awards["award_bk"], results)
        for position, key in enumerate(result.matched_keys, start=1)
    ]
    bridge = pd.DataFrame(
        bridge_rows,
        columns=["award_bk", "artist_key", "artist_position", "match_method"],
    )

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

    prepared_tracks = exploded.sort_values(
        ["track_id", "track_genre", "artist_position"]
    ).reset_index(drop=True)
    prepared_grammys = awards.sort_values(["year", "category", "nominee"]).reset_index(
        drop=True
    )

    # --- T16: artist dominant genre profile (consumed by load/dim_artist) --
    artist_profile = build_artist_genre_profile(prepared_tracks)

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

    # --- T11/T12 integration report ---------------------------------------
    total_awards = len(prepared_grammys)
    strict_rows = int(prepared_grammys["is_matched_strict"].sum())
    method_counts = (
        prepared_grammys["match_method"].value_counts().reindex(
            ["exact", "split", "workers", "nominee", "fuzzy", "none"], fill_value=0
        )
    )
    method_rates = {
        method: {
            "rows": int(count),
            "share_pct": round(100.0 * int(count) / total_awards, 4) if total_awards else 0.0,
        }
        for method, count in method_counts.items()
    }
    song_rows = prepared_grammys[
        prepared_grammys["category_clean"].fillna("").map(
            lambda text: bool(SONG_TYPE_CATEGORY_RE.search(text))
        )
    ]
    song_matched_rows = int(song_rows["is_matched_spotify"].sum())
    song_confirmed_rows = int(song_rows["is_song_confirmed"].sum())
    song_confirmation_rate_pct = (
        round(100.0 * song_confirmed_rows / song_matched_rows, 4)
        if song_matched_rows
        else 0.0
    )
    decade_frame = prepared_grammys.copy()
    decade_frame["decade"] = (decade_frame["year"] // 10 * 10).astype(int)
    by_decade = {
        str(decade): {
            "rows": int(group.shape[0]),
            "matched": int(group["is_matched_spotify"].sum()),
            "match_rate_pct": round(
                100.0 * int(group["is_matched_spotify"].sum()) / int(group.shape[0]), 4
            ),
        }
        for decade, group in decade_frame.groupby("decade")
    }
    strict_match_rate_pct = round(100.0 * strict_rows / total_awards, 4) if total_awards else 0.0
    workers_recovered = int(
        (prepared_grammys["match_method"] == "workers").sum()
    )
    split_recovered = int((prepared_grammys["match_method"] == "split").sum())
    nominee_recovered = int((prepared_grammys["match_method"] == "nominee").sum())
    fuzzy_recovered = int((prepared_grammys["match_method"] == "fuzzy").sum())
    genre_tie_share = (
        round(100.0 * float(artist_profile["genre_tie"].mean()), 4)
        if len(artist_profile)
        else 0.0
    )

    integration_metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_grammy": total_awards,
        "rows_spotify": len(prepared_tracks),
        "match_rate_pct": grammy_match_rate_pct,
        "match_rate_strict_pct": strict_match_rate_pct,
        "match_rate_by_method": method_rates,
        "match_rate_by_decade": by_decade,
        "song_confirmation_rate_pct": song_confirmation_rate_pct,
        "song_type_rows": int(len(song_rows)),
        "song_type_matched_rows": song_matched_rows,
        "workers_recovered": workers_recovered,
        "split_recovered": split_recovered,
        "nominee_recovered": nominee_recovered,
        "fuzzy_recovered": fuzzy_recovered,
        "bridge_rows": int(len(bridge)),
        "artist_keys_with_genre_tie": int(artist_profile["genre_tie"].sum()),
        "genre_tie_share_pct": genre_tie_share,
        "primary_song_rows": int(prepared_tracks["is_primary_song"].sum()),
        "enable_fuzzy": bool(enable_fuzzy),
    }

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
                "grammy_match_rate_strict_pct": strict_match_rate_pct,
                "grammy_rows_without_artist_pct": grammy_rows_without_artist_pct,
                "unmatched_artist_rows": unmatched_artist_rows,
                "spotify_artist_keys": len(spotify_artist_keys),
                "grammy_artist_keys": len(grammy_artist_keys),
                "matched_artist_keys": len(matched_artist_keys),
                "normalized_display_name_conflicts": normalized_display_name_conflicts,
                "bridge_award_artist_rows": int(len(bridge)),
                "workers_recovered": workers_recovered,
                "split_recovered": split_recovered,
                "nominee_recovered": nominee_recovered,
                "song_confirmation_rate_pct": song_confirmation_rate_pct,
                "primary_song_rows": integration_metrics["primary_song_rows"],
                "genre_tie_share_pct": genre_tie_share,
                "zero_popularity_share_pct": round(
                    100.0 * float(prepared_tracks["is_zero_popularity"].mean()), 4
                ),
            }
        ]
    )

    prepared_tracks.to_csv(config.PREPARED_TRACKS_PATH, index=False)
    prepared_grammys.to_csv(config.PREPARED_GRAMMYS_PATH, index=False)
    bridge.to_csv(config.BRIDGE_AWARD_ARTIST_PATH, index=False)
    metrics.to_csv(config.PREPARED_METRICS_PATH, index=False)
    config.RUNS_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    config.INTEGRATION_METRICS_PATH.write_text(
        json.dumps(integration_metrics, indent=2, default=str)
    )

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
            "T11_match_rate_strict_pct": strict_match_rate_pct,
            "T12_bridge_award_artist_rows": int(len(bridge)),
            "T12_workers_recovered": workers_recovered,
            "T12_split_recovered": split_recovered,
            "T12_song_confirmation_rate_pct": song_confirmation_rate_pct,
            "T15_primary_song_rows": integration_metrics["primary_song_rows"],
            "T16_artist_genre_ties": int(artist_profile["genre_tie"].sum()),
        },
        "reconciliation": {
            "prepared_tracks_rows": len(prepared_tracks),
            "prepared_grammys_rows": len(prepared_grammys),
            "bridge_award_artist_rows": int(len(bridge)),
            "grammy_row_balance": (
                f"{rows_grammy_raw} source rows -> {len(prepared_grammys)} prepared rows "
                "(no Grammy row is dropped by design)"
            ),
        },
        "outputs": {
            "prepared_tracks": str(config.PREPARED_TRACKS_PATH),
            "prepared_grammys": str(config.PREPARED_GRAMMYS_PATH),
            "prepared_metrics": str(config.PREPARED_METRICS_PATH),
            "bridge_award_artist": str(config.BRIDGE_AWARD_ARTIST_PATH),
            "integration_metrics": str(config.INTEGRATION_METRICS_PATH),
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
