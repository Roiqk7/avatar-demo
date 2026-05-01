import io
import types

import pytest
from fastapi.testclient import TestClient


def _configure_ws(ws):
    ws._settings = types.SimpleNamespace(
        openai_api_key="x",
        azure_speech_key="x",
        azure_speech_region="x",
        azure_voice_name="voice",
        llm_system_prompt="sys",
        llm_model="m-openai",
        llm_max_completion_tokens=8,
        stt_model="m-stt",
    )
    ws._lang_detect = None


def test_history_slicing_echo_openai_max(monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    _configure_ws(ws)

    monkeypatch.setattr(ws, "load_personality", lambda _pid: types.SimpleNamespace(llm_system_prompt=""))
    monkeypatch.setattr(ws, "_resolve_voice", lambda *_a, **_kw: "voice")
    monkeypatch.setattr(
        ws,
        "synthesize_mixed_language_ssml",
        lambda *_a, **_kw: (types.SimpleNamespace(audio_data=b"wav", visemes=[], duration_ms=1.0), "voice"),
    )

    seen: dict[str, list] = {}

    class _FakeLlm:
        def __init__(self, key: str):
            self._key = key

        def generate(self, _text: str, *, history=None):
            seen[self._key] = list(history or [])
            return types.SimpleNamespace(response="ok", prompt_tokens=0, completion_tokens=0)

    def _fake_get_llm(llm_backend: str, system_prompt: str):
        return _FakeLlm(llm_backend)

    monkeypatch.setattr(ws, "_get_llm", _fake_get_llm)

    history = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
    ]

    client = TestClient(ws.app)

    res = client.post(
        "/api/pipeline/text",
        json={"text": "hello", "personality_id": "peter", "llm_backend": "echo", "session_id": "s", "history": history},
    )
    assert res.status_code == 200, res.text
    assert seen.get("echo") == []

    res = client.post(
        "/api/pipeline/text",
        json={"text": "hello", "personality_id": "peter", "llm_backend": "openai", "session_id": "s", "history": history},
    )
    assert res.status_code == 200, res.text
    assert seen.get("openai") == history[-3:]

    res = client.post(
        "/api/pipeline/text",
        json={"text": "hello", "personality_id": "peter", "llm_backend": "max", "session_id": "s", "history": history},
    )
    assert res.status_code == 200, res.text
    assert seen.get("max") == history


def test_max_audio_stream_emits_delta_before_done(monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    _configure_ws(ws)

    class _FakeStt:
        def transcribe(self, *_a, **_kw):
            return types.SimpleNamespace(text="hello", duration_ms=0.0)

    ws._stt = _FakeStt()
    monkeypatch.setattr(ws, "load_personality", lambda _pid: types.SimpleNamespace(llm_system_prompt=""))
    monkeypatch.setattr(ws, "_resolve_voice", lambda *_a, **_kw: "voice")
    monkeypatch.setattr(
        ws,
        "synthesize_mixed_language_ssml",
        lambda *_a, **_kw: (types.SimpleNamespace(audio_data=b"wav", visemes=[], duration_ms=1.0), "voice"),
    )

    class _FakeLlm:
        def generate_stream(self, _text: str, *, history=None):
            yield "hi"
            yield " there"

    monkeypatch.setattr(ws, "_get_llm", lambda *_a, **_kw: _FakeLlm())

    client = TestClient(ws.app, raise_server_exceptions=False)
    small = b"\x00" * 1024
    res = client.post(
        "/api/pipeline/audio_stream",
        files={"audio_file": ("clip.wav", io.BytesIO(small), "audio/wav")},
        data={"personality_id": "peter", "llm_backend": "max", "session_id": "s", "history": "[]"},
    )
    assert res.status_code == 200, res.text
    body = res.content
    assert b"event: delta" in body
    assert b"event: done" in body
    assert body.index(b"event: delta") < body.index(b"event: done")


def test_max_text_stream_emits_delta_before_done(monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    _configure_ws(ws)

    monkeypatch.setattr(ws, "load_personality", lambda _pid: types.SimpleNamespace(llm_system_prompt=""))
    monkeypatch.setattr(ws, "_resolve_voice", lambda *_a, **_kw: "voice")
    monkeypatch.setattr(
        ws,
        "synthesize_mixed_language_ssml",
        lambda *_a, **_kw: (types.SimpleNamespace(audio_data=b"wav", visemes=[], duration_ms=1.0), "voice"),
    )

    class _FakeLlm:
        def generate_stream(self, _text: str, *, history=None):
            yield "hi"
            yield " there"

    monkeypatch.setattr(ws, "_get_llm", lambda *_a, **_kw: _FakeLlm())

    client = TestClient(ws.app, raise_server_exceptions=False)
    res = client.post(
        "/api/pipeline/text_stream",
        json={"text": "hello", "personality_id": "peter", "llm_backend": "max", "session_id": "s", "history": []},
    )
    assert res.status_code == 200, res.text
    body = res.content
    assert b"event: delta" in body
    assert b"event: done" in body
    assert body.index(b"event: delta") < body.index(b"event: done")

