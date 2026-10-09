"""Unit tests for T12 artist matching cascade (src/artist_match.py).

Tests edge cases:
- Collaborative credits: "Eminem Featuring Rihanna" -> split
- Compound bands: "Earth, Wind & Fire" stays whole when key exists in index
- Workers recovery: "(Prince & The Revolution)" extracted from workers
- Marker filtering: "(A)" / "(S)" markers ignored in workers
- Nominee fallback: used when artist is null and category is a producer/artist category
- Accents: NFKD normalization matches accented names ("Beyoncé" -> "beyonce")
- Fuzzy matching: disabled by default; enabled only with enable_fuzzy=True
"""

from __future__ import annotations

import pytest

from src.artist_match import (
    AwardMatch,
    SpotifyArtistIndex,
    last_workers_parenthetical,
    match_award,
    match_credit,
    split_credit,
)


@pytest.fixture
def spotify_index() -> SpotifyArtistIndex:
    return SpotifyArtistIndex([
        "Eminem",
        "Rihanna",
        "Earth, Wind & Fire",
        "Wind",
        "Fire",
        "Prince",
        "The Revolution",
        "Prince & The Revolution",
        "Beyonce",
        "Finneas O'Connell",
        "Billie Eilish",
    ])


def test_earth_wind_and_fire_stays_whole_when_key_exists(spotify_index):
    # Step 1 exact takes precedence over split
    match = match_award(
        artist="Earth, Wind & Fire",
        workers=None,
        category="Best R&B Performance",
        nominee="Shining Star",
        index=spotify_index,
    )
    assert match.match_method == "exact"
    assert match.artist_key == "Earth, Wind & Fire"
    assert match.matched_keys == ["Earth, Wind & Fire"]
    assert match.credit_artist_count == 1
    assert match.artist_source == "credit"


def test_eminem_featuring_rihanna_splits_collaborators(spotify_index):
    # Step 2 split
    match = match_award(
        artist="Eminem Featuring Rihanna",
        workers=None,
        category="Best Rap/Sung Collaboration",
        nominee="Love the Way You Lie",
        index=spotify_index,
    )
    assert match.match_method == "split"
    assert match.artist_key == "Eminem"
    assert set(match.matched_keys) == {"Eminem", "Rihanna"}
    assert match.credit_artist_count == 2
    assert match.artist_source == "credit"


def test_workers_parenthetical_extraction_and_marker_ignored():
    # Last parenthetical ignoring trailing marker like (A) or (S)
    workers_with_marker = "Produced by Jimmy Jam, Terry Lewis (Prince & The Revolution) (A)"
    recovered = last_workers_parenthetical(workers_with_marker)
    assert recovered == "Prince & The Revolution"

    # Trailing single marker (A) alone returns None
    assert last_workers_parenthetical("(A)") is None


def test_workers_match_recovery(spotify_index):
    # Step 3 workers when artist is null
    match = match_award(
        artist=None,
        workers="Producer: Rick Rubin (Prince)",
        category="Album Of The Year",
        nominee="Purple Rain",
        index=spotify_index,
    )
    assert match.match_method == "workers"
    assert match.artist_key == "Prince"
    assert match.artist_source == "workers"


def test_nominee_fallback_for_producer_categories(spotify_index):
    # Step 4 nominee fallback when artist and workers are blank
    match = match_award(
        artist=None,
        workers=None,
        category="Producer Of The Year, Non-Classical",
        nominee="Finneas O'Connell",
        index=spotify_index,
    )
    assert match.match_method == "nominee"
    assert match.artist_key == "Finneas O'Connell"
    assert match.artist_source == "nominee"


def test_accents_normalized_for_matching(spotify_index):
    # Beyoncé with accent matches Beyonce in Spotify index
    match = match_award(
        artist="Beyoncé",
        workers=None,
        category="Best R&B Song",
        nominee="Cuff It",
        index=spotify_index,
    )
    assert match.match_method == "exact"
    assert match.artist_key == "Beyonce"


def test_fuzzy_off_by_default(spotify_index):
    # "Billie Eilishs" has ratio 96.3 > 95 against "Billie Eilish" and does not split
    # With enable_fuzzy=False, it does not match (method is none)
    match_default = match_award(
        artist="Billie Eilishs",
        workers=None,
        category="Best Pop Vocal Album",
        nominee="Happier Than Ever",
        index=spotify_index,
        enable_fuzzy=False,
    )
    assert match_default.match_method == "none"

    # With enable_fuzzy=True, rapidfuzz matches
    match_fuzzy = match_award(
        artist="Billie Eilishs",
        workers=None,
        category="Best Pop Vocal Album",
        nominee="Happier Than Ever",
        index=spotify_index,
        enable_fuzzy=True,
    )
    assert match_fuzzy.match_method == "fuzzy"
    assert match_fuzzy.artist_key == "Billie Eilish"
