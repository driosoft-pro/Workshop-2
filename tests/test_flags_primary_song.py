"""Unit tests for T15 Spotify quality flags and primary song selection.

Tests:
- Exactly one is_primary_song=1 for each (song_key, artist_key) pair.
- Deterministic tie-breaking: max popularity -> min track_id -> alphabetical track_genre.
- Quality flags are purely derived and do not alter source values:
  - is_zero_popularity (popularity == 0)
  - is_outlier_duration (duration_ms == 0 or > 600000)
  - is_outlier_loudness (loudness > 0)
  - is_outlier_tempo (tempo <= 0)
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import config
from src.transform import transform_and_integrate


@pytest.fixture
def run_pipeline_with_synthetic(isolated_config):
    # 3 duplicate listings of the same song by the same artist across different genres/popularities
    spotify = pd.DataFrame([
        {
            "track_id": "T03",
            "artists": "Queen",
            "album_name": "A Night at the Opera",
            "track_name": "Bohemian Rhapsody",
            "popularity": 75,
            "duration_ms": 354000,
            "explicit": False,
            "danceability": 0.41,
            "energy": 0.40,
            "key": 11,
            "loudness": -9.9,
            "mode": 0,
            "speechiness": 0.05,
            "acousticness": 0.28,
            "instrumentalness": 0.0,
            "liveness": 0.24,
            "valence": 0.22,
            "tempo": 144.0,
            "time_signature": 4,
            "track_genre": "rock",
        },
        {
            "track_id": "T01",
            "artists": "Queen",
            "album_name": "Greatest Hits",
            "track_name": "Bohemian Rhapsody",
            "popularity": 85,  # Higher popularity -> should win primary
            "duration_ms": 354000,
            "explicit": False,
            "danceability": 0.41,
            "energy": 0.40,
            "key": 11,
            "loudness": -9.9,
            "mode": 0,
            "speechiness": 0.05,
            "acousticness": 0.28,
            "instrumentalness": 0.0,
            "liveness": 0.24,
            "valence": 0.22,
            "tempo": 144.0,
            "time_signature": 4,
            "track_genre": "classic-rock",
        },
        {
            "track_id": "T02",
            "artists": "Queen",
            "album_name": "Queen Live",
            "track_name": "Bohemian Rhapsody",
            "popularity": 85,  # Tied popularity with T01 -> tie-break by min track_id (T01 < T02)
            "duration_ms": 354000,
            "explicit": False,
            "danceability": 0.41,
            "energy": 0.40,
            "key": 11,
            "loudness": -9.9,
            "mode": 0,
            "speechiness": 0.05,
            "acousticness": 0.28,
            "instrumentalness": 0.0,
            "liveness": 0.24,
            "valence": 0.22,
            "tempo": 144.0,
            "time_signature": 4,
            "track_genre": "hard-rock",
        },
        # Song with outlier values
        {
            "track_id": "T04",
            "artists": "Weird Artist",
            "album_name": "Experimental",
            "track_name": "Extreme Noise",
            "popularity": 0,  # is_zero_popularity = 1
            "duration_ms": 700000,  # is_outlier_duration = 1 (>600000)
            "explicit": True,
            "danceability": 0.1,
            "energy": 0.9,
            "key": 0,
            "loudness": 1.5,  # is_outlier_loudness = 1 (>0)
            "mode": 1,
            "speechiness": 0.8,
            "acousticness": 0.0,
            "instrumentalness": 0.9,
            "liveness": 0.1,
            "valence": 0.1,
            "tempo": 0.0,  # is_outlier_tempo = 1 (<=0)
            "time_signature": 4,
            "track_genre": "industrial",
        },
    ])

    grammy = pd.DataFrame([
        {
            "year": 1976,
            "title": "18th Annual GRAMMY Awards",
            "category": "Record Of The Year",
            "nominee": "Bohemian Rhapsody",
            "artist": "Queen",
            "workers": None,
            "img": None,
            "winner": True,
        }
    ])

    spotify.to_csv(config.SPOTIFY_RAW_PATH, index=False)
    grammy.to_csv(config.GRAMMY_RAW_PATH, index=False)

    summary = transform_and_integrate()
    tracks = pd.read_csv(summary["outputs"]["prepared_tracks"])
    return tracks


def test_primary_song_selection_and_deterministic_ties(run_pipeline_with_synthetic):
    tracks = run_pipeline_with_synthetic

    # Bohemian Rhapsody by Queen has 3 rows
    bohemian_rows = tracks[tracks["track_name"] == "Bohemian Rhapsody"]
    assert len(bohemian_rows) == 3

    # Exactly one is_primary_song = 1
    assert bohemian_rows["is_primary_song"].sum() == 1

    # Winner should be T01 (popularity 85, min track_id between T01 and T02)
    primary_row = bohemian_rows[bohemian_rows["is_primary_song"] == 1].iloc[0]
    assert primary_row["track_id"] == "T01"
    assert primary_row["popularity"] == 85


def test_quality_flags_do_not_alter_source_values(run_pipeline_with_synthetic):
    tracks = run_pipeline_with_synthetic

    weird = tracks[tracks["track_id"] == "T04"].iloc[0]
    assert weird["is_zero_popularity"] == 1
    assert weird["popularity"] == 0  # source value untouched

    assert weird["is_outlier_duration"] == 1
    assert weird["duration_ms"] == 700000  # source value untouched

    assert weird["is_outlier_loudness"] == 1
    assert weird["loudness"] == 1.5  # source value untouched

    assert weird["is_outlier_tempo"] == 1
    assert weird["tempo"] == 0.0  # source value untouched
