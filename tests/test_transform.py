"""Transformation rules T1-T11 on synthetic inputs (offline, isolated config)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import config, transform

SPOTIFY_COLUMNS = [
    "track_id", "artists", "album_name", "track_name", "popularity", "duration_ms",
    "explicit", "danceability", "energy", "valence", "acousticness", "speechiness",
    "liveness", "loudness", "tempo", "track_genre",
]
GRAMMY_COLUMNS = [
    "year", "title", "published_at", "updated_at", "category", "nominee",
    "artist", "workers", "winner",
]


def _track(track_id, artists, genre, popularity=50, duration=200000):
    return {
        "track_id": track_id, "artists": artists, "album_name": "album",
        "track_name": "track", "popularity": popularity, "duration_ms": duration,
        "explicit": False, "danceability": 0.5, "energy": 0.5, "valence": 0.5,
        "acousticness": 0.5, "speechiness": 0.5, "liveness": 0.5, "loudness": -5.0,
        "tempo": 120.0, "track_genre": genre,
    }


def _award(year, category, nominee, artist, winner):
    return {
        "year": year, "title": "Grammy Awards", "published_at": f"{year}-02-01",
        "updated_at": f"{year}-02-02", "category": category, "nominee": nominee,
        "artist": artist, "workers": "", "winner": winner,
    }


@pytest.fixture()
def pipeline_inputs(isolated_config):
    tracks = pd.DataFrame([
        _track("t1", "Beyoncé;Jay-Z", "pop", popularity=80),
        _track("t1", "Beyoncé;Jay-Z", "pop", popularity=70),   # T2 duplicate grain
        _track("t2", "", "rock"),                               # T1 missing artist
        _track("t3", "Beyoncé", "rock", popularity=150),        # T5 out-of-range value
        _track("t4", ' "Drake."', "rap"),                       # T4 quotes/periods
        _track("t5", "André 3000", "hip-hop"),                  # T4 accents
    ])
    awards = pd.DataFrame([
        _award(2020, "Record of the Year", "X", "Beyoncé", "True"),
        _award(2021, "Album of the Year", "Y", "Unknown Person", "False"),
        _award(2019, "Song of the Year", "Z", "", "False"),     # no artist credit
    ])
    tracks.to_csv(config.SPOTIFY_RAW_PATH, index=False)
    awards.to_csv(config.GRAMMY_RAW_PATH, index=False)
    return config


def test_t1_drops_rows_without_artist_key(pipeline_inputs):
    summary = transform.transform_and_integrate()
    assert summary["decisions"]["T1_rows_dropped_missing_artist"] == 1


def test_t2_drops_duplicate_source_grain(pipeline_inputs):
    summary = transform.transform_and_integrate()
    assert summary["decisions"]["T2_rows_dropped_duplicate_grain"] == 1
    metrics = summary["metrics"]
    assert metrics["duplicate_grain_rows"] == 0
    assert metrics["rows_spotify_raw"] == 6
    assert metrics["fact_track_rows"] == 5  # 4 tracks after T1/T2, one explode (2 artists)


def test_t3_explodes_multi_artist_tracks(pipeline_inputs):
    transform.transform_and_integrate()
    prepared = config.read_csv(config.PREPARED_TRACKS_PATH)
    t1 = prepared[prepared["track_id"] == "t1"].sort_values("artist_position")
    assert len(t1) == 2
    assert list(t1["artist_key"]) == ["beyonce", "jay-z"]
    assert list(t1["artist_position"]) == [1, 2]
    assert list(t1["artist_total"]) == [2, 2]


def test_t4_normalizes_artist_keys(pipeline_inputs):
    transform.transform_and_integrate()
    prepared = config.read_csv(config.PREPARED_TRACKS_PATH)
    keys = set(prepared["artist_key"])
    assert {"beyonce", "jay-z", "drake", "andre 3000"} <= keys
    assert "Beyoncé" not in keys
    awards = config.read_csv(config.PREPARED_GRAMMYS_PATH, dtype={"winner_flag": "int64"})
    assert set(awards["artist_key"].dropna()) <= keys | {"unknown person"}


def test_t5_never_repairs_source_values(pipeline_inputs):
    transform.transform_and_integrate()
    prepared = config.read_csv(config.PREPARED_TRACKS_PATH)
    out_of_range = prepared[prepared["popularity"] > 100]
    assert len(out_of_range) == 1
    assert int(out_of_range.iloc[0]["popularity"]) == 150


def test_t9_winner_flag_derivation(pipeline_inputs):
    transform.transform_and_integrate()
    awards = config.read_csv(config.PREPARED_GRAMMYS_PATH, dtype={"winner_flag": "int64"})
    assert len(awards) == 3  # no Grammy row is ever dropped
    flags = dict(zip(awards["nominee"], awards["winner_flag"]))
    assert flags == {"Z": 0, "X": 1, "Y": 0}


def test_t10_match_flags_and_coverage(pipeline_inputs):
    summary = transform.transform_and_integrate()
    awards = config.read_csv(config.PREPARED_GRAMMYS_PATH, dtype={"winner_flag": "int64"})
    matched = dict(zip(awards["nominee"], awards["is_matched_spotify"]))
    assert matched == {"X": 1, "Y": 0, "Z": 0}  # unmatched rows retained, not dropped
    assert summary["metrics"]["grammy_match_rate_pct"] == pytest.approx(33.3333, rel=1e-4)
    assert summary["metrics"]["matched_artist_keys"] == 1


def test_is_grammy_artist_flag(pipeline_inputs):
    transform.transform_and_integrate()
    prepared = config.read_csv(config.PREPARED_TRACKS_PATH)
    grammy_rows = prepared[prepared["is_grammy_artist"] == 1]
    assert set(grammy_rows["artist_key"]) == {"beyonce"}
    assert len(grammy_rows) == 2  # t1 (beyonce leg) + t3; jay-z/andre/drake stay 0


def test_summary_and_outputs_are_written(pipeline_inputs):
    summary = transform.transform_and_integrate()
    assert config.TRANSFORM_SUMMARY_PATH.exists()
    for key in ("prepared_tracks", "prepared_grammys", "prepared_metrics"):
        assert summary["outputs"][key]
        assert Path(summary["outputs"][key]).exists()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Beyoncé", "beyonce"),
        ("  Drake. ", "drake"),
        ('"Jay-Z"', "jay-z"),
        ("(Various Artists)", "various artists"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_artist_name(value, expected):
    assert transform.normalize_artist_name(value) == expected
