"""Dimensional Data Warehouse load (Workshop-2, sections 6.10 and 7.3).

Responsibilities
    1. Build the star-schema tables from the validated prepared datasets.
    2. Materialise every table as CSV in data/output/ (reconciliation evidence
       and a fallback for offline inspection).
    3. Load the Data Warehouse in PostgreSQL using the documented strategy:
           controlled replace = single transaction { delete -> insert }
       Business-key uniqueness constraints remain in place as a backstop, so a
       rerun of the same batch can never silently duplicate analytical rows.
    4. Record the load in etl_batch_log with row counts before and after.

The Grammy SOURCE preparation import (scripts/prepare_source_db.py into
music_source) is a different step and never happens here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src import config
from src.mappings import category_family, clean_category, genre_family
from src.transform import build_artist_genre_profile

# Deletion order matters: the bridge references both facts and dimensions, so
# it is cleared first. Insertion order is dims -> facts -> bridge.
TABLE_ORDER = [
    "bridge_award_artist",
    "fact_track_artist",
    "fact_grammy_award",
    "dim_artist",
    "dim_genre",
    "dim_year",
    "dim_award_category",
]

INSERT_ORDER = (
    "dim_artist",
    "dim_genre",
    "dim_year",
    "dim_award_category",
    "fact_track_artist",
    "fact_grammy_award",
    "bridge_award_artist",
)


def _sql_object(series: pd.Series) -> pd.Series:
    return series.map(lambda value: None if pd.isna(value) else value)


def _sql_int(series: pd.Series) -> pd.Series:
    return series.map(lambda value: None if pd.isna(value) else int(value))


def build_dimensional_frames(
    prepared_tracks_path: Path | None = None,
    prepared_grammys_path: Path | None = None,
    batch_id: str = "manual",
) -> dict[str, pd.DataFrame]:
    tracks = config.read_csv(
        prepared_tracks_path or config.PREPARED_TRACKS_PATH,
        dtype={
            "popularity": "int32",
            "duration_ms": "int64",
            "artist_position": "int32",
            "artist_total": "int32",
            "is_grammy_artist": "int16",
            "artist_grammy_awards": "int32",
            "explicit": "boolean",
        },
    )
    awards = config.read_csv(
        prepared_grammys_path or config.PREPARED_GRAMMYS_PATH,
        dtype={
            "year": "int32",
            "winner_flag": "int16",
            "is_matched_spotify": "int16",
            "spotify_track_count": "int32",
        },
    )

    artist_keys = pd.concat(
        [
            tracks[["artist_key", "artist_display_name"]].rename(
                columns={"artist_display_name": "display_name"}
            ),
            awards.dropna(subset=["artist_key"])[["artist_key", "artist"]].rename(
                columns={"artist": "display_name"}
            ),
        ],
        ignore_index=True,
    ).dropna(subset=["artist_key"])
    artist_keys["display_name"] = artist_keys["display_name"].fillna("").astype(str)

    artist_display = (
        artist_keys[artist_keys["display_name"] != ""]
        .sort_values("artist_key")
        .groupby("artist_key")["display_name"]
        .first()
    )
    display_fallback = (
        artist_keys.sort_values("artist_key").groupby("artist_key")["display_name"].first()
    )

    bridge = config.read_csv(config.BRIDGE_AWARD_ARTIST_PATH)
    if bridge.empty:
        bridge = pd.DataFrame(
            columns=["award_bk", "artist_key", "artist_position", "match_method", "recognition_tier"]
        )

    bridge_award_info = bridge.merge(
        awards[["award_bk", "year", "category"]], on="award_bk", how="left"
    )
    award_counts = (
        bridge_award_info.drop_duplicates(subset=["artist_key", "year", "category"])
        .groupby("artist_key")
        .size()
        .rename("grammy_award_count")
    )
    core_bridge_info = bridge_award_info[bridge_award_info["recognition_tier"].isin(["A", "B"])]
    award_counts_core = (
        core_bridge_info.drop_duplicates(subset=["artist_key", "year", "category"])
        .groupby("artist_key")
        .size()
        .rename("grammy_award_count_core")
    )
    track_counts = tracks.groupby("artist_key").size().rename("spotify_track_count")

    dim_artist = pd.DataFrame({"artist_key": sorted(set(artist_keys["artist_key"]))})
    dim_artist.insert(0, "artist_sk", range(1, len(dim_artist) + 1))
    dim_artist["artist_display_name"] = (
        dim_artist["artist_key"].map(artist_display)
        .fillna(dim_artist["artist_key"].map(display_fallback))
        .fillna(dim_artist["artist_key"])
    )
    dim_artist = (
        dim_artist.merge(award_counts, left_on="artist_key", right_index=True, how="left")
        .merge(award_counts_core, left_on="artist_key", right_index=True, how="left")
        .merge(track_counts, left_on="artist_key", right_index=True, how="left")
    )
    dim_artist["from_spotify"] = dim_artist["spotify_track_count"].fillna(0).gt(0)
    dim_artist["from_grammy"] = dim_artist["grammy_award_count"].fillna(0).gt(0)
    dim_artist["grammy_award_count"] = dim_artist["grammy_award_count"].fillna(0).astype("int32")
    dim_artist["grammy_award_count_core"] = dim_artist["grammy_award_count_core"].fillna(0).astype("int32")
    dim_artist["spotify_track_count"] = dim_artist["spotify_track_count"].fillna(0).astype("int32")
    dim_artist = dim_artist.rename(columns={"artist_key": "artist_bk"})

    # T16: dominant genre profile derived from the primary-song rows only
    genre_profile = build_artist_genre_profile(tracks).rename(
        columns={"artist_key": "artist_bk"}
    )
    dim_artist = dim_artist.merge(genre_profile, on="artist_bk", how="left")
    dim_artist["genre_tie"] = dim_artist["genre_tie"].fillna(False).astype(bool)
    dim_artist = dim_artist[
        [
            "artist_sk",
            "artist_bk",
            "artist_display_name",
            "from_spotify",
            "from_grammy",
            "grammy_award_count",
            "grammy_award_count_core",
            "spotify_track_count",
            "dominant_genre",
            "dominant_genre_family",
            "n_genres",
            "genre_tie",
        ]
    ]

    dim_genre = pd.DataFrame({"genre": sorted(tracks["track_genre"].dropna().unique())})
    dim_genre.insert(0, "genre_sk", range(1, len(dim_genre) + 1))
    dim_genre["genre_family"] = dim_genre["genre"].map(genre_family)

    dim_year = pd.DataFrame({"year": sorted(awards["year"].unique())})
    dim_year["year"] = dim_year["year"].astype("int32")
    dim_year["year_sk"] = dim_year["year"]
    dim_year["decade"] = (dim_year["year"] // 10 * 10).astype("int32")
    dim_year = dim_year[["year_sk", "year", "decade"]]

    dim_award_category = pd.DataFrame(
        {"category": sorted(awards["category"].dropna().unique())}
    )
    dim_award_category.insert(0, "category_sk", range(1, len(dim_award_category) + 1))
    # T13: clean label + family are derived attributes of the raw category
    dim_award_category["category_clean"] = dim_award_category["category"].map(clean_category)
    dim_award_category["category_family"] = dim_award_category["category_clean"].map(
        category_family
    )

    artist_sk = dim_artist[["artist_bk", "artist_sk"]]
    genre_sk = dim_genre[["genre", "genre_sk"]]

    fact_track_artist = tracks.merge(
        artist_sk, left_on="artist_key", right_on="artist_bk", how="left"
    ).merge(genre_sk, left_on="track_genre", right_on="genre", how="left")
    if fact_track_artist["artist_sk"].isna().any() or fact_track_artist["genre_sk"].isna().any():
        raise RuntimeError("fact_track_artist contains unresolved dimension keys")

    fact_track_artist = fact_track_artist[
        [
            "track_id", "track_genre", "artist_sk", "genre_sk", "track_name", "album_name",
            "popularity", "duration_ms", "duration_min", "explicit", "danceability", "energy",
            "valence", "acousticness", "speechiness", "liveness", "loudness", "tempo",
            "artist_position", "artist_total", "is_grammy_artist", "is_grammy_artist_strict",
            "artist_grammy_awards",
            "song_key", "is_zero_popularity", "is_outlier_duration", "is_outlier_loudness",
            "is_outlier_tempo", "is_primary_song",
        ]
    ].copy()
    fact_track_artist["artist_sk"] = fact_track_artist["artist_sk"].astype("int64")
    fact_track_artist["genre_sk"] = fact_track_artist["genre_sk"].astype("int64")
    fact_track_artist["explicit"] = fact_track_artist["explicit"].astype(bool)
    for column in (
        "is_grammy_artist", "is_grammy_artist_strict", "is_zero_popularity",
        "is_outlier_duration", "is_outlier_loudness", "is_outlier_tempo", "is_primary_song",
    ):
        fact_track_artist[column] = fact_track_artist[column].fillna(0).astype("int16")
    fact_track_artist["batch_id"] = batch_id
    fact_track_artist["track_name"] = _sql_object(fact_track_artist["track_name"])
    fact_track_artist["album_name"] = _sql_object(fact_track_artist["album_name"])

    fact_grammy_award = awards.merge(
        artist_sk, left_on="artist_key", right_on="artist_bk", how="left"
    ).merge(dim_year[["year_sk"]], left_on="year", right_on="year_sk", how="left").merge(
        dim_award_category[["category", "category_sk"]],
        on="category",
        how="left",
    )
    if fact_grammy_award["year_sk"].isna().any() or fact_grammy_award["category_sk"].isna().any():
        raise RuntimeError("fact_grammy_award contains unresolved dimension keys")

    fact_grammy_award = fact_grammy_award[
        [
            "award_bk", "artist_sk", "year_sk", "category_sk", "title", "nominee", "artist",
            "workers", "winner", "winner_flag", "is_matched_spotify", "is_matched_strict",
            "is_song_confirmed", "artist_source", "match_method", "recognition_tier",
            "is_aggregate_credit", "credit_artist_count", "spotify_track_count",
        ]
    ].copy()
    fact_grammy_award = fact_grammy_award.rename(columns={"artist": "artist_credit"})
    fact_grammy_award["artist_sk"] = _sql_int(fact_grammy_award["artist_sk"])
    fact_grammy_award["year_sk"] = fact_grammy_award["year_sk"].astype("int32")
    fact_grammy_award["category_sk"] = fact_grammy_award["category_sk"].astype("int64")
    fact_grammy_award["credit_artist_count"] = _sql_int(
        fact_grammy_award["credit_artist_count"]
    ).map(lambda value: 0 if value is None else int(value))
    for column in ("is_matched_strict", "is_song_confirmed", "is_aggregate_credit"):
        fact_grammy_award[column] = fact_grammy_award[column].fillna(0).astype("int16")
    for column in ("artist_source", "match_method", "recognition_tier"):
        fact_grammy_award[column] = _sql_object(fact_grammy_award[column])
    fact_grammy_award["award_count"] = pd.Series(
        1, index=fact_grammy_award.index, dtype="int16"
    )
    fact_grammy_award["batch_id"] = batch_id
    for column in ("title", "nominee", "artist_credit", "workers"):
        fact_grammy_award[column] = _sql_object(fact_grammy_award[column])

    # T12 bridge: award_bk + artist_key are resolved to surrogate keys at load
    bridge = config.read_csv(config.BRIDGE_AWARD_ARTIST_PATH)
    if bridge.empty:
        bridge = pd.DataFrame(
            columns=["award_bk", "artist_key", "artist_position", "match_method", "recognition_tier"]
        )
    artist_sk_map = dim_artist.set_index("artist_bk")["artist_sk"]
    bridge = bridge.copy()
    bridge["artist_sk"] = bridge["artist_key"].map(artist_sk_map)
    if bridge["artist_sk"].isna().any():
        missing = bridge.loc[bridge["artist_sk"].isna(), "artist_key"].unique()[:5]
        raise RuntimeError(f"bridge_award_artist contains unresolved artist keys: {missing}")
    bridge["artist_position"] = bridge["artist_position"].astype("int32")
    bridge["match_method"] = bridge["match_method"].astype(str)
    bridge["recognition_tier"] = bridge["recognition_tier"].fillna("none").astype(str)
    bridge["batch_id"] = batch_id
    bridge = bridge[
        ["award_bk", "artist_sk", "artist_position", "match_method", "recognition_tier", "batch_id"]
    ]
    if bridge.duplicated(subset=["award_bk", "artist_sk"]).any():
        raise RuntimeError("bridge_award_artist violates (award_bk, artist_key) uniqueness")

    return {
        "dim_artist": dim_artist,
        "dim_genre": dim_genre,
        "dim_year": dim_year,
        "dim_award_category": dim_award_category,
        "fact_track_artist": fact_track_artist,
        "fact_grammy_award": fact_grammy_award,
        "bridge_award_artist": bridge,
    }


def _execute_schema(engine) -> None:
    schema_sql = config.SQL_DIR / "dw_schema.sql"
    script = schema_sql.read_text()
    statements = []
    for raw_statement in script.split(";"):
        statement = "\n".join(
            line for line in raw_statement.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ).strip()
        if statement:
            statements.append(statement)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    print(f"[load_dw] schema ensured from {schema_sql}")


def _row_counts(engine, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table in tables:
            counts[table] = int(
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            )
    return counts


def _ensure_dw_database() -> str:
    url = config.DW_DB_URL
    try:
        engine = create_engine(url)
        with engine.connect():
            pass
        return url
    except Exception as error:
        print(f"[load_dw] DW not reachable ({error.__class__.__name__}); attempting creation")

    database = url.rsplit("/", 1)[-1].split("?")[0]
    maintenance_url = url.rsplit("/", 1)[0] + "/postgres"
    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :db"), {"db": database}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
            print(f"[load_dw] created database {database}")
    engine.dispose()
    return url


def load_dw(
    batch_id: str = "manual",
    dag_id: str = "manual",
    run_id: str = "manual",
    strategy: str | None = None,
) -> dict:
    config.ensure_directories()
    strategy = strategy or config.DW_LOAD_STRATEGY
    started_at = datetime.now(timezone.utc)

    frames = build_dimensional_frames(batch_id=batch_id)

    for name, frame in frames.items():
        frame.to_csv(config.OUTPUT_DIR / f"{name}.csv", index=False)

    db_url = _ensure_dw_database()
    engine = create_engine(db_url)
    _execute_schema(engine)

    counts_before = _row_counts(engine, TABLE_ORDER)

    with engine.begin() as connection:
        for table in TABLE_ORDER:
            connection.execute(text(f"DELETE FROM {table}"))

        for name in INSERT_ORDER:
            if name == "bridge_award_artist":
                continue
            frames[name].to_sql(name, connection, if_exists="append", index=False)

        # bridge needs the surrogate key generated for each award row
        award_sk = {
            row[0]: row[1]
            for row in connection.execute(
                text("SELECT award_bk, grammy_award_sk FROM fact_grammy_award")
            )
        }
        bridge = frames["bridge_award_artist"].copy()
        bridge["grammy_award_sk"] = bridge["award_bk"].map(award_sk)
        if bridge["grammy_award_sk"].isna().any():
            raise RuntimeError("bridge_award_artist contains unresolved award_bk values")
        if bridge.duplicated(subset=["grammy_award_sk", "artist_sk"]).any():
            raise RuntimeError("bridge_award_artist violates UNIQUE (grammy_award_sk, artist_sk)")
        bridge[
            [
                "grammy_award_sk", "artist_sk", "artist_position",
                "match_method", "recognition_tier", "batch_id",
            ]
        ].to_sql("bridge_award_artist", connection, if_exists="append", index=False)

        for table, key_column in (
            ("dim_artist", "artist_sk"),
            ("dim_genre", "genre_sk"),
            ("dim_award_category", "category_sk"),
        ):
            connection.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', '{key_column}'), "
                    f"COALESCE((SELECT MAX({key_column}) FROM {table}), 1), "
                    f"EXISTS (SELECT 1 FROM {table}))"
                )
            )

        counts_after = {
            name: int(len(frames[name])) for name in TABLE_ORDER
        }

        finished_at = datetime.now(timezone.utc)
        metrics_path = config.RUNS_EVIDENCE_DIR / "integration_metrics.json"
        if metrics_path.exists():
            try:
                batch_notes = json.dumps(json.loads(metrics_path.read_text()))
            except Exception:
                batch_notes = json.dumps({"description": "controlled replace"})
        else:
            batch_notes = json.dumps({"description": "controlled replace"})

        connection.execute(
            text(
                """
                INSERT INTO etl_batch_log (
                    batch_id, dag_id, run_id, strategy,
                    target_rows_before, target_rows_after,
                    status, started_at, finished_at, notes
                ) VALUES (
                    :batch_id, :dag_id, :run_id, :strategy,
                    CAST(:before AS jsonb), CAST(:after AS jsonb),
                    :status, :started_at, :finished_at, :notes
                )
                ON CONFLICT (batch_id) DO UPDATE SET
                    dag_id = EXCLUDED.dag_id,
                    run_id = EXCLUDED.run_id,
                    strategy = EXCLUDED.strategy,
                    target_rows_before = EXCLUDED.target_rows_before,
                    target_rows_after = EXCLUDED.target_rows_after,
                    status = EXCLUDED.status,
                    started_at = EXCLUDED.started_at,
                    finished_at = EXCLUDED.finished_at,
                    notes = EXCLUDED.notes
                """
            ),
            {
                "batch_id": batch_id,
                "dag_id": dag_id,
                "run_id": run_id,
                "strategy": strategy,
                "before": json.dumps(counts_before),
                "after": json.dumps(counts_after),
                "status": "success",
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "notes": batch_notes,
            },
        )

    summary = {
        "batch_id": batch_id,
        "dag_id": dag_id,
        "run_id": run_id,
        "strategy": strategy,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "row_counts_before": counts_before,
        "row_counts_after": counts_after,
        "outputs": {name: str(config.OUTPUT_DIR / f"{name}.csv") for name in TABLE_ORDER},
    }
    config.LOAD_SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
    engine.dispose()
    print(f"[load_dw] {json.dumps(summary, indent=2)}")
    return summary


def main() -> int:
    load_dw()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
