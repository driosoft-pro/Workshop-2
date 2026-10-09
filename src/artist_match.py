"""T12 - Grammy credit -> Spotify artist matching cascade.

The two sources share no identifier (no ISRC, no artist id), so the match is
name-based *by necessity*. The cascade below is the documented order; it stops
at the first hit and records which step produced the result:

    1. exact    full normalized credit is a Spotify artist key
                (FULL string first so "Earth, Wind & Fire", "Simon & Garfunkel"
                 and "Hall & Oates" are never split)
    2. split    only if (1) failed: split the credit on & , / and feat. ...
                and match every part independently
    3. workers  only when ``artist`` is null: last parenthetical of ``workers``
    4. nominee  still null and a person-category -> the nominee is the artist
    5. fuzzy    opt-in (DAG param enable_fuzzy), rapidfuzz >= 95
    6. none     no match; the normalized credit is kept for measurement

No source value is ever altered: every step only *derives* keys and flags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from src.mappings import AGGREGATE_CREDITS, is_aggregate_credit, norm_key, normalize_artist_name

SPLIT_RE = re.compile(
    r"\s*(?:&|,|/|\band\b|\bfeaturing\b|\bfeat\.?|\bwith\b| x )\s*", re.IGNORECASE
)
TRAILING_PAREN_RE = re.compile(r"\s*\(.*\)\s*$")
WORKERS_PAREN_RE = re.compile(r"\(([^()]+)\)\s*(?:\(\w\))?\s*$")
_SINGLE_TOKEN_RE = re.compile(r"^[a-z]$")

ROLE_WORDS = (
    "songwriters", "songwriter", "composers", "composer", "producers", "producer",
    "arrangers", "arranger", "engineers", "engineer", "conductors", "conductor",
    "musicians", "musician", "performers", "performer", "vocalists", "vocalist",
    "artists", "artist", "writers", "writer", "lyricists", "lyricist",
    "remixers", "remixer", "mixers", "mixer",
)
_ROLE_SUFFIX_RE = re.compile(r"\s*,?\s*(?:" + "|".join(ROLE_WORDS) + r")\s*$", re.IGNORECASE)

GENERIC_CREDITS = {
    "various artists", "original cast", "orchestra", "ensemble", "unknown",
    "none", "n a", "na", "tbd",
}
GENERIC_WORKERS_MARKERS = GENERIC_CREDITS | {
    "a", "b", "c", "d", "e", "p", "s", "m", "r", "l", "v", "i",
}

NOMINEE_CATEGORY_RE = re.compile(
    r"artist|producer|songwriter|composer|arranger|engineer|conductor", re.IGNORECASE
)
SONG_TYPE_CATEGORY_RE = re.compile(
    r"\bsong\b|\bsingle\b|\btrack\b|^record of the year$", re.IGNORECASE
)


def is_blank(value) -> bool:
    """True for None / NaN / empty-or-whitespace strings (NaN is not 'nan')."""
    if value is None:
        return True
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return True
        except (TypeError, ValueError):
            pass
    return str(value).strip() == ""


def strip_role_suffix(part: str) -> str:
    """Remove trailing role words (`, songwriters`) and a trailing ``(...)``."""
    text = str(part).strip()
    previous = None
    while text and text != previous:
        previous = text
        text = _ROLE_SUFFIX_RE.sub("", text).strip()
        text = TRAILING_PAREN_RE.sub("", text).strip()
    return text.strip(" ,;.")


def split_credit(credit) -> list[str]:
    """Split a collaborative credit into candidate artist names (T12 step 2)."""
    if is_blank(credit):
        return []
    text = str(credit).strip()
    if not text:
        return []
    parts = [strip_role_suffix(part) for part in SPLIT_RE.split(text)]
    return [part for part in parts if part]


def last_workers_parenthetical(workers):
    """Last parenthetical of ``workers`` ignoring trailing markers like ``(A)``."""
    if is_blank(workers):
        return None
    match = WORKERS_PAREN_RE.search(str(workers).strip())
    if not match:
        return None
    candidate = strip_role_suffix(match.group(1).strip())
    if not candidate:
        return None
    lowered = norm_key(candidate) or ""
    if (
        _SINGLE_TOKEN_RE.match(lowered)
        or lowered in GENERIC_WORKERS_MARKERS
        or lowered in AGGREGATE_CREDITS
    ):
        return None
    return candidate


class SpotifyArtistIndex:
    """Normalized Spotify artist keys -> source artist_key (+ fuzzy support)."""

    def __init__(self, spotify_keys):
        self.keys: dict[str, str] = {}
        self.norm_to_key: dict[str, str] = {}
        for key in sorted(set(spotify_keys)):
            if not key:
                continue
            normalized = norm_key(key)
            if normalized is None or normalized in AGGREGATE_CREDITS:
                continue
            self.keys[key] = key
            self.norm_to_key.setdefault(normalized, key)

    def lookup(self, candidate) -> str | None:
        normalized = norm_key(candidate)
        if normalized is None or normalized in AGGREGATE_CREDITS:
            return None
        return self.norm_to_key.get(normalized)

    def fuzzy_lookup(self, candidate, threshold: float = 95.0):
        """Optional (T12 step 5) fuzzy match; rapidfuzz is imported lazily."""
        norm_cand = norm_key(candidate)
        if norm_cand is None or norm_cand in AGGREGATE_CREDITS or not self.norm_to_key:
            return None
        try:
            from rapidfuzz import fuzz
        except ImportError:  # pragma: no cover - dependency is optional
            return None
        best_key, best_score = None, threshold
        for norm, key in self.norm_to_key.items():
            score = fuzz.token_sort_ratio(norm_cand, norm)
            if score >= best_score:
                best_key, best_score = key, score
        return best_key


@dataclass
class AwardMatch:
    """Result of the T12 cascade for a single Grammy award row."""

    artist_key: str | None = None
    matched_keys: list[str] = field(default_factory=list)
    match_method: str = "none"
    artist_source: str = "none"
    credit_artist_count: int = 0
    fuzzy_score: float | None = None
    is_aggregate_credit: int = 0

    @property
    def is_matched(self) -> bool:
        return bool(self.matched_keys)

    @property
    def is_strict(self) -> bool:
        return self.match_method == "exact"


def _match_parts(parts: list[str], index: SpotifyArtistIndex) -> list[str]:
    matched: list[str] = []
    for part in parts:
        if norm_key(part) in AGGREGATE_CREDITS:
            continue
        key = index.lookup(part)
        if key and key not in matched:
            matched.append(key)
    return matched


def match_credit(credit, index: SpotifyArtistIndex) -> tuple[str | None, list[str], str, int]:
    """Steps 1 and 2 for an explicit credit.

    Returns (candidate_key, matched_keys, match_method, credit_artist_count).
    """
    if is_blank(credit):
        return None, [], "none", 0
    exact = index.lookup(credit)
    if exact:
        return exact, [exact], "exact", 1
    parts = split_credit(credit)
    matched = _match_parts(parts, index)
    if matched:
        return matched[0], matched, "split", len(parts)
    return normalize_artist_name(credit) or None, [], "none", len(parts)


def match_award(
    *,
    artist,
    workers,
    category,
    nominee,
    index: SpotifyArtistIndex,
    enable_fuzzy: bool = False,
) -> AwardMatch:
    """Run the documented T12 cascade for one award row (first hit wins)."""
    candidate: str | None = None
    source = "none"
    count = 0
    artist_present = not is_blank(artist)

    # F1a: Aggregate-credit blocklist - such credits never match, never enter the bridge
    is_agg = 0
    if artist_present and norm_key(artist) in AGGREGATE_CREDITS:
        is_agg = 1
    elif not artist_present:
        p_raw = None
        if not is_blank(workers):
            m = WORKERS_PAREN_RE.search(str(workers).strip())
            if m:
                p_raw = strip_role_suffix(m.group(1).strip())
        if p_raw and norm_key(p_raw) in AGGREGATE_CREDITS:
            is_agg = 1
        elif not is_blank(nominee) and norm_key(nominee) in AGGREGATE_CREDITS:
            is_agg = 1

    if is_agg:
        source = "credit" if artist_present else ("workers" if not is_blank(workers) else "nominee")
        return AwardMatch(
            artist_key=None,
            matched_keys=[],
            match_method="none",
            artist_source=source,
            credit_artist_count=0,
            is_aggregate_credit=1,
        )

    if artist_present:
        candidate, matched, method, count = match_credit(artist, index)
        if matched:
            return AwardMatch(
                artist_key=matched[0],
                matched_keys=matched,
                match_method=method,
                artist_source="credit",
                credit_artist_count=count,
            )
        source = "credit"

    if not artist_present:
        parenthetical = last_workers_parenthetical(workers)
        if parenthetical:
            worker_key, matched, _method, count = match_credit(parenthetical, index)
            if matched:
                return AwardMatch(
                    artist_key=matched[0],
                    matched_keys=matched,
                    match_method="workers",
                    artist_source="workers",
                    credit_artist_count=len(matched) or 1,
                )
            candidate, source, count = worker_key, "workers", count or 1

    if candidate is None and category is not None and NOMINEE_CATEGORY_RE.search(str(category)):
        if not is_blank(nominee):
            nominee_key, matched, _method, _count = match_credit(nominee, index)
            if matched:
                return AwardMatch(
                    artist_key=matched[0],
                    matched_keys=matched,
                    match_method="nominee",
                    artist_source="nominee",
                    credit_artist_count=1,
                )
            candidate, source, count = nominee_key, "nominee", 1

    if candidate is None:
        return AwardMatch(match_method="none", artist_source=source, credit_artist_count=0)

    if enable_fuzzy:
        fuzzy_key = index.fuzzy_lookup(candidate)
        if fuzzy_key:
            return AwardMatch(
                artist_key=fuzzy_key,
                matched_keys=[fuzzy_key],
                match_method="fuzzy",
                artist_source=source,
                credit_artist_count=count or 1,
            )

    return AwardMatch(
        artist_key=candidate,
        matched_keys=[],
        match_method="none",
        artist_source=source,
        credit_artist_count=count,
    )
