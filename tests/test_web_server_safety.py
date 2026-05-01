import base64
import types

import pytest
from fastapi.testclient import TestClient


def test_pipeline_text_slur_skips_llm_and_sets_sad(monkeypatch: pytest.MonkeyPatch):
    import web_server as ws

    # Ensure server is "configured"
    ws._settings = types.SimpleNamespace(
        openai_api_key="x",
        azure_speech_key="x",
        azure_speech_region="x",
        azure_voice_name="voice",
        llm_system_prompt="sys",
        llm_model="m",
        llm_max_completion_tokens=8,
    )
    ws._lang_detect = None

    # Make the slur detector trigger deterministically without shipping real terms.
    monkeypatch.setattr(ws, "_slur_regex_by_lang", ws.compile_slur_regex_by_language({"en": ["bad"], "cs": []}))

    seen = {}

    class _FakeLlm:
        def generate(self, text: str):
            assert text == "you are bad"
            return types.SimpleNamespace(response="Please be kind.")

    def _fake_get_llm(llm_backend: str, system_prompt: str):
        seen["llm_backend"] = llm_backend
        seen["system_prompt"] = system_prompt
        return _FakeLlm()

    monkeypatch.setattr(ws, "_get_llm", _fake_get_llm)

    # Avoid personality disk reads.
    monkeypatch.setattr(ws, "load_personality", lambda _pid: types.SimpleNamespace(llm_system_prompt=""))

    # Avoid voice selection complexity.
    monkeypatch.setattr(ws, "_resolve_voice", lambda *_args, **_kwargs: "voice")

    monkeypatch.setattr(
        ws,
        "synthesize_mixed_language_ssml",
        lambda text, **_kw: (types.SimpleNamespace(audio_data=b"wav", visemes=[], duration_ms=123.0), "voice"),
    )

    client = TestClient(ws.app)
    res = client.post(
        "/api/pipeline/text",
        json={"text": "you are bad", "personality_id": "peter", "llm_backend": "openai", "session_id": "s"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["mood"] == "sad"
    assert data["safety_triggered"] is True
    assert data["safety_language"] == "en"
    assert data["response_text"] == "Please be kind."
    assert seen["llm_backend"] == "openai"
    assert "insulting or hateful language" in seen["system_prompt"]
    assert base64.b64decode(data["audio_base64"]) == b"wav"

