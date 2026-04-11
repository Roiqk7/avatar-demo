import pygame
import pytest

from backend.rendering.animation_config import (
    EMOTE_TIMING_PRESETS,
    EYE_PRESETS,
    MOUTH_TIMING_PRESETS,
    MouthIdlePools,
)
from backend.rendering.avatar_controllers import EmoteController, EyeController, MouthController, SEQ_BLINK
from backend.rendering.emote_catalog import resolve_emotes

_HYPER_EYE = EYE_PRESETS["hyperactive"]
_DEFAULT_POOLS = MouthIdlePools(
    subtle=("on-side", "stunt", "stunt2"),
    happy=("big-smile", "wide-smile"),
    goofy=("tongue-out",),
    dramatic=("scream",),
)
_HYPER_MOUTH_T = MOUTH_TIMING_PRESETS["hyperactive"]
_EMOTES = resolve_emotes(["grin", "laugh", "cheeky"])
_HYPER_EMOTE_T = EMOTE_TIMING_PRESETS["hyperactive"]


def test_eye_transition_and_visible_state():
    eye = EyeController(_HYPER_EYE)
    eye.transition_to(3, 100.0, 0.0)
    assert eye._current == 3
    assert eye._in_trans is True
    assert eye._visible(10.0) in (eye._prev, eye._current)


def test_eye_transition_to_same_index_noop_when_idle():
    eye = EyeController(_HYPER_EYE)
    eye._current = 0
    eye._in_trans = False
    eye.transition_to(0, 100.0, 0.0)
    assert eye._in_trans is False


def test_eye_t_finishes_transition():
    eye = EyeController(_HYPER_EYE)
    eye.transition_to(1, 100.0, 0.0)
    t = eye._t(500.0)
    assert t == 1.0
    assert eye._in_trans is False


def test_eye_play_sequence_sets_first_step():
    eye = EyeController(_HYPER_EYE)
    eye.play_sequence(SEQ_BLINK, 1000.0)
    assert eye._seq_active is True
    assert eye._seq_step == 0
    assert eye._current == SEQ_BLINK[0][0]


def test_eye_sequence_advances_and_stops():
    eye = EyeController(_HYPER_EYE)
    eye.play_sequence([(1, 10, 0), (2, 10, 0)], 0.0)
    eye._advance_seq(20.0)
    assert eye._seq_step == 1
    eye._advance_seq(40.0)
    assert eye._seq_active is False


def test_eye_advance_seq_noop_when_inactive():
    eye = EyeController(_HYPER_EYE)
    eye._seq_active = False
    eye._advance_seq(100.0)
    assert eye._seq_active is False


@pytest.mark.parametrize("label,seq_active,looking", [("seq", True, False), ("look", False, True), ("idle", False, False)])
def test_eye_state_label(label: str, seq_active: bool, looking: bool):
    eye = EyeController(_HYPER_EYE)
    eye._seq_active = seq_active
    eye._looking_away = looking
    assert eye.state_label == label


def test_eye_get_blend_triggers_blink(monkeypatch: pytest.MonkeyPatch):
    eye = EyeController(_HYPER_EYE)
    eye._next_blink_ms = 0.0
    eye._next_micro_ms = 999999
    eye._next_glance_ms = 999999
    eye._next_expr_ms = 999999
    eye._next_goofy_ms = 999999
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.choices", lambda seq, weights: [seq[0]])
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.uniform", lambda a, b: a)
    blend = eye.get_blend(1.0)
    assert blend.to_idx == SEQ_BLINK[0][0]
    assert eye._seq_active is True


