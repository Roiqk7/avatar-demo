import queue
import types

import pygame
import pytest

from backend.models import PipelineResult, TtsResult, VisemeEvent
from backend.rendering.avatar_window import AvatarWindow


def _make_window_stub() -> AvatarWindow:
    w = AvatarWindow.__new__(AvatarWindow)
    w._screen = pygame.Surface((200, 200), pygame.SRCALPHA)
    w._mouth_cx = 100
    w._mouth_cy = 120
    w._viseme_images = {0: pygame.Surface((10, 10), pygame.SRCALPHA)}
    w._idle_mouth_images = {"smile": pygame.Surface((8, 8), pygame.SRCALPHA)}
    w._eye_ctrl = types.SimpleNamespace(notify_speaking=lambda: None, state_label="idle")
    w._mouth_ctrl = types.SimpleNamespace(notify_speaking=lambda: None)
    w._emote_ctrl = types.SimpleNamespace(notify_speaking=lambda: None)
    w._play_queue = queue.Queue()
    w._visemes = []
    w._status_text = ""
    w._playing = False
    return w


def test_ready_property_reflects_internal_flag():
    w = AvatarWindow.__new__(AvatarWindow)
    w._ready = True
    assert w.ready is True
    w._ready = False
    assert w.ready is False


def test_play_enqueues_result():
    w = _make_window_stub()
    result = PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b""))
    w.play(result)
    assert w._play_queue.get_nowait() is result


def test_request_close_sets_flag():
    w = _make_window_stub()
    w._close_requested = False
    w.request_close()
    assert w._close_requested is True


def test_resolve_mouth_none_uses_sil_viseme():
    w = _make_window_stub()
    out = w._resolve_mouth(None)
    assert out is w._viseme_images[0]


def test_resolve_mouth_name_uses_idle_mouth():
    w = _make_window_stub()
    out = w._resolve_mouth("smile")
    assert out is w._idle_mouth_images["smile"]


@pytest.mark.parametrize("t,prev,cur,expected_calls", [(1.0, None, "smile", 1), (0.7, None, "smile", 2), (0.3, "smile", None, 2)])
def test_draw_idle_mouth_blits_expected_count(
    monkeypatch: pytest.MonkeyPatch,
    t: float,
    prev: str | None,
    cur: str | None,
    expected_calls: int,
):
    w = _make_window_stub()
    calls = []
    monkeypatch.setattr(
        "backend.rendering.avatar_window.blit_centered",
        lambda screen, surf, cx, cy, alpha=255: calls.append(alpha),
    )
    w._draw_idle_mouth(prev, cur, t)
    assert len(calls) == expected_calls


def test_start_playback_without_audio(monkeypatch: pytest.MonkeyPatch):
    w = _make_window_stub()
    notified = {"mouth": 0, "emote": 0}
    w._mouth_ctrl = types.SimpleNamespace(notify_speaking=lambda: notified.__setitem__("mouth", notified["mouth"] + 1))
    w._emote_ctrl = types.SimpleNamespace(notify_speaking=lambda: notified.__setitem__("emote", notified["emote"] + 1))
    monkeypatch.setattr("time.time", lambda: 123.0)
    result = PipelineResult(
        user_text="u",
        response_text="hello world",
        tts=TtsResult(audio_data=b"", visemes=[VisemeEvent(id=1, offset_ms=0)]),
    )
    w._start_playback(result)
    assert w._playing is True
    assert w._sound is None
    assert w._status_text == "hello world"
    assert notified == {"mouth": 1, "emote": 1}


def test_start_playback_with_audio(monkeypatch: pytest.MonkeyPatch):
    w = _make_window_stub()
    played = {"count": 0}

    class _Sound:
        def play(self):
            played["count"] += 1

    monkeypatch.setattr("pygame.mixer.Sound", lambda src: _Sound())
    monkeypatch.setattr("time.time", lambda: 50.0)
    result = PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"abc"))
    w._start_playback(result)
    assert played["count"] == 1
    assert w._sound is not None


def test_run_forever_when_not_ready_quits(monkeypatch: pytest.MonkeyPatch):
    w = AvatarWindow.__new__(AvatarWindow)
    w._ready = False
    called = {"quit": 0}
    monkeypatch.setattr("pygame.quit", lambda: called.__setitem__("quit", called["quit"] + 1))
    w.run_forever()
    assert called["quit"] == 1


def test_run_forever_handles_close_request(monkeypatch: pytest.MonkeyPatch):
    w = AvatarWindow.__new__(AvatarWindow)
    w._ready = True
    w._close_requested = True
    w._play_queue = queue.Queue()
    w._clock = types.SimpleNamespace(tick=lambda fps: None)
    w._screen = pygame.Surface((100, 100), pygame.SRCALPHA)
    w._face = pygame.Surface((50, 50), pygame.SRCALPHA)
    w._face_pos = (0, 0)
    w._eye_images = {}
    w._viseme_images = {0: pygame.Surface((5, 5), pygame.SRCALPHA)}
    w._idle_mouth_images = {}
    w._eye_ctrl = types.SimpleNamespace(get_blend=lambda ms: types.SimpleNamespace(t=1.0, from_idx=0, to_idx=0), state_label="idle")
    w._mouth_ctrl = types.SimpleNamespace(notify_idle=lambda ms: None, get_idle_mouth=lambda ms, imgs: (None, None, 1.0))
    w._emote_ctrl = types.SimpleNamespace(notify_idle=lambda ms: None, update=lambda *args, **kwargs: False)
    w._playing = False
    w._oneshot = False
    w._status_text = ""
    w._font = types.SimpleNamespace(render=lambda *args, **kwargs: pygame.Surface((1, 1)))
    w._mouth_cx = 10
    w._mouth_cy = 10
    w._eye_cx = 10
    w._eye_cy = 10
    w._sound = None
    monkeypatch.setattr("pygame.event.get", lambda: [])
    monkeypatch.setattr("pygame.display.flip", lambda: None)
    monkeypatch.setattr("pygame.mixer.quit", lambda: None)
    monkeypatch.setattr("pygame.quit", lambda: None)
    w.run_forever()
