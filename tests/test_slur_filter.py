import re

from backend.safety.slur_filter import (
    compile_slur_regex,
    detect_slur,
    compile_slur_regex_by_language,
    detect_slur_by_language,
)


def test_compile_slur_regex_none_when_empty():
    assert compile_slur_regex([]) is None
    assert compile_slur_regex(["", "   "]) is None


def test_detect_slur_none_when_regex_none():
    assert detect_slur("anything", regex=None) is None


def test_detect_slur_matches_whole_words_only():
    rx = compile_slur_regex(["bad"])
    assert rx is not None

    assert detect_slur("bad", regex=rx) is not None
    assert detect_slur("you are bad", regex=rx) is not None
    assert detect_slur("bad!", regex=rx) is not None
    assert detect_slur("so...bad...", regex=rx) is not None

    # Should not match substrings inside larger words after normalization.
    assert detect_slur("badminton", regex=rx) is None
    assert detect_slur("notbad", regex=rx) is None


def test_detect_slur_tolerates_punctuation_and_spacing_tricks():
    rx = compile_slur_regex(["slurterm"])
    assert rx is not None

    assert detect_slur("slurterm", regex=rx) is not None
    assert detect_slur("slur-term", regex=rx) is not None
    assert detect_slur("slur_term", regex=rx) is not None
    assert detect_slur("slur   term", regex=rx) is not None


def test_compile_slur_regex_escapes_terms_as_literals():
    rx = compile_slur_regex(["a.b", "(x)"])
    assert rx is not None
    assert isinstance(rx, re.Pattern)

    assert detect_slur("a.b", regex=rx) is not None
    assert detect_slur("(x)", regex=rx) is not None


def test_default_list_style_terms_match_profanity_example():
    rx = compile_slur_regex(["fuck", "fucking"])
    assert rx is not None
    assert detect_slur("fuck", regex=rx) is not None
    assert detect_slur("fucking", regex=rx) is not None
    assert detect_slur("what the f-u-c-k", regex=rx) is not None


def test_detect_slur_by_language_returns_bucket():
    rx_by_lang = compile_slur_regex_by_language({"en": ["bad"], "cs": ["zle"]})
    assert detect_slur_by_language("you are bad", regex_by_lang=rx_by_lang) is not None
    assert detect_slur_by_language("you are bad", regex_by_lang=rx_by_lang).language == "en"
    assert detect_slur_by_language("to je zle", regex_by_lang=rx_by_lang).language == "cs"


def test_compile_slur_regex_supports_prefix_operator():
    rx = compile_slur_regex(["kokot*"])
    assert rx is not None
    assert detect_slur("kokot", regex=rx) is not None
    assert detect_slur("kokote", regex=rx) is not None
    assert detect_slur("kokotko", regex=rx) is not None