@pytest.mark.parametrize(
    ("attr_name", "choices", "expected_current"),
    [
        ("_next_micro_ms", [1, 8, 10, 11], 1),
        ("_next_glance_ms", [1, 8, 11], 1),
        ("_next_expr_ms", [9, 12, 5, 7], 9),
    ],
)
def test_eye_get_blend_triggers_look_transitions(
    monkeypatch: pytest.MonkeyPatch,
    attr_name: str,
    choices: list[int],
    expected_current: int,
):
    eye = EyeController(_HYPER_EYE)
    eye._next_blink_ms = 999999
    eye._next_micro_ms = 999999
    eye._next_glance_ms = 999999
    eye._next_expr_ms = 999999
    eye._next_goofy_ms = 999999
    setattr(eye, attr_name, 0.0)
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.choice", lambda pool: choices[0])
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.uniform", lambda a, b: a)
    eye.get_blend(1.0)
    assert eye._current == expected_current
    assert eye._looking_away is True


def test_eye_get_blend_triggers_goofy_sequence(monkeypatch: pytest.MonkeyPatch):
    eye = EyeController(_HYPER_EYE)
    eye._next_blink_ms = 999999
    eye._next_micro_ms = 999999
    eye._next_glance_ms = 999999
    eye._next_expr_ms = 999999
    eye._next_goofy_ms = 0.0
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.choice", lambda pool: pool[0])
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.uniform", lambda a, b: a)
    eye.get_blend(1.0)
    assert eye._seq_active is True


def test_mouth_notify_speaking_resets():
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    mouth._idle = True
    mouth._current = "x"
    mouth._prev = "y"
    mouth._in_trans = True
    mouth._holding = True
    mouth.notify_speaking()
    assert mouth._idle is False
    assert mouth._current is None
    assert mouth._prev is None
    assert mouth._in_trans is False
    assert mouth._holding is False


def test_mouth_transition_to_visible_name_noop():
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    mouth._current = "smile"
    mouth._prev = "other"
    mouth._in_trans = False
    mouth.transition_to("smile", 100.0, 0.0)
    assert mouth._in_trans is False


def test_mouth_notify_idle_sets_timers(monkeypatch: pytest.MonkeyPatch):
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.uniform", lambda a, b: a)
    mouth.notify_idle(100.0)
    assert mouth._idle is True
    assert mouth._idle_since_ms == 100.0
    assert mouth._next_subtle_ms >= 100.0 + mouth._timing.idle_delay_ms


def test_mouth_get_idle_before_delay_returns_neutral():
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    mouth.notify_idle(0.0)
    prev, cur, t = mouth.get_idle_mouth(1000.0, {})
    assert (prev, cur, t) == (None, None, 1.0)


def test_mouth_idle_animation_disabled_never_shows_idle_sprites():
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T, idle_animation_enabled=False)
    mouth.notify_idle(0.0)
    avail = {"on-side": pygame.Surface((1, 1))}
    prev, cur, t = mouth.get_idle_mouth(999999.0, avail)
    assert (prev, cur, t) == (None, None, 1.0)


def test_mouth_get_idle_returns_neutral_when_not_idle():
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    prev, cur, t = mouth.get_idle_mouth(1000.0, {})
    assert (prev, cur, t) == (None, None, 1.0)


def test_mouth_begin_hold_then_return_to_none(monkeypatch: pytest.MonkeyPatch):
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    mouth._idle = True
    mouth._idle_since_ms = -10000
    mouth.begin_hold("laugh", transition_ms=50.0, hold_ms=100.0, elapsed_ms=0.0)
    assert mouth._holding is True
    mouth.get_idle_mouth(150.0, {"laugh": pygame.Surface((1, 1))})
    assert mouth._holding is False


@pytest.mark.parametrize(
    ("timer_attr", "available", "expected_name"),
    [
        ("_next_subtle_ms", {"on-side": pygame.Surface((1, 1))}, "on-side"),
        ("_next_happy_ms", {"big-smile": pygame.Surface((1, 1))}, "big-smile"),
        ("_next_goofy_ms", {"tongue-out": pygame.Surface((1, 1))}, "tongue-out"),
        ("_next_dramatic_ms", {"scream": pygame.Surface((1, 1))}, "scream"),
    ],
)
def test_mouth_idle_timers_trigger_holds(
    monkeypatch: pytest.MonkeyPatch,
    timer_attr: str,
    available: dict[str, pygame.Surface],
    expected_name: str,
):
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    mouth._idle = True
    mouth._idle_since_ms = -10000
    mouth._in_trans = False
    mouth._holding = False
    mouth._next_subtle_ms = 999999
    mouth._next_happy_ms = 999999
    mouth._next_goofy_ms = 999999
    mouth._next_dramatic_ms = 999999
    setattr(mouth, timer_attr, 0.0)
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.choice", lambda pool: list(available.keys())[0])
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.uniform", lambda a, b: a)
    _, cur, _ = mouth.get_idle_mouth(1.0, available)
    assert cur == expected_name


