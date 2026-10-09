"""Tests for aggregate credit blocklist (F1a).

Verifies that aggregate terms (Various Artists, Original Cast, etc.)
are blocked across all match methods and never enter the bridge.
"""

import pandas as pd
import pytest

from src.artist_match import SpotifyArtistIndex, match_award
from src.mappings import AGGREGATE_CREDITS, is_aggregate_credit


def test_aggregate_credits_set_contains_required_keys():
    expected = {
        "various artists", "original cast", "original broadway cast",
        "soundtrack", "various", "cast", "unknown", "traditional", "anonymous"
    }
    assert expected.issubset(AGGREGATE_CREDITS)


def test_is_aggregate_credit_detects_keywords():
    assert is_aggregate_credit("Various Artists")
    assert is_aggregate_credit("Original Broadway Cast")
    assert is_aggregate_credit("Traditional")
    assert not is_aggregate_credit("Stevie Wonder")
    assert not is_aggregate_credit("Beyonce")


def test_various_artists_never_matches_via_any_method():
    # Build artist index containing Various Artists and real artists
    artist_df = pd.DataFrame([
        {"artist_key": "various artists", "artist_display_name": "Various Artists"},
        {"artist_key": "stevie wonder", "artist_display_name": "Stevie Wonder"},
    ])
    index = SpotifyArtistIndex(artist_df)

    # 1. Exact credit Various Artists
    res1 = match_award(
        artist="Various Artists",
        workers="",
        category="Pop",
        nominee="Song",
        index=index,
    )
    assert res1.match_method == "none"
    assert res1.matched_keys == []
    assert res1.is_aggregate_credit == 1

    # 2. In workers parenthetical
    res2 = match_award(
        artist="",
        workers="produced by (Various Artists)",
        category="Pop",
        nominee="Song",
        index=index,
    )
    assert res2.match_method == "none"
    assert res2.matched_keys == []
    assert res2.is_aggregate_credit == 1

    # 3. In split credit
    res3 = match_award(
        artist="Various Artists & Friends",
        workers="",
        category="Pop",
        nominee="Song",
        index=index,
    )
    assert "various artists" not in res3.matched_keys

    # 4. In nominee
    res4 = match_award(
        artist="",
        workers="",
        category="Pop",
        nominee="Various Artists",
        index=index,
    )
    assert res4.match_method == "none"
    assert res4.matched_keys == []

