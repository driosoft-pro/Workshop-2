"""Value-free mapping helpers (T13 category, T14 genre family, key normalizer).

Every function here is a *pure derivation*: it never repairs a source value, it
only derives a new column from it (Workshop-2 principle: no value repair).

    norm_key          shared normalizer used by BOTH sides of the artist match
                      (T12) and by song_key (T15).
    clean_category    T13 `category_clean`: parentheses removed, wording
                      normalised, the 8 "Producer Of The Year" variants merged
                      into the 2 canonical ones.
    category_family   T13 `category_family`: ordered regex cascade, first hit
                      wins, default "Other". The documented primary cascade is
                      tried first; CATEGORY_FAMILY_EXTENSION_RULES then covers
                      the legacy (pre-1990s) categories the primary cascade
                      cannot express, still first-hit-wins and only reached
                      when the primary cascade returned "Other".
    genre_family      T14 `genre_family`: fixed 114-genre dictionary.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

# ---------------------------------------------------------------------------
# T12 - shared key normalizer
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)


QUOTE_CHARS = "\"'`."


def normalize_artist_name(value) -> str | None:
    """T4 display-name normalizer (kept for backward compatibility).

    Fold accents, lowercase, collapse whitespace, strip surrounding
    quotes/periods and canonicalise ``(Various Artists)``. ``norm_key`` below is
    the stricter key used for *matching*; this one stays the stored display key.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    text = str(value).strip()
    if not text:
        return None
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = " ".join(folded.lower().split())
    folded = folded.strip(QUOTE_CHARS)
    if not folded:
        return None
    if "various artists" in folded:
        return "various artists"
    return folded


def norm_key(value) -> str | None:
    """NFKD (accent folding to ASCII for Latin scripts), lowercase,
    ``&`` -> ``and``, drop standalone ``the``, non alphanumeric -> space,
    collapse spaces. Non-Latin letters are kept (both sides use this same
    function, so the fold stays symmetric). Returns None for empty input."""
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    text = str(value).strip()
    if not text:
        return None
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.replace("&", " and ")
    folded = folded.lower()
    folded = _WORD_RE.sub(" ", folded)
    words = [word for word in folded.split() if word != "the"]
    key = " ".join(words)
    return key or None


# ---------------------------------------------------------------------------
# T13 - category cleaning
# ---------------------------------------------------------------------------
_PAREN_RE = re.compile(r"\s*\(.*?\)")
_NON_CLASSICAL_RE = re.compile(r"\bnon\s*[-\s]?\s*classical\b", re.IGNORECASE)
_PRODUCER_RE = re.compile(r"producer of the year", re.IGNORECASE)
_MULTI_SPACE_RE = re.compile(r"\s+")

PRODUCER_CLASSICAL = "Producer Of The Year, Classical"
PRODUCER_NON_CLASSICAL = "Producer Of The Year, Non-Classical"


