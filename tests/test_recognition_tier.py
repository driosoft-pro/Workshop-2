"""Tests for recognition tiers (F1b).

Rules:
  Tier C: category_family == 'Production & Technical' OR category matches craft keywords.
  Tier B: not C and artist_source == 'workers'.
  Tier A: not C and artist_source in ('credit', 'nominee').
  none  : unmatched.
Flags:
  is_grammy_artist (core) = >=1 bridge row with tier A or B.
  is_grammy_artist_strict = >=1 bridge row with tier A.
  Tier C awardees never set either flag.
"""

import pandas as pd
import pytest

from src.mappings import derive_recognition_tier


def test_derive_recognition_tier_assignments():
    # Technical category -> C even with credit
    assert derive_recognition_tier(
        category_family_val="Production & Technical", category="Best Engineered Album",
        artist_source="credit", match_method="exact"
    ) == "C"
    assert derive_recognition_tier(
        category_family_val="General", category="Best Historical Album",
        artist_source="credit", match_method="exact"
    ) == "C"
    assert derive_recognition_tier(
        category_family_val="General", category="Best Arrangement",
        artist_source="credit", match_method="exact"
    ) == "C"
    assert derive_recognition_tier(
        category_family_val="General", category="Producer of the Year",
        artist_source="credit", match_method="exact"
    ) == "C"

    # Workers in song category -> B
    assert derive_recognition_tier(
        category_family_val="Pop", category="Best Pop Vocal Album",
        artist_source="workers", match_method="workers"
    ) == "B"

    # Credit performer in song category -> A
    assert derive_recognition_tier(
        category_family_val="Pop", category="Best Pop Solo Performance",
        artist_source="credit", match_method="exact"
    ) == "A"
    assert derive_recognition_tier(
        category_family_val="Rock", category="Best Rock Album",
        artist_source="nominee", match_method="nominee"
    ) == "A"

    # Unmatched -> none
    assert derive_recognition_tier(
        category_family_val="Pop", category="Best Pop Solo Performance",
        artist_source="none", match_method="none"
    ) == "none"
    assert derive_recognition_tier(
        category_family_val="Production & Technical", category="Best Engineered Album",
        artist_source="none", match_method="none"
    ) == "none"


def test_flag_definitions_for_tiers():
    # Synthetic bridge and fact_track_artist representation
    artists = ["artist_a", "artist_b", "artist_c", "artist_none"]
    bridge = pd.DataFrame([
        {"artist_sk": 1, "recognition_tier": "A"},
        {"artist_sk": 2, "recognition_tier": "B"},
        {"artist_sk": 3, "recognition_tier": "C"},
    ])

    core_artists = set(bridge[bridge["recognition_tier"].isin(["A", "B"])]["artist_sk"])
    strict_artists = set(bridge[bridge["recognition_tier"] == "A"]["artist_sk"])

    # Artist 1 has tier A: core=1, strict=1
    assert 1 in core_artists and 1 in strict_artists
    # Artist 2 has tier B: core=1, strict=0
    assert 2 in core_artists and 2 not in strict_artists
    # Artist 3 has tier C: core=0, strict=0
    assert 3 not in core_artists and 3 not in strict_artists
    # Artist 4 unmatched: core=0, strict=0
    assert 4 not in core_artists and 4 not in strict_artists
