"""Avatar animation controllers (eyes, mouth, coordinated emotes).

These classes are deliberately pure state machines: they do not load assets and
do not perform any rendering. They only compute which sprite(s) should be shown
and how to blend between them.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.rendering.avatar_utils import smoothstep

# ---------------------------------------------------------------------------
# Eye sequences
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


@dataclass(frozen=True, slots=True)
class Blend:
    """A simple cross-fade definition."""

    from_idx: int
    to_idx: int
    t: float  # 0.0 = fully from_idx, 1.0 = fully to_idx


class EyeController:
    """Smooth, independent eye animation.

    Four async routines fire on randomised timers:
      blink     — regular + slow + double blinks, every ~2-4 s
      micro     — very brief glances, every ~3-5 s (kills the stare-down)
      glance    — longer look-aways, every ~6-14 s
      goofy     — multi-step silly sequences, every ~24-48 s

    All state changes cross-fade with smoothstep easing.
    """

    def __init__(self) -> None:
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

        # Staggered initial timers so nothing fires simultaneously.
        self._next_blink_ms: float = random.uniform(1500, 3500)
        self._next_micro_ms: float = random.uniform(2200, 5000)
        self._next_glance_ms: float = random.uniform(6000, 12000)
        self._next_expr_ms: float = random.uniform(12000, 24000)
        self._next_goofy_ms: float = random.uniform(24000, 42000)

    # ---- low-level transition primitives ---------------------------------

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

    # ---- sequences --------------------------------------------------------

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

    # ---- public API -------------------------------------------------------

    def get_blend(self, elapsed_ms: float) -> Blend:
        """Advance state machine and return current cross-fade blend."""
        if self._seq_active:
            self._advance_seq(elapsed_ms)

        elif self._looking_away and elapsed_ms >= self._look_return_ms:
            self._looking_away = False
            self.transition_to(0, 264.0, elapsed_ms)

        else:
            # Priority: blink > micro-glance > glance > goofy.
            if elapsed_ms >= self._next_blink_ms:
                seq = random.choices(
                    [s for s, _ in _BLINK_POOL],
                    weights=[w for _, w in _BLINK_POOL],
                )[0]
                self.play_sequence(seq, elapsed_ms)
                self._next_blink_ms = elapsed_ms + random.uniform(1800, 4200)

            elif elapsed_ms >= self._next_micro_ms:
                self.transition_to(random.choice([1, 8, 10, 11]), 174.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(204, 444)
                self._next_micro_ms = elapsed_ms + random.uniform(2800, 5800)

            elif elapsed_ms >= self._next_glance_ms:
                self.transition_to(random.choice([1, 8, 11]), 288.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(840, 1800)
                self._next_glance_ms = elapsed_ms + random.uniform(6500, 15000)

            elif elapsed_ms >= self._next_expr_ms:
                self.transition_to(random.choice([9, 12, 5, 7]), 336.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(1200, 3120)
                self._next_expr_ms = elapsed_ms + random.uniform(14000, 30000)

            elif elapsed_ms >= self._next_goofy_ms:
                self.play_sequence(random.choice(_GOOFY_POOL), elapsed_ms)
                self._next_goofy_ms = elapsed_ms + random.uniform(25000, 50000)

        t = self._t(elapsed_ms)
        return Blend(self._prev, self._current, t)

    @property
    def state_label(self) -> str:
        if self._seq_active:
            return "seq"
        if self._looking_away:
            return "look"
        return "idle"


# ---------------------------------------------------------------------------
# Mouth controller
# ---------------------------------------------------------------------------

# Subtle idle expressions — appear frequently, short holds.
_IDLE_MOUTH_SUBTLE: list[str] = ["on-side", "stunt", "stunt2"]
# Happy idle — occasional smiles.
_IDLE_MOUTH_HAPPY: list[str] = ["big-smile", "wide-smile"]
# Rare goofy idle — tongue, laugh, etc.
_IDLE_MOUTH_GOOFY: list[str] = ["tongue-out", "tongue-out2", "laugh", "laugh2", "laugh3"]
# Very rare dramatic idle.
_IDLE_MOUTH_DRAMATIC: list[str] = ["scream"]


class MouthController:
    """Randomised idle mouth animations when the avatar is not speaking."""

    IDLE_DELAY_MS: float = 3000.0  # start idle mouth after this much silence

    def __init__(self) -> None:
        # Current / previous sprite name (None = use speech viseme 0 / sil).
        self._current: str | None = None
        self._prev: str | None = None
        self._trans_start: float = 0.0
        self._trans_dur: float = 0.0
        self._in_trans: bool = False

        # When the avatar stopped speaking (set externally).
        self._idle_since_ms: float = 0.0
        self._idle: bool = False

        # Return-to-neutral timer.
        self._return_ms: float = 0.0
        self._holding: bool = False

        # Randomised next-fire timers (offsets from idle start).
        self._next_subtle_ms: float = 0.0
        self._next_happy_ms: float = 0.0
        self._next_goofy_ms: float = 0.0
        self._next_dramatic_ms: float = 0.0
        self._reset_timers(0.0)

    def _reset_timers(self, now_ms: float) -> None:
        self._next_subtle_ms = now_ms + random.uniform(3000, 6000)
        self._next_happy_ms = now_ms + random.uniform(8000, 16000)
        self._next_goofy_ms = now_ms + random.uniform(20000, 40000)
        self._next_dramatic_ms = now_ms + random.uniform(45000, 80000)

    # ---- transition primitives --------------------------------------------

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

    # ---- public API -------------------------------------------------------

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
            self._reset_timers(now_ms + self.IDLE_DELAY_MS)

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
        """Return (prev_name, current_name, blend_t).

        None means "draw the default sil viseme". blend_t controls cross-fade
        between prev and current sprite.
        """
        if not self._idle:
            return None, None, 1.0

        # Don't start idle animations until delay has passed.
        if elapsed_ms - self._idle_since_ms < self.IDLE_DELAY_MS:
            return None, None, 1.0

        # Return to neutral after hold.
        if self._holding and elapsed_ms >= self._return_ms:
            self._holding = False
            self.transition_to(None, 350.0, elapsed_ms)

        # Fire timers (priority: subtle > happy > goofy > dramatic).
        if not self._holding and not self._in_trans:
            if elapsed_ms >= self._next_subtle_ms:
                pool = [n for n in _IDLE_MOUTH_SUBTLE if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=300.0,
                        hold_ms=random.uniform(1200, 3000),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_subtle_ms = elapsed_ms + random.uniform(4000, 8000)

            elif elapsed_ms >= self._next_happy_ms:
                pool = [n for n in _IDLE_MOUTH_HAPPY if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=350.0,
                        hold_ms=random.uniform(2000, 4500),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_happy_ms = elapsed_ms + random.uniform(10000, 20000)

            elif elapsed_ms >= self._next_goofy_ms:
                pool = [n for n in _IDLE_MOUTH_GOOFY if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=280.0,
                        hold_ms=random.uniform(1500, 3500),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_goofy_ms = elapsed_ms + random.uniform(22000, 45000)

            elif elapsed_ms >= self._next_dramatic_ms:
                pool = [n for n in _IDLE_MOUTH_DRAMATIC if n in available]
                if pool:
                    self.begin_hold(
                        random.choice(pool),
                        transition_ms=400.0,
                        hold_ms=random.uniform(1800, 3500),
                        elapsed_ms=elapsed_ms,
                    )
                self._next_dramatic_ms = elapsed_ms + random.uniform(50000, 90000)

        t = self._t(elapsed_ms)
        return self._prev, self._current, t


# ---------------------------------------------------------------------------
# Coordinated emotes (eye + mouth together)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Emote:
    """A full-face emote: paired eye sequence + mouth sprite."""

    name: str
    eye_seq: list[tuple[int, float, float]]
    mouth: str
    mouth_hold_ms: float


EMOTES: list[Emote] = [
    Emote(
        name="grin",
        eye_seq=[(9, 250, 0)],  # squinting
        mouth="wide-smile",
        mouth_hold_ms=2800,
    ),
    Emote(
        name="laugh",
        eye_seq=[(3, 120, 80), (4, 100, 400), (3, 100, 80), (4, 100, 500), (0, 180, 0)],
        mouth="laugh2",
        mouth_hold_ms=2200,
    ),
    Emote(
        name="cheeky",
        eye_seq=[(11, 220, 0)],  # side glance
        mouth="tongue-out",
        mouth_hold_ms=2500,
    ),
    Emote(
        name="shocked",
        eye_seq=[(2, 180, 0)],  # open large pupils
        mouth="scream",
        mouth_hold_ms=2200,
    ),
    Emote(
        name="smug",
        eye_seq=[(5, 280, 0)],  # sleepy asymmetric
        mouth="on-side",
        mouth_hold_ms=3000,
    ),
    Emote(
        name="derp",
        eye_seq=[(13, 200, 600), (4, 80, 100), (13, 150, 400), (0, 220, 0)],
        mouth="tongue-out2",
        mouth_hold_ms=2000,
    ),
    Emote(
        name="hysterical",
        eye_seq=[(2, 90, 70), (14, 90, 70), (2, 90, 70), (14, 90, 70), (9, 180, 400), (0, 200, 0)],
        mouth="laugh3",
        mouth_hold_ms=2400,
    ),
]


class EmoteController:
    """Fires coordinated eye+mouth emotes on a random timer during idle."""

    IDLE_DELAY_MS: float = 5000.0  # wait this long after idle starts

    def __init__(self) -> None:
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
        if not self._idle:
            self._idle = True
            self._idle_since_ms = now_ms
            self._next_emote_ms = now_ms + self.IDLE_DELAY_MS + random.uniform(8000, 18000)

    def update(
        self,
        elapsed_ms: float,
        *,
        eye_ctrl: EyeController,
        mouth_ctrl: MouthController,
        available_mouths: dict[str, pygame.Surface],
    ) -> bool:
        """Tick the emote controller. Returns True if an emote is active.

        When active, the caller should skip independent eye/mouth updates
        (the emote drives both).
        """
        if not self._idle:
            return False

        if elapsed_ms - self._idle_since_ms < self.IDLE_DELAY_MS:
            return False

        # If an emote is playing, check if it's done.
        if self._active and self._emote:
            total_eye_ms = sum(t + h for _, t, h in self._emote.eye_seq)
            emote_dur = max(total_eye_ms, self._emote.mouth_hold_ms)
            if elapsed_ms - self._start_ms > emote_dur:
                self._active = False
                self._emote = None
                eye_ctrl.transition_to(0, 250.0, elapsed_ms)
                mouth_ctrl.transition_to(None, 350.0, elapsed_ms)
                self._next_emote_ms = elapsed_ms + random.uniform(15000, 35000)
                return False
            return True

        # Fire next emote?
        if elapsed_ms >= self._next_emote_ms:
            pool = [e for e in EMOTES if e.mouth in available_mouths]
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

            self._next_emote_ms = elapsed_ms + random.uniform(15000, 35000)

        return False