def test_emote_update_returns_false_when_not_idle():
    emote = EmoteController(_EMOTES, _HYPER_EMOTE_T)
    eye = EyeController(_HYPER_EYE)
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    assert emote.update(1.0, eye_ctrl=eye, mouth_ctrl=mouth, available_mouths={}) is False


def test_emote_notify_speaking_clears_active():
    emote = EmoteController(_EMOTES, _HYPER_EMOTE_T)
    emote._idle = True
    emote._active = True
    emote._emote = object()  # type: ignore[assignment]
    emote.notify_speaking()
    assert emote._idle is False
    assert emote._active is False
    assert emote._emote is None


def test_emote_update_returns_false_before_delay():
    emote = EmoteController(_EMOTES, _HYPER_EMOTE_T)
    eye = EyeController(_HYPER_EYE)
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    emote.notify_idle(0.0)
    assert emote.update(100.0, eye_ctrl=eye, mouth_ctrl=mouth, available_mouths={}) is False


def test_emote_update_starts_emote(monkeypatch: pytest.MonkeyPatch):
    emote = EmoteController(_EMOTES, _HYPER_EMOTE_T)
    eye = EyeController(_HYPER_EYE)
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    emote.notify_idle(0.0)
    emote._next_emote_ms = 0.0
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.choice", lambda pool: pool[0])
    available = {"wide-smile": pygame.Surface((1, 1)), "laugh2": pygame.Surface((1, 1)), "tongue-out": pygame.Surface((1, 1))}
    active = emote.update(10000.0, eye_ctrl=eye, mouth_ctrl=mouth, available_mouths=available)
    assert active is True
    assert emote._active is True


def test_emote_update_completes_active_emote(monkeypatch: pytest.MonkeyPatch):
    emote = EmoteController(_EMOTES, _HYPER_EMOTE_T)
    eye = EyeController(_HYPER_EYE)
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    emote.notify_idle(0.0)
    emote._next_emote_ms = 0.0
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.choice", lambda pool: pool[0])
    available = {"wide-smile": pygame.Surface((1, 1)), "laugh2": pygame.Surface((1, 1)), "tongue-out": pygame.Surface((1, 1))}
    emote.update(10000.0, eye_ctrl=eye, mouth_ctrl=mouth, available_mouths=available)
    done = emote.update(20000.0, eye_ctrl=eye, mouth_ctrl=mouth, available_mouths=available)
    assert done is False
    assert emote._active is False


def test_emote_update_no_available_mouths_reschedules(monkeypatch: pytest.MonkeyPatch):
    emote = EmoteController(_EMOTES, _HYPER_EMOTE_T)
    eye = EyeController(_HYPER_EYE)
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    emote.notify_idle(0.0)
    emote._next_emote_ms = 0.0
    monkeypatch.setattr("backend.rendering.avatar_controllers.random.uniform", lambda a, b: a)
    assert emote.update(10000.0, eye_ctrl=eye, mouth_ctrl=mouth, available_mouths={}) is False
    assert emote._next_emote_ms >= 10000.0


def test_emote_disabled_never_schedules():
    timing = EMOTE_TIMING_PRESETS["boring"]
    emote = EmoteController(_EMOTES, timing)
    eye = EyeController(_HYPER_EYE)
    mouth = MouthController(_DEFAULT_POOLS, _HYPER_MOUTH_T)
    emote.notify_idle(0.0)
    assert emote.update(1_000_000.0, eye_ctrl=eye, mouth_ctrl=mouth, available_mouths={"wide-smile": pygame.Surface((1, 1))}) is False
