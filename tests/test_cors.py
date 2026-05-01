"""Tests: CORS origins are restricted to the configured allowlist."""
import os
import types

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    import web_server as ws

    # Suppress service init errors in tests
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
    return TestClient(ws.app, raise_server_exceptions=False)


def test_cors_allowed_origin_included(client: TestClient):
    """Allowed origin gets Access-Control-Allow-Origin header."""
    res = client.options(
        "/api/personalities",
        headers={
            "Origin": "https://ai-avatar.signosoft.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in res.headers
    assert res.headers["access-control-allow-origin"] == "https://ai-avatar.signosoft.com"


def test_cors_disallowed_origin_excluded(client: TestClient):
    """Unknown origin does NOT get Access-Control-Allow-Origin header."""
    res = client.options(
        "/api/personalities",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_cors_localhost_dev_allowed(client: TestClient):
    """localhost:5173 (Vite dev) is allowed by default."""
    res = client.options(
        "/api/personalities",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in res.headers
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_env_var_parsed(monkeypatch: pytest.MonkeyPatch):
    """ALLOWED_ORIGINS env var is split and applied correctly."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://custom.example.com,http://127.0.0.1:9000")
    import importlib
    import web_server as ws

    importlib.reload(ws)
    assert "https://custom.example.com" in ws._ALLOWED_ORIGINS
    assert "http://127.0.0.1:9000" in ws._ALLOWED_ORIGINS
    # Default prod domain should NOT be present (it was replaced)
    assert "https://ai-avatar.signosoft.com" not in ws._ALLOWED_ORIGINS
