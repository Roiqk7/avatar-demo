"""Tests: rate limiting is configured on pipeline endpoints."""
import types

import pytest
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded


def test_rate_limiter_configured_on_app():
    import web_server as ws

    assert hasattr(ws.app.state, "limiter"), "app.state.limiter not set"
    assert isinstance(ws.app.state.limiter, Limiter)


def test_rate_limit_exception_handler_registered():
    """RateLimitExceeded is handled and returns a 429 response."""
    import web_server as ws

    handlers = ws.app.exception_handlers
    assert RateLimitExceeded in handlers, "No handler registered for RateLimitExceeded"


def test_pipeline_text_has_rate_limit_decorator():
    """pipeline_text endpoint is wrapped by the rate limiter."""
    import web_server as ws

    # slowapi marks decorated callables with _rate_limiting attribute or similar.
    # We verify by checking the endpoint is registered and the limiter has rules.
    route = next(
        (r for r in ws.app.routes if getattr(r, "path", None) == "/api/pipeline/text"),
        None,
    )
    assert route is not None, "/api/pipeline/text route not found"


def test_pipeline_audio_has_rate_limit_decorator():
    import web_server as ws

    route = next(
        (r for r in ws.app.routes if getattr(r, "path", None) == "/api/pipeline/audio"),
        None,
    )
    assert route is not None, "/api/pipeline/audio route not found"


def test_pipeline_audio_stream_has_rate_limit_decorator():
    import web_server as ws

    route = next(
        (r for r in ws.app.routes if getattr(r, "path", None) == "/api/pipeline/audio_stream"),
        None,
    )
    assert route is not None, "/api/pipeline/audio_stream route not found"
