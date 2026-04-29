from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Pattern, Literal


@dataclass(frozen=True, slots=True)
class SlurMatch:
    """Match metadata for a safety-triggered user input."""

    matched: str
    start: int
    end: int


SlurLanguage = Literal["en", "cs"]


@dataclass(frozen=True, slots=True)
class SlurMatchByLang(SlurMatch):
    language: SlurLanguage


def _normalize_for_matching(text: str) -> str:
    """Normalize user text to improve simple regex matching.

    Goals:
    - Make matches robust to case, punctuation, and common spacing tricks.
    - Avoid complex NLP; keep this deterministic and easily testable.
    """

    # NFKC folds many Unicode lookalikes to their compatibility forms.
    s = unicodedata.normalize("NFKC", text or "")
    s = s.lower()

    # Replace separators/punctuation with spaces and collapse runs.
    # This makes patterns like "b-a_d" match "bad" via relaxed regexes.
    s = re.sub(r"[\s\W_]+", " ", s, flags=re.UNICODE)
    return s.strip()


def compile_slur_regex(terms: list[str]) -> Pattern[str] | None:
    """Compile a regex matching any term in the provided list.

    Notes:
    - This is a deliberately *simple* detector. It is not a moderation system.
    - Callers should keep `terms` short and curated.
    - Returns None when no terms are provided.
    """

    cleaned: list[str] = []
    for t in terms:
        raw = (t or "").strip()
        if not raw:
            continue
        low = raw.lower()
        # Support a minimal "prefix" operator for inflected forms (e.g. "kokot*").
        # This still matches whole normalized words, but allows extra word characters after the prefix.
        if low.endswith("*") and len(low) > 1:
            cleaned.append(re.escape(low[:-1]) + r"\w*")
        else:
            # Interpret the input as a literal term (not an arbitrary regex).
            cleaned.append(re.escape(low))

    if not cleaned:
        return None

    # Match terms as whole words in the normalized string.
    # Example: term "bad" matches "bad" but not "badminton".
    pattern = r"(?:^|[\s])(" + "|".join(cleaned) + r")(?:$|[\s])"
    return re.compile(pattern, flags=re.IGNORECASE)


def detect_slur(text: str, *, regex: Pattern[str] | None) -> SlurMatch | None:
    """Return match metadata if `text` triggers the provided slur regex."""

    if regex is None:
        return None

    normalized = _normalize_for_matching(text)
    if not normalized:
        return None

    m = regex.search(f" {normalized} ")
    if not m:
        return None

    # Indices are in the normalized string with padded spaces; still useful for logs/tests.
    return SlurMatch(matched=m.group(1), start=m.start(1) - 1, end=m.end(1) - 1)


def default_slur_terms() -> list[str]:
    """Default curated term list.

    NOTE: This list exists to make the demo safer out of the box.
    You can override/extend it at runtime via `AVATAR_DEMO_SLUR_TERMS` (comma-separated).

    The detector is intentionally simple (literal terms + word-boundary-ish matching
    after normalization). It will have both false positives and false negatives.
    """

    # Kept as plain strings (not regex fragments) to keep matching simple and predictable.
    # Includes common English + Czech slurs.
    return [
        # English
        "nigger",
        "nigga",
        "faggot",
        "fag",
        "retard",
        "spic",
        "kike",
        "chink",
        "gook",
        "tranny",
        # Profanity (requested: e.g. "fuck")
        "fuck",
        "fucking",
        "fucked",
        "fucker",
        "shit",
        "shitty",
        "cunt",
        "bitch",
        "bastard",
        # Czech / Slovak (common variants)
        "cigan",
        "cigán",
        "cigani",
        "cigáni",
        "negr",
        "buzna",
        "buzerant",
        "teplouš",
        "cikán",
        "cikani",
        "cikáni",
    ]


def default_slur_terms_by_language() -> dict[SlurLanguage, list[str]]:
    """Return curated slur terms grouped by language.

    This enables choosing a localized safety response when a match occurs.
    """

    # Keep these lists short and curated (demo-grade, not a moderation system).
    # NOTE: We intentionally include common profanity because the demo UX treats it as "be kind".
    return {
        "en": [
            "nigger",
            "nigga",
            "faggot",
            "fag",
            "retard",
            "spic",
            "kike",
            "chink",
            "gook",
            "tranny",
            "fuck",
            "fucking",
            "fucked",
            "fucker",
            "shit",
            "shitty",
            "cunt",
            "bitch",
            "bastard",
        ],
        "cs": [
            "cigan",
            "cigán",
            "cigani",
            "cigáni",
            "negr",
            "buzna",
            "buzerant",
            "teplouš",
            "cikán",
            "cikani",
            "cikáni",
            # Inflections: kokot, kokote, kokotko, ...
            "kokot*",
            "pica",
            "pico",
            "pizda",
            "kurv*"
            "retard*"
        ],
    }


def compile_slur_regex_by_language(terms_by_lang: dict[SlurLanguage, list[str]]) -> dict[SlurLanguage, Pattern[str] | None]:
    """Compile one regex per language."""

    return {lang: compile_slur_regex(terms) for lang, terms in terms_by_lang.items()}


def detect_slur_by_language(
    text: str, *, regex_by_lang: dict[SlurLanguage, Pattern[str] | None]
) -> SlurMatchByLang | None:
    """Return the first match across language buckets (deterministic order)."""

    # Deterministic: check Czech first (more diacritics/false positives risk), then English.
    for lang in ("cs", "en"):
        rx = regex_by_lang.get(lang)
        m = detect_slur(text, regex=rx)
        if m is None:
            continue
        return SlurMatchByLang(matched=m.matched, start=m.start, end=m.end, language=lang)
    return None

