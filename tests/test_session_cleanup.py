"""Tests: session voice map TTL eviction."""
import time
import types

import pytest


@pytest.fixture(autouse=True)
def reset_session_state():
    import web_server as ws

    ws._session_voice_maps.clear()
    ws._session_voice_map_timestamps.clear()
    yield
    ws._session_voice_maps.clear()
    ws._session_voice_map_timestamps.clear()


def test_cleanup_removes_stale_sessions():
    import web_server as ws

    old_sid = "old-session"
    new_sid = "new-session"
    now = time.time()

    ws._session_voice_maps[old_sid] = {"en": "voice-en"}
    ws._session_voice_map_timestamps[old_sid] = now - ws._SESSION_TTL_S - 10  # expired

    ws._session_voice_maps[new_sid] = {"cs": "voice-cs"}
    ws._session_voice_map_timestamps[new_sid] = now - 60  # fresh

    ws._cleanup_stale_sessions()

    assert old_sid not in ws._session_voice_maps
    assert old_sid not in ws._session_voice_map_timestamps
    assert new_sid in ws._session_voice_maps
    assert new_sid in ws._session_voice_map_timestamps


def test_cleanup_preserves_active_sessions():
    import web_server as ws

    sid = "active-session"
    ws._session_voice_maps[sid] = {"en": "voice-en"}
    ws._session_voice_map_timestamps[sid] = time.time()

    ws._cleanup_stale_sessions()

    assert sid in ws._session_voice_maps


def test_resolve_voice_updates_timestamp(monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    ws._settings = types.SimpleNamespace(
        azure_speech_key="x",
        azure_speech_region="x",
        azure_voice_name="fallback-voice",
    )

    monkeypatch.setattr(
        ws,
        "choose_voice",
        lambda **_kwargs: types.SimpleNamespace(voice_name="chosen-voice"),
    )
    ws._voice_catalog = None

    before = time.time()
    ws._resolve_voice("session-abc", None, "fallback-voice")
    after = time.time()

    ts = ws._session_voice_map_timestamps.get("session-abc")
    assert ts is not None
    assert before <= ts <= after


def test_resolve_voice_evicts_expired_before_resolving(monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    ws._settings = types.SimpleNamespace(
        azure_speech_key="x",
        azure_speech_region="x",
        azure_voice_name="fallback",
    )
    monkeypatch.setattr(
        ws,
        "choose_voice",
        lambda **_kwargs: types.SimpleNamespace(voice_name="chosen"),
    )
    ws._voice_catalog = None

    stale_sid = "stale"
    ws._session_voice_maps[stale_sid] = {"en": "old"}
    ws._session_voice_map_timestamps[stale_sid] = time.time() - ws._SESSION_TTL_S - 1

    ws._resolve_voice("new-session", None, "fallback")

    # Stale session should have been cleaned up during the call
    assert stale_sid not in ws._session_voice_maps
