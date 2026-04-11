"""Avatar animation controllers (eyes, mouth, coordinated emotes).

State machines are pure logic (no asset loading, no drawing). Behaviour is
driven by :mod:`backend.rendering.animation_config` and per-personality pools.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.rendering.animation_config import (
    EmoteTimingConfig,
    EyeAnimationConfig,
    MouthIdlePools,
    MouthTimingConfig,
)
from backend.rendering.emote_catalog import Emote
from backend.rendering.avatar_utils import smoothstep

# ---------------------------------------------------------------------------
# Eye sequences (for debugging / animation test viewer)
# Each step: (eye_idx, transition_in_ms, hold_ms)
# ---------------------------------------------------------------------------

SEQ_BLINK: list[tuple[int, float, float]] = [
    (3, 90, 42),
    (4, 66, 66),
    (3, 66, 42),
    (0, 114, 0),
]
SEQ_SLOW_BLINK: list[tuple[int, float, float]] = [
    (3, 138, 72),
    (4, 108, 108),
    (12, 96, 624),
    (3, 102, 60),
    (0, 168, 0),
]
SEQ_DOUBLE_BLINK: list[tuple[int, float, float]] = [
    (3, 78, 34),
    (4, 60, 54),
    (3, 60, 34),
    (0, 72, 228),
    (3, 78, 34),
    (4, 60, 54),
    (3, 60, 34),
    (0, 120, 0),
]

SEQ_SPIN: list[tuple[int, float, float]] = [
    (8, 138, 90),
    (10, 126, 78),
    (1, 126, 78),
    (11, 126, 78),
    (0, 186, 0),
]
SEQ_FRANTIC: list[tuple[int, float, float]] = [
    (2, 90, 66),
    (14, 90, 66),
    (2, 90, 66),
    (14, 90, 66),
    (0, 192, 0),
]
SEQ_CROSSEYED: list[tuple[int, float, float]] = [
    (13, 222, 432),
    (4, 72, 78),
    (13, 150, 372),
    (0, 252, 0),
]
SEQ_SHOCK_SQUINT: list[tuple[int, float, float]] = [
    (2, 150, 468),
    (9, 270, 720),
    (0, 234, 0),
]
SEQ_CONFUSED: list[tuple[int, float, float]] = [
    (10, 198, 240),
    (1, 174, 240),
    (5, 222, 504),
    (0, 222, 0),
]

EYE_SEQUENCE_CATALOG: list[tuple[str, list[tuple[int, float, float]]]] = [
    ("blink", SEQ_BLINK),
    ("slow-blink", SEQ_SLOW_BLINK),
    ("double-blink", SEQ_DOUBLE_BLINK),
    ("spin", SEQ_SPIN),
    ("frantic", SEQ_FRANTIC),
    ("crosseyed", SEQ_CROSSEYED),
    ("shock-squint", SEQ_SHOCK_SQUINT),
    ("confused", SEQ_CONFUSED),
]

_BLINK_POOL: list[tuple[list[tuple[int, float, float]], float]] = [
    (SEQ_BLINK, 0.65),
    (SEQ_SLOW_BLINK, 0.20),
    (SEQ_DOUBLE_BLINK, 0.15),
]
_GOOFY_POOL: list[list[tuple[int, float, float]]] = [
    SEQ_SPIN,
    SEQ_FRANTIC,
    SEQ_CROSSEYED,
    SEQ_SHOCK_SQUINT,
    SEQ_CONFUSED,
]


def _eye_seq_uses_forbidden(
    seq: list[tuple[int, float, float]], forbidden: frozenset[int]
) -> bool:
    return bool(forbidden) and any(idx in forbidden for idx, _, _ in seq)


@dataclass(frozen=True, slots=True)
class Blend:
    """A simple cross-fade definition."""

    from_idx: int
    to_idx: int
    t: float  # 0.0 = fully from_idx, 1.0 = fully to_idx


class EyeController:
    """Smooth, independent eye animation driven by :class:`EyeAnimationConfig`."""

    def __init__(self, cfg: EyeAnimationConfig) -> None:
        self._cfg: EyeAnimationConfig = cfg
        self.forbidden_eye_indices: frozenset[int] = cfg.forbidden_eye_indices
        self._current: int = 0
        self._prev: int = 0
        self._trans_start: float = 0.0
        self._trans_dur: float = 0.0
        self._in_trans: bool = False

        self._seq: list[tuple[int, float, float]] = []
        self._seq_step: int = 0
        self._seq_step_start: float = 0.0
        self._seq_active: bool = False

        self._look_return_ms: float = 0.0
        self._looking_away: bool = False

        self._next_blink_ms: float = random.uniform(*cfg.blink_initial_ms)
        self._next_micro_ms: float = (
            random.uniform(*cfg.micro_initial_ms) if cfg.enable_micro_glance else float("inf")
        )
        self._next_glance_ms: float = (
            random.uniform(*cfg.glance_initial_ms) if cfg.enable_long_glance else float("inf")
        )
        self._next_expr_ms: float = (
            random.uniform(*cfg.expr_initial_ms) if cfg.enable_expr_glance else float("inf")
        )
        self._next_goofy_ms: float = (
            random.uniform(*cfg.goofy_initial_ms) if cfg.enable_goofy_sequences else float("inf")
        )

    def transition_to(self, idx: int, dur_ms: float, elapsed_ms: float) -> None:
        """Start a smooth cross-fade to a new eye state."""
        if idx == self._current and not self._in_trans:
            return
        self._prev = self._visible(elapsed_ms)
        self._current = idx
        self._trans_start = elapsed_ms
        self._trans_dur = dur_ms
        self._in_trans = True

    def _visible(self, elapsed_ms: float) -> int:
        """Return whichever eye index is currently dominant (>50% opacity)."""
        return self._current if self._t(elapsed_ms) >= 0.5 else self._prev

    def _t(self, elapsed_ms: float) -> float:
        if not self._in_trans:
            return 1.0
        raw = (elapsed_ms - self._trans_start) / max(1.0, self._trans_dur)
        t = smoothstep(min(1.0, raw))
        if t >= 1.0:
            self._in_trans = False
        return t

    def play_sequence(self, seq: list[tuple[int, float, float]], elapsed_ms: float) -> None:
        """Begin a discrete eye sequence (blink/spin/etc)."""
        self._seq = seq
        self._seq_step = 0
        self._seq_step_start = elapsed_ms
        self._seq_active = True
        self._looking_away = False
        idx, trans_ms, _ = seq[0]
        self.transition_to(idx, trans_ms, elapsed_ms)

    def _advance_seq(self, elapsed_ms: float) -> None:
        if not self._seq_active:
            return
        _, trans_ms, hold_ms = self._seq[self._seq_step]
        if elapsed_ms - self._seq_step_start >= trans_ms + hold_ms:
            self._seq_step += 1
            if self._seq_step >= len(self._seq):
                self._seq_active = False
                return
            nidx, ntrans, _ = self._seq[self._seq_step]
            self.transition_to(nidx, ntrans, elapsed_ms)
            self._seq_step_start = elapsed_ms

    def get_blend(self, elapsed_ms: float) -> Blend:
        """Advance state machine and return current cross-fade blend."""
        cfg = self._cfg

        if self._seq_active:
            self._advance_seq(elapsed_ms)

        elif self._looking_away and elapsed_ms >= self._look_return_ms:
            self._looking_away = False
            self.transition_to(0, 264.0, elapsed_ms)

        else:
            if elapsed_ms >= self._next_blink_ms:
                seq = random.choices(
                    [s for s, _ in _BLINK_POOL],
                    weights=[w for _, w in _BLINK_POOL],
                )[0]
                self.play_sequence(seq, elapsed_ms)
                self._next_blink_ms = elapsed_ms + random.uniform(*cfg.blink_after_ms)

            elif (
                cfg.enable_micro_glance
                and cfg.micro_glance_indices
                and elapsed_ms >= self._next_micro_ms
            ):
                self.transition_to(random.choice(cfg.micro_glance_indices), cfg.micro_transition_ms, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(*cfg.micro_return_ms)
                self._next_micro_ms = elapsed_ms + random.uniform(*cfg.micro_after_ms)

            elif cfg.enable_long_glance and cfg.glance_indices and elapsed_ms >= self._next_glance_ms:
                self.transition_to(random.choice(cfg.glance_indices), cfg.glance_transition_ms, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(*cfg.glance_return_ms)
                self._next_glance_ms = elapsed_ms + random.uniform(*cfg.glance_after_ms)

            elif cfg.enable_expr_glance and cfg.expr_indices and elapsed_ms >= self._next_expr_ms:
                self.transition_to(random.choice(cfg.expr_indices), cfg.expr_transition_ms, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(*cfg.expr_return_ms)
                self._next_expr_ms = elapsed_ms + random.uniform(*cfg.expr_after_ms)

            elif cfg.enable_goofy_sequences and elapsed_ms >= self._next_goofy_ms:
                goofy_ok = [
                    s
                    for s in _GOOFY_POOL
                    if not _eye_seq_uses_forbidden(s, self.forbidden_eye_indices)
                ]
                if goofy_ok:
                    self.play_sequence(random.choice(goofy_ok), elapsed_ms)
                self._next_goofy_ms = elapsed_ms + random.uniform(*cfg.goofy_after_ms)

        t = self._t(elapsed_ms)
        return Blend(self._prev, self._current, t)

    @property
    def state_label(self) -> str:
        if self._seq_active:
            return "seq"
        if self._looking_away:
            return "look"
        return "idle"


class MouthController:
    """Randomised idle mouth animations when the avatar is not speaking."""

    def __init__(
        self,
        pools: MouthIdlePools,
        timing: MouthTimingConfig,
        *,
        idle_animation_enabled: bool = True,
    ) -> None:
        self._pools: MouthIdlePools = pools
        self._timing: MouthTimingConfig = timing
        self._idle_animation_enabled: bool = idle_animation_enabled
        self._current: str | None = None
        self._prev: str | None = None
        self._trans_start: float = 0.0
        self._trans_dur: float = 0.0
        self._in_trans: bool = False

        self._idle_since_ms: float = 0.0
        self._idle: bool = False

        self._return_ms: float = 0.0
        self._holding: bool = False

        self._next_subtle_ms: float = 0.0
        self._next_happy_ms: float = 0.0
        self._next_goofy_ms: float = 0.0
        self._next_dramatic_ms: float = 0.0
        self._reset_timers(0.0)

    def _reset_timers(self, now_ms: float) -> None:
        t = self._timing
        self._next_subtle_ms = now_ms + random.uniform(*t.subtle_next_initial)
        self._next_happy_ms = now_ms + random.uniform(*t.happy_next_initial)
        self._next_goofy_ms = now_ms + random.uniform(*t.goofy_next_initial)
        self._next_dramatic_ms = now_ms + random.uniform(*t.dramatic_next_initial)

    def transition_to(self, name: str | None, dur_ms: float, elapsed_ms: float) -> None:
        """Start a smooth cross-fade to a new mouth sprite name."""
        vis = self._visible(elapsed_ms)
        if name == vis:
            return
        self._prev = vis
        self._current = name
        self._trans_start = elapsed_ms
        self._trans_dur = dur_ms
        self._in_trans = True

    def _visible(self, elapsed_ms: float) -> str | None:
        return self._current if self._t(elapsed_ms) >= 0.5 else self._prev

    def _t(self, elapsed_ms: float) -> float:
        if not self._in_trans:
            return 1.0
        raw = (elapsed_ms - self._trans_start) / max(1.0, self._trans_dur)
        t = smoothstep(min(1.0, raw))
        if t >= 1.0:
            self._in_trans = False
        return t

    def notify_speaking(self) -> None:
        """Call when speech starts — resets idle state."""
        self._idle = False
        self._current = None
        self._prev = None
        self._in_trans = False
        self._holding = False

    def notify_idle(self, now_ms: float) -> None:
        """Call when speech stops — starts the idle delay countdown."""
        if not self._idle:
            self._idle = True
            self._idle_since_ms = now_ms
            self._reset_timers(now_ms + self._timing.idle_delay_ms)

    def begin_hold(
        self,
        name: str | None,
        *,
        transition_ms: float,
        hold_ms: float,
        elapsed_ms: float,
    ) -> None:
        """Force a mouth sprite for a fixed duration (used by emotes)."""
        self.transition_to(name, transition_ms, elapsed_ms)
        self._holding = True
        self._return_ms = elapsed_ms + hold_ms

    def get_idle_mouth(
        self,
        elapsed_ms: float,
        available: dict[str, pygame.Surface],
    ) -> tuple[str | None, str | None, float]:
        """Return (prev_name, current_name, blend_t). None means sil viseme."""
        if not self._idle:
            return None, None, 1.0

        if not self._idle_animation_enabled:
            return None, None, 1.0

        if elapsed_ms - self._idle_since_ms < self._timing.idle_delay_ms:
            return None, None, 1.0

        if self._holding and elapsed_ms >= self._return_ms:
            self._holding = False
            self.transition_to(None, self._timing.return_transition_ms, elapsed_ms)

        tcfg = self._timing
        pools = self._pools

        if not self._holding and not self._in_trans:
            if elapsed_ms >= self._next_subtle_ms:
                pool = [n for n in pools.subtle if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=tcfg.subtle_transition_ms,
                        hold_ms=random.uniform(*tcfg.subtle_hold_ms),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_subtle_ms = elapsed_ms + random.uniform(*tcfg.subtle_next_after)

            elif elapsed_ms >= self._next_happy_ms:
                pool = [n for n in pools.happy if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=tcfg.happy_transition_ms,
                        hold_ms=random.uniform(*tcfg.happy_hold_ms),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_happy_ms = elapsed_ms + random.uniform(*tcfg.happy_next_after)

            elif elapsed_ms >= self._next_goofy_ms:
                pool = [n for n in pools.goofy if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=tcfg.goofy_transition_ms,
                        hold_ms=random.uniform(*tcfg.goofy_hold_ms),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_goofy_ms = elapsed_ms + random.uniform(*tcfg.goofy_next_after)

            elif elapsed_ms >= self._next_dramatic_ms:
                pool = [n for n in pools.dramatic if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=tcfg.dramatic_transition_ms,
                        hold_ms=random.uniform(*tcfg.dramatic_hold_ms),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_dramatic_ms = elapsed_ms + random.uniform(*tcfg.dramatic_next_after)

        t = self._t(elapsed_ms)
        return self._prev, self._current, t


class EmoteController:
    """Fires coordinated eye+mouth emotes on a random timer during idle."""

    def __init__(self, emotes: list[Emote], timing: EmoteTimingConfig) -> None:
        self._emotes: list[Emote] = emotes
        self._timing: EmoteTimingConfig = timing
        self._idle: bool = False
        self._idle_since_ms: float = 0.0
        self._next_emote_ms: float = 0.0
        self._active: bool = False
        self._emote: Emote | None = None
        self._start_ms: float = 0.0

    def notify_speaking(self) -> None:
        self._idle = False
        self._active = False
        self._emote = None

    def notify_idle(self, now_ms: float) -> None:
        if not self._timing.enabled or not self._emotes:
            return
        if not self._idle:
            self._idle = True
            self._idle_since_ms = now_ms
            self._next_emote_ms = now_ms + self._timing.idle_delay_ms + random.uniform(
                *self._timing.first_emote_after_ms
            )

    def update(
        self,
        elapsed_ms: float,
        *,
        eye_ctrl: EyeController,
        mouth_ctrl: MouthController,
        available_mouths: dict[str, pygame.Surface],
    ) -> bool:
        """Tick the emote controller. Returns True if an emote is active."""
        if not self._timing.enabled or not self._emotes:
            return False

        if not self._idle:
            return False

        if elapsed_ms - self._idle_since_ms < self._timing.idle_delay_ms:
            return False

        if self._active and self._emote:
            total_eye_ms = sum(t + h for _, t, h in self._emote.eye_seq)
            emote_dur = max(total_eye_ms, self._emote.mouth_hold_ms)
            if elapsed_ms - self._start_ms > emote_dur:
                self._active = False
                self._emote = None
                eye_ctrl.transition_to(0, 250.0, elapsed_ms)
                mouth_ctrl.transition_to(None, 350.0, elapsed_ms)
                self._next_emote_ms = elapsed_ms + random.uniform(*self._timing.emote_after_ms)
                return False
            return True

        if elapsed_ms >= self._next_emote_ms:
            forbidden = eye_ctrl.forbidden_eye_indices
            pool = [
                e
                for e in self._emotes
                if e.mouth in available_mouths and not _eye_seq_uses_forbidden(e.eye_seq, forbidden)
            ]
            if pool:
                emote = random.choice(pool)
                self._emote = emote
                self._active = True
                self._start_ms = elapsed_ms
                eye_ctrl.play_sequence(emote.eye_seq, elapsed_ms)
                mouth_ctrl.begin_hold(
                    emote.mouth,
                    transition_ms=300.0,
                    hold_ms=emote.mouth_hold_ms,
                    elapsed_ms=elapsed_ms,
                )
                return True

            self._next_emote_ms = elapsed_ms + random.uniform(*self._timing.emote_after_ms)

        return False
