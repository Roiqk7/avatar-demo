import web_server as ws


def _reset_session(sid: str = "s") -> None:
    ws._session_detected_lang.pop(sid, None)
    ws._session_lang_state.pop(sid, None)
    ws._session_voice_maps.pop(sid, None)
    ws._session_voice_map_timestamps.pop(sid, None)


def _turn(sid: str, signals: list[tuple[str, float]]) -> None:
    """Simulate one audio request turn with one or more detection signals."""
    ws._advance_session_language_turn(sid)
    for lang, score in signals:
        ws._apply_session_language_signal(sid, lang, score)
    ws._finalize_session_language_turn(sid)


def test_turn1_czech_pins_immediately_and_is_sticky() -> None:
    sid = "s"
    _reset_session(sid)

    # Turn 1: Czech detected -> immediate pin.
    _turn(sid, [("cs", 0.6)])
    assert ws._session_detected_lang[sid] == "cs"

    # Turn 2: single English signal should NOT override sticky Czech.
    _turn(sid, [("en", 0.99)])
    assert ws._session_detected_lang[sid] == "cs"


def test_non_czech_requires_two_in_a_row_to_pin() -> None:
    sid = "s"
    _reset_session(sid)

    _turn(sid, [("en", 0.9)])
    assert sid not in ws._session_detected_lang  # not pinned yet

    _turn(sid, [("en", 0.9)])
    assert ws._session_detected_lang[sid] == "en"


def test_slavic_low_confidence_maps_to_czech() -> None:
    sid = "s"
    _reset_session(sid)

    # Slovak under _CONF_SLAVIC (0.85) should be treated as Czech.
    _turn(sid, [("sk", 0.84)])
    assert ws._session_detected_lang[sid] == "cs"


def test_forced_pin_by_turn4_defaults_to_best_holy_trio() -> None:
    sid = "s"
    _reset_session(sid)

    # Provide no holy-trio candidate for 3 turns by using a high-confidence other language.
    # _resolve_session_language returns None when score >= _CONF_HIGH (0.90).
    _turn(sid, [("de", 0.95)])
    _turn(sid, [("de", 0.95)])
    _turn(sid, [("de", 0.95)])
    assert sid not in ws._session_detected_lang

    # By turn 4, we force a holy-trio pin; with no evidence, Czech wins by default.
    _turn(sid, [("de", 0.95)])
    assert ws._session_detected_lang[sid] == "cs"

