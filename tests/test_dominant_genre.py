"""Unit tests for T16 dominant genre resolution (src/transform.py build_artist_genre_profile).

Tests:
- Dominant genre chosen by most tracks on primary songs.
- Tie-break 1: higher mean popularity when track count is equal.
- Tie-break 2: alphabetical genre when both track count and mean popularity are equal.
- Flag genre_tie is True when multiple genres share the maximum track count.
- n_genres counts unique genres for the artist.
- dominant_genre_family maps to the correct family.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.transform import build_artist_genre_profile


def test_dominant_genre_by_track_count():
    # Artist A has 2 rock tracks and 1 pop track
    tracks = pd.DataFrame([
        {"artist_key": "artist_a", "track_genre": "rock", "popularity": 50, "is_primary_song": 1},
        {"artist_key": "artist_a", "track_genre": "rock", "popularity": 60, "is_primary_song": 1},
        {"artist_key": "artist_a", "track_genre": "pop", "popularity": 80, "is_primary_song": 1},
    ])
    profile = build_artist_genre_profile(tracks)
    row = profile.iloc[0]
    assert row["artist_key"] == "artist_a"
    assert row["dominant_genre"] == "rock"
    assert row["dominant_genre_family"] == "Rock"
    assert row["n_genres"] == 2
    assert row["genre_tie"] == False


def test_dominant_genre_tie_broken_by_mean_popularity():
    # Artist B has 1 track in jazz (pop=70) and 1 in blues (pop=50) -> jazz wins on popularity
    tracks = pd.DataFrame([
        {"artist_key": "artist_b", "track_genre": "jazz", "popularity": 70, "is_primary_song": 1},
        {"artist_key": "artist_b", "track_genre": "blues", "popularity": 50, "is_primary_song": 1},
    ])
    profile = build_artist_genre_profile(tracks)
    row = profile.iloc[0]
    assert row["artist_key"] == "artist_b"
    assert row["dominant_genre"] == "jazz"
    assert row["n_genres"] == 2
    assert row["genre_tie"] == True  # track counts were tied


def test_dominant_genre_tie_broken_alphabetically():
    # Artist C has 1 track in 'techno' (pop=60) and 1 track in 'ambient' (pop=60) -> ambient wins alphabetically
    tracks = pd.DataFrame([
        {"artist_key": "artist_c", "track_genre": "techno", "popularity": 60, "is_primary_song": 1},
        {"artist_key": "artist_c", "track_genre": "ambient", "popularity": 60, "is_primary_song": 1},
    ])
    profile = build_artist_genre_profile(tracks)
    row = profile.iloc[0]
    assert row["artist_key"] == "artist_c"
    assert row["dominant_genre"] == "ambient"
    assert row["dominant_genre_family"] == "Classical & Instrumental"
    assert row["n_genres"] == 2
    assert row["genre_tie"] == True


def test_dominant_genre_ignores_non_primary_songs():
    # Non-primary songs (is_primary_song=0) should NOT affect dominant genre calculation
    tracks = pd.DataFrame([
        {"artist_key": "artist_d", "track_genre": "disco", "popularity": 90, "is_primary_song": 0},
        {"artist_key": "artist_d", "track_genre": "disco", "popularity": 90, "is_primary_song": 0},
        {"artist_key": "artist_d", "track_genre": "country", "popularity": 50, "is_primary_song": 1},
    ])
    profile = build_artist_genre_profile(tracks)
    row = profile.iloc[0]
    assert row["artist_key"] == "artist_d"
    assert row["dominant_genre"] == "country"
    assert row["n_genres"] == 1
    assert row["genre_tie"] == False
