"""Unit tests for T13 and T14 category and genre mappings (src/mappings.py).

Tests:
- 114/114 Spotify genres mapped into genre families without unmapped defaults.
- All 8 raw 'Producer Of The Year' variants merged into exactly 2 standard forms:
  'Producer Of The Year, Non-Classical' and 'Producer Of The Year, Classical'.
- Category family resolution assigns >=90% of real Grammy categories to a valid family (Other <= 10%).
- Key normalizer (norm_key) collapses spaces, converts & to 'and', strips 'the'.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from src.mappings import (
    GENRE_FAMILY,
    category_family,
    clean_category,
    genre_family,
    norm_key,
)


def test_all_114_genres_mapped_to_valid_families():
    assert len(GENRE_FAMILY) == 114
    for genre, family in GENRE_FAMILY.items():
        assert family != "Other"
        assert genre_family(genre) == family

    # Unmapped genre returns 'Other'
    assert genre_family("non-existent-genre-xyz") == "Other"


def test_producer_variants_merged_into_two():
    raw_producer_variants = [
        "Producer Of The Year",
        "Producer Of The Year (Non-Classical)",
        "Producer of the Year, Non-Classical",
        "Producer of the Year (Classical)",
        "Producer Of The Year, Classical",
        "Best Producer of the Year",
        "Best Producer Of The Year, Non-Classical",
        "Producer Of The Year (Other Than Classical)",
    ]
    cleaned = {clean_category(variant) for variant in raw_producer_variants}
    expected = {
        "Producer Of The Year, Non-Classical",
        "Producer Of The Year, Classical",
    }
    assert cleaned == expected


def test_other_category_family_share_below_10_percent_on_real_categories():
    raw_path = Path("data/raw/the_grammy_awards.csv")
    if not raw_path.exists():
        pytest.skip("data/raw/the_grammy_awards.csv not available")

    df = pd.read_csv(raw_path, usecols=["category"])
    categories = df["category"].dropna().unique()
    assert len(categories) > 0

    families = [category_family(clean_category(cat)) for cat in categories]
    other_count = sum(1 for f in families if f == "Other")
    other_share = other_count / len(categories)

    # Required: Other <= 0.10 (observed is 0.00)
    assert other_share <= 0.10, f"Other share too high: {other_share:.4f}"


def test_key_normalizer_rules():
    assert norm_key("Earth, Wind & Fire") == "earth wind and fire"
    assert norm_key("The Beatles") == "beatles"
    assert norm_key("Beyoncé") == "beyonce"
    assert norm_key("  Rock &  Roll  ") == "rock and roll"
