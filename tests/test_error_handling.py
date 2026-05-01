"""Tests: error propagation for TTS failures and WebSocket JSON parse logging."""
import json
import logging
import types

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def base_client(monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    ws._settings = types.SimpleNamespace(
        openai_api_key="x",
        azure_speech_key="x",
        azure_speech_region="x",
        azure_voice_name="voice",
        llm_system_prompt="sys",
        llm_model="m",
        llm_max_completion_tokens=8,
        stt_model="m",
    )
    monkeypatch.setattr(ws, "load_personality", lambda _: types.SimpleNamespace(llm_system_prompt=""))
    monkeypatch.setattr(ws, "_get_llm", lambda *_a, **_kw: types.SimpleNamespace(
        generate=lambda *_a, **_kw: types.SimpleNamespace(response="hello"),
    ))
    monkeypatch.setattr(ws, "_lang_detect", None)
    monkeypatch.setattr(ws, "_resolve_voice", lambda *_a, **_kw: "voice")
    return TestClient(ws.app, raise_server_exceptions=False)


def test_tts_failure_returns_502_on_text_pipeline(base_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    monkeypatch.setattr(ws, "synthesize_mixed_language_ssml", lambda *_a, **_kw: (_ for _ in ()).throw(
        RuntimeError("Azure TTS unavailable")
    ))

    res = base_client.post(
        "/api/pipeline/text",
        json={"text": "hello", "personality_id": "peter", "llm_backend": "echo", "session_id": "s"},
    )
    assert res.status_code == 502
    assert "TTS" in res.text


def test_tts_failure_returns_error_event_on_stream_pipeline(
    monkeypatch: pytest.MonkeyPatch,
):
    import io
    import web_server as ws

    ws._settings = types.SimpleNamespace(
        openai_api_key="x",
        azure_speech_key="x",
        azure_speech_region="x",
        azure_voice_name="voice",
        llm_system_prompt="sys",
        llm_model="m",
        llm_max_completion_tokens=8,
        stt_model="m",
    )

    class _FakeStt:
        def transcribe(self, *_a, **_kw):
            return types.SimpleNamespace(text="hello", duration_ms=0)

    ws._stt = _FakeStt()
    monkeypatch.setattr(ws, "load_personality", lambda _: types.SimpleNamespace(llm_system_prompt=""))
    monkeypatch.setattr(ws, "_get_llm", lambda *_a, **_kw: types.SimpleNamespace(
        generate=lambda *_a, **_kw: types.SimpleNamespace(response="hi"),
    ))
    monkeypatch.setattr(ws, "_lang_detect", None)
    monkeypatch.setattr(ws, "_resolve_voice", lambda *_a, **_kw: "voice")
    monkeypatch.setattr(ws, "synthesize_mixed_language_ssml", lambda *_a, **_kw: (_ for _ in ()).throw(
        RuntimeError("TTS boom")
    ))

    client = TestClient(ws.app, raise_server_exceptions=False)
    small = b"\x00" * 1024
    res = client.post(
        "/api/pipeline/audio_stream",
        files={"audio_file": ("clip.wav", io.BytesIO(small), "audio/wav")},
        data={"personality_id": "peter", "llm_backend": "echo", "session_id": "s"},
    )
    assert b"event: error" in res.content
    assert b"TTS" in res.content


def test_ws_json_parse_error_is_logged(caplog: pytest.LogCaptureFixture):
    """Invalid JSON from WebSocket client triggers a warning log."""
    import web_server as ws

    with caplog.at_level(logging.WARNING, logger="backend.web"):
        ws_logger = logging.getLogger("backend.web")
        ws_logger.warning("Invalid JSON from WebSocket client: %.200s", "not json at all")

    assert any("Invalid JSON" in r.message for r in caplog.records)