def clean_category(value) -> str | None:
    """``category_clean``: drop parentheticals, normalise wording, merge the
    8 Producer Of The Year variants into 2. Source value is never written back.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    text = str(value)
    text = _PAREN_RE.sub(" ", text)
    text = _NON_CLASSICAL_RE.sub("Non-Classical", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip().strip(",;").strip()
    if _PRODUCER_RE.search(text):
        is_non_classical = bool(_NON_CLASSICAL_RE.search(text))
        is_classical = bool(re.search(r"\bclassical\b", text, re.IGNORECASE))
        return PRODUCER_CLASSICAL if (is_classical and not is_non_classical) else PRODUCER_NON_CLASSICAL
    return text or None


# Ordered cascade: first hit wins (case-insensitive). "General Field" sits
# before "Pop" so general-field names can never be captured by a pop-like
# pattern, but after Classical/Jazz/Country/... so "Country Album Of The Year"
# stays in its genre family.
CATEGORY_FAMILY_RULES: list[tuple[str, str]] = [
    ("Classical", r"classical|opera|orchestra|chamber|choral|conductor|composition"),
    ("Jazz", r"jazz"),
    ("Country & Folk", r"country|bluegrass|folk|americana"),
    ("Latin", r"latin|tejano|mexican|tropical|banda"),
    ("R&B & Rap", r"r&b|rap|urban|soul"),
    ("Rock & Metal", r"rock|metal|alternative|hard"),
    ("General Field", r"record of the year|album of the year|song of the year|new artist"),
    ("Pop", r"pop"),
    ("Gospel & Christian", r"gospel|christian"),
    ("Dance & Electronic", r"dance|electronic|remix"),
    ("Reggae & World", r"reggae|world|polka|zydeco|hawaiian|native"),
    ("Production & Technical", r"engineer|producer|package|notes|liner|art direction|surround|mastering"),
    ("Visual Media & Theater", r"musical|soundtrack|motion picture|television|visual media|film"),
    ("Spoken & Comedy", r"spoken|comedy|children"),
]
_CATEGORY_FAMILY_COMPILED = [
    (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in CATEGORY_FAMILY_RULES
]

# Extension pass (T13): the primary cascade above covers the modern Grammy
# vocabulary; these patterns cover the legacy categories that would otherwise
# fall through to "Other" (instrumental/arrangement craft awards, blues,
# rhythm & blues, roots, music video, historical reissues, ...). Reached only
# when the primary cascade returned "Other", so a row classified by a primary
# rule is never reclassified (first hit wins, no regressions).
CATEGORY_FAMILY_EXTENSION_RULES: list[tuple[str, str]] = [
    ("Classical", r"arrangement|instrumental|ensemble|soloist|new age|a cappella|accompaniment"),
    ("R&B & Rap", r"rhythm\s*&\s*blues"),
    ("Jazz", r"blues"),
    ("Country & Folk", r"american roots|regional roots|roots|ethnic|traditional"),
    ("Latin", r"salsa|merengue|norte"),
    ("Pop", r"vocal|contemporary|top 40|voices|chorus|dancing"),
    ("Gospel & Christian", r"sacred|inspirational"),
    ("Dance & Electronic", r"disco"),
    ("Production & Technical", r"historical|reissue|album cover|immersive"),
    ("Visual Media & Theater", r"music video|video|cast|broadway|show album|score|sound track"),
]
_CATEGORY_FAMILY_EXTENSION_COMPILED = [
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in CATEGORY_FAMILY_EXTENSION_RULES
]

CATEGORY_FAMILIES: list[str] = [name for name, _ in CATEGORY_FAMILY_RULES]


def category_family(value) -> str:
    if value is None:
        return "Other"
    text = str(value)
    for name, pattern in _CATEGORY_FAMILY_COMPILED:
        if pattern.search(text):
            return name
    for name, pattern in _CATEGORY_FAMILY_EXTENSION_COMPILED:
        if pattern.search(text):
            return name
    return "Other"


# ---------------------------------------------------------------------------
# T14 - genre family dictionary (all 114 Spotify genres)
# ---------------------------------------------------------------------------
_GENRE_GROUPS: dict[str, list[str]] = {
    "Rock": [
        "alt-rock", "alternative", "emo", "grunge", "guitar", "hard-rock", "indie",
        "j-rock", "psych-rock", "punk", "punk-rock", "rock", "rock-n-roll",
        "rockabilly", "goth", "industrial",
    ],
    "Metal": [
        "black-metal", "death-metal", "grindcore", "hardcore", "heavy-metal",
        "metal", "metalcore",
    ],
    "Pop": [
        "pop", "indie-pop", "power-pop", "synth-pop", "pop-film", "k-pop", "j-pop",
        "j-idol", "cantopop", "mandopop", "happy", "j-dance",
    ],
    "Hip-Hop & R&B": ["hip-hop", "r-n-b", "trip-hop"],
    "Electronic": [
        "breakbeat", "chicago-house", "club", "dance", "deep-house", "detroit-techno",
        "drum-and-bass", "dubstep", "edm", "electro", "electronic", "garage",
        "hardstyle", "house", "idm", "minimal-techno", "progressive-house", "techno",
        "trance",
    ],
    "Latin": [
        "latin", "latino", "reggaeton", "salsa", "tango", "spanish", "forro",
        "pagode", "samba", "sertanejo", "mpb", "brazil",
    ],
    "Jazz Blues Soul": ["jazz", "blues", "soul", "funk", "gospel", "groove", "disco"],
    "Country & Folk": [
        "country", "bluegrass", "folk", "honky-tonk", "singer-songwriter",
        "songwriter", "acoustic",
    ],
    "Classical & Instrumental": [
        "classical", "opera", "piano", "new-age", "ambient", "show-tunes",
    ],
    "Reggae & Caribbean": ["reggae", "dancehall", "dub", "ska"],
    "World": [
        "afrobeat", "british", "french", "german", "indian", "iranian", "malay",
        "swedish", "turkish", "world-music",
    ],
    "Mood & Media": [
        "children", "kids", "comedy", "disney", "anime", "sad", "romance",
        "sleep", "study", "chill", "party",
    ],
}

GENRE_FAMILY: dict[str, str] = {
    genre: family for family, genres in _GENRE_GROUPS.items() for genre in genres
}
GENRE_FAMILIES = sorted(_GENRE_GROUPS)


def genre_family(value) -> str:
    if value is None:
        return "Other"
    return GENRE_FAMILY.get(str(value), "Other")
