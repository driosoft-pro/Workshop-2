"""Tests for R1 statistical tests (F3).

Verifies Mann-Whitney U, Cliff's delta, and bootstrap 95% CI on synthetic data.
"""

import numpy as np
import pandas as pd
import pytest

from src.analytics import r1_stats


def test_r1_stats_known_synthetic():
    # Synthetic group where Grammy artists have significantly higher popularity
    rng = np.random.default_rng(42)
    n1, n2 = 50, 50
    grammy_pop = rng.normal(loc=75.0, scale=5.0, size=n1)
    non_pop = rng.normal(loc=50.0, scale=5.0, size=n2)

    df = pd.DataFrame({
        "recognition": ["core"] * (n1 + n2),
        "basis": ["all"] * (n1 + n2),
        "artist_sk": list(range(n1 + n2)),
        "is_grammy_artist": [1] * n1 + [0] * n2,
        "mean_popularity": np.concatenate([grammy_pop, non_pop]),
    })

    stats = r1_stats(df)
    assert len(stats) == 1
    row = stats.iloc[0]

    # Delta sign: should be strongly positive
    assert row["cliffs_delta"] > 0.8
    # p-value: should be very small
    assert row["p_value"] < 1e-4
    # Median difference should be around 25
    true_diff = np.median(grammy_pop) - np.median(non_pop)
    assert row["ci_lower"] <= true_diff <= row["ci_upper"]
    assert row["ci_lower"] > 15.0
