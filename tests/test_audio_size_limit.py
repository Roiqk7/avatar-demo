"""Tests: audio upload size limit (10 MB) on pipeline endpoints."""
import io
import types

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def configured_client(monkeypatch: pytest.MonkeyPatch):
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
    monkeypatch.setattr(ws, "synthesize_mixed_language_ssml", lambda *_a, **_kw: (
        types.SimpleNamespace(audio_data=b"wav", visemes=[], duration_ms=100.0),
        "voice",
    ))

    return TestClient(ws.app, raise_server_exceptions=False)


def _wav_bytes(size: int) -> bytes:
    """Return a fake audio payload of given size."""
    return b"\x00" * size


def test_audio_pipeline_accepts_small_file(configured_client: TestClient):
    small = _wav_bytes(1024)  # 1 KB
    res = configured_client.post(
        "/api/pipeline/audio",
        files={"audio_file": ("clip.wav", io.BytesIO(small), "audio/wav")},
        data={"personality_id": "peter", "llm_backend": "echo", "session_id": "s"},
    )
    assert res.status_code == 200


def test_audio_pipeline_rejects_oversized_file(configured_client: TestClient):
    big = _wav_bytes(11 * 1024 * 1024)  # 11 MB
    res = configured_client.post(
        "/api/pipeline/audio",
        files={"audio_file": ("clip.wav", io.BytesIO(big), "audio/wav")},
        data={"personality_id": "peter", "llm_backend": "echo", "session_id": "s"},
    )
    assert res.status_code == 413


def test_audio_stream_rejects_oversized_file(configured_client: TestClient):
    big = _wav_bytes(11 * 1024 * 1024)  # 11 MB
    res = configured_client.post(
        "/api/pipeline/audio_stream",
        files={"audio_file": ("clip.wav", io.BytesIO(big), "audio/wav")},
        data={"personality_id": "peter", "llm_backend": "echo", "session_id": "s"},
    )
    # Streaming endpoint yields an error event instead of HTTP 413
    assert b"error" in res.content
