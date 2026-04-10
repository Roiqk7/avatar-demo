import io
import logging
import os
import queue
import random
import time
from dataclasses import dataclass
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.models import PipelineResult, VisemeEvent

logger: logging.Logger = logging.getLogger("backend.avatar")

WINDOW_WIDTH: int = 600
WINDOW_HEIGHT: int = 700
BG_COLOR: tuple[int, int, int] = (40, 40, 50)

ASSETS_DIR: Path = Path(__file__).parent.parent / "assets"
VISEME_LABELS: tuple[str, ...] = (
    "sil",
    "ah",
    "aa",
    "aw",
    "eh",
    "er",
    "ee",
    "oo",
    "oh",
    "ow",
    "oy",
    "eye",
    "h",
    "r",
    "l",
    "s",
    "sh",
    "th",
    "f",
    "t",
    "k",
    "m",
)

IDLE_MOUTH_NAMES: tuple[str, ...] = (
    "big-smile",
    "wide-smile",
    # "sad",
    #"sad2",
    "on-side",
    # "stunt",
    "stunt2",
    "tongue-out",
    "tongue-out2",
    "laugh",
    "laugh2",
    "laugh3",
    #"angry",
    #"cry",
    #"cry2",
    "scream",
)

MOUTH_WIDTH_RATIO: float = 0.55
MOUTH_HEIGHT_RATIO: float = 0.35
MOUTH_Y_RATIO: float = 0.72

# Fine-tune these if the eye overlay doesn't land on the face's eye sockets.
EYE_Y_RATIO: float = 0.36      # fraction of face height from top → eye centre
EYE_WIDTH_RATIO: float = 0.72  # max eye width as fraction of face width
EYE_HEIGHT_RATIO: float = 0.45 # max eye height as fraction of face width


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _smoothstep(t: float) -> float:
    """Ease-in-out curve: smooth, natural-feeling transitions."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _scale_to_fit(surface: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    ow, oh = surface.get_size()
    r = min(max_w / ow, max_h / oh)
    return pygame.transform.smoothscale(surface, (int(ow * r), int(oh * r)))


def _scale_to_width(surface: pygame.Surface, target_w: int) -> pygame.Surface:
    """Scale to a fixed width, letting height vary proportionally."""
    ow, oh = surface.get_size()
    r = target_w / ow
    return pygame.transform.smoothscale(surface, (int(ow * r), int(oh * r)))


def _trim_to_content(surf: pygame.Surface, pad: int = 8) -> pygame.Surface:
    """Remove transparent border pixels, keeping a small padding around content.

    Eye PNGs extracted from a sprite sheet carry silent transparent rows from
    cell boundaries.  Trimming ensures the visual eye content lands at eye_cy
    rather than the geometric centre of a padded canvas.

    Uses numpy (always available in this project) to scan the alpha channel.
    Returns the original surface unchanged if anything goes wrong.
    """
    try:
        import numpy as np
        alpha = pygame.surfarray.pixels_alpha(surf)  # shape (W, H)
        col_has = np.any(alpha > 15, axis=1)          # (W,) — column has content
        row_has = np.any(alpha > 15, axis=0)          # (H,) — row    has content
        del alpha                                       # release the surface lock
        if not (col_has.any() and row_has.any()):
            return surf
        x_idx = np.where(col_has)[0]
        y_idx = np.where(row_has)[0]
        x0 = max(0,                   int(x_idx[0])  - pad)
        x1 = min(surf.get_width()  - 1, int(x_idx[-1]) + pad)
        y0 = max(0,                   int(y_idx[0])  - pad)
        y1 = min(surf.get_height() - 1, int(y_idx[-1]) + pad)
        if x1 <= x0 or y1 <= y0:
            return surf
        return surf.subsurface(pygame.Rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)).copy()
    except Exception:
        return surf


def _load_face(face_width: int) -> pygame.Surface | None:
    path: Path = ASSETS_DIR / "avatar-base.png"
    if not path.exists():
        return None
    return _scale_to_fit(pygame.image.load(str(path)).convert_alpha(), face_width, face_width)


def _load_visemes(max_w: int, max_h: int) -> dict[int, pygame.Surface]:
    images: dict[int, pygame.Surface] = {}
    for i, label in enumerate(VISEME_LABELS):
        path = ASSETS_DIR / "visemes" / f"viseme-{i:02d}-{label}.png"
        if path.exists():
            images[i] = _scale_to_fit(pygame.image.load(str(path)).convert_alpha(), max_w, max_h)
    return images


def _load_idle_mouths(max_w: int, max_h: int) -> dict[str, pygame.Surface]:
    images: dict[str, pygame.Surface] = {}
    for name in IDLE_MOUTH_NAMES:
        path = ASSETS_DIR / "visemes" / f"viseme-{name}.png"
        if path.exists():
            images[name] = _scale_to_fit(
                pygame.image.load(str(path)).convert_alpha(), max_w, max_h,
            )
    return images


def _load_eyes(max_w: int, max_h: int) -> dict[int, pygame.Surface]:
    """Load eyes scaled to fit within max_w x max_h (preserving aspect ratio).

    All eye PNGs share the same canvas (from the union-bbox extraction),
    so they scale uniformly and maintain relative sizing between sprites.
    """
    images: dict[int, pygame.Surface] = {}
    eyes_dir: Path = ASSETS_DIR / "eyes"
    if not eyes_dir.exists():
        return images
    for path in sorted(eyes_dir.glob("eye-*.png")):
        try:
            idx = int(path.name.split("-")[1])
            raw = pygame.image.load(str(path)).convert_alpha()
            images[idx] = _scale_to_fit(raw, max_w, max_h)
        except Exception as exc:
            logger.debug("Skipping eye %s: %s", path.name, exc)
    return images


def _get_active_viseme(visemes: list[VisemeEvent], elapsed_ms: float) -> int:
    active: int = 0
    for v in visemes:
        if v.offset_ms <= elapsed_ms:
            active = v.id
        else:
            break
    return active


def _blit_eye(
    screen: pygame.Surface,
    surf: pygame.Surface,
    cx: int,
    cy: int,
    alpha: int = 255,
) -> None:
    """Blit an eye surface centered at (cx, cy) with per-surface alpha."""
    if alpha <= 0:
        return
    x = cx - surf.get_width() // 2
    y = cy - surf.get_height() // 2
    if alpha >= 255:
        screen.blit(surf, (x, y))
    else:
        surf.set_alpha(alpha)
        screen.blit(surf, (x, y))
        surf.set_alpha(255)


# ---------------------------------------------------------------------------
# Eye sequences
# Each step: (eye_idx, transition_in_ms, hold_ms)
# ---------------------------------------------------------------------------

_SEQ_BLINK: list[tuple[int, float, float]] = [
    (3, 90, 42), (4, 66, 66), (3, 66, 42), (0, 114, 0),
]
_SEQ_SLOW_BLINK: list[tuple[int, float, float]] = [
    (3, 138, 72), (4, 108, 108), (12, 96, 624), (3, 102, 60), (0, 168, 0),
]
_SEQ_DOUBLE_BLINK: list[tuple[int, float, float]] = [
    (3, 78, 34), (4, 60, 54), (3, 60, 34), (0, 72, 228),
    (3, 78, 34), (4, 60, 54), (3, 60, 34), (0, 120, 0),
]

_SEQ_SPIN: list[tuple[int, float, float]] = [
    (8, 138, 90), (10, 126, 78), (1, 126, 78), (11, 126, 78), (0, 186, 0),
]
_SEQ_FRANTIC: list[tuple[int, float, float]] = [
    (2, 90, 66), (14, 90, 66), (2, 90, 66), (14, 90, 66), (0, 192, 0),
]
_SEQ_CROSSEYED: list[tuple[int, float, float]] = [
    (13, 222, 432), (4, 72, 78), (13, 150, 372), (0, 252, 0),
]
_SEQ_SHOCK_SQUINT: list[tuple[int, float, float]] = [
    (2, 150, 468), (9, 270, 720), (0, 234, 0),
]
_SEQ_CONFUSED: list[tuple[int, float, float]] = [
    (10, 198, 240), (1, 174, 240), (5, 222, 504), (0, 222, 0),
]

_BLINK_POOL: list[tuple[list[tuple[int, float, float]], float]] = [
    (_SEQ_BLINK, 0.65),
    (_SEQ_SLOW_BLINK, 0.20),
    (_SEQ_DOUBLE_BLINK, 0.15),
]
_GOOFY_POOL: list[list[tuple[int, float, float]]] = [
    _SEQ_SPIN, _SEQ_FRANTIC, _SEQ_CROSSEYED, _SEQ_SHOCK_SQUINT, _SEQ_CONFUSED,
]


# ---------------------------------------------------------------------------
# Eye blend state
# ---------------------------------------------------------------------------

@dataclass
class _Blend:
    from_idx: int
    to_idx: int
    t: float  # 0.0 = fully from_idx, 1.0 = fully to_idx


# ---------------------------------------------------------------------------
# EyeController
# ---------------------------------------------------------------------------

class EyeController:
    """
    Smooth, independent eye animation.

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

        # Staggered initial timers so nothing fires simultaneously
        self._next_blink_ms: float = random.uniform(1500, 3500)
        self._next_micro_ms: float = random.uniform(2200, 5000)
        self._next_glance_ms: float = random.uniform(6000, 12000)
        self._next_expr_ms: float = random.uniform(12000, 24000)
        self._next_goofy_ms: float = random.uniform(24000, 42000)

    # ------------------------------------------------------------------
    # Internal transition helpers
    # ------------------------------------------------------------------

    def _go(self, idx: int, dur_ms: float, elapsed_ms: float) -> None:
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
        t = _smoothstep(min(1.0, raw))
        if t >= 1.0:
            self._in_trans = False
        return t

    # ------------------------------------------------------------------
    # Sequence helpers
    # ------------------------------------------------------------------

    def _start_seq(self, seq: list[tuple[int, float, float]], elapsed_ms: float) -> None:
        self._seq = seq
        self._seq_step = 0
        self._seq_step_start = elapsed_ms
        self._seq_active = True
        self._looking_away = False
        idx, trans_ms, _ = seq[0]
        self._go(idx, trans_ms, elapsed_ms)

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
            self._go(nidx, ntrans, elapsed_ms)
            self._seq_step_start = elapsed_ms

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_blend(self, elapsed_ms: float) -> _Blend:
        """Advance state machine and return current cross-fade blend."""
        if self._seq_active:
            self._advance_seq(elapsed_ms)

        elif self._looking_away and elapsed_ms >= self._look_return_ms:
            self._looking_away = False
            self._go(0, 264.0, elapsed_ms)

        else:
            # Priority: blink > micro-glance > glance > goofy
            if elapsed_ms >= self._next_blink_ms:
                seq = random.choices(
                    [s for s, _ in _BLINK_POOL],
                    weights=[w for _, w in _BLINK_POOL],
                )[0]
                self._start_seq(seq, elapsed_ms)
                self._next_blink_ms = elapsed_ms + random.uniform(1800, 4200)

            elif elapsed_ms >= self._next_micro_ms:
                self._go(random.choice([1, 8, 10, 11]), 174.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(204, 444)
                self._next_micro_ms = elapsed_ms + random.uniform(2800, 5800)

            elif elapsed_ms >= self._next_glance_ms:
                self._go(random.choice([1, 8, 11]), 288.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(840, 1800)
                self._next_glance_ms = elapsed_ms + random.uniform(6500, 15000)

            elif elapsed_ms >= self._next_expr_ms:
                self._go(random.choice([9, 12, 5, 7]), 336.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(1200, 3120)
                self._next_expr_ms = elapsed_ms + random.uniform(14000, 30000)

            elif elapsed_ms >= self._next_goofy_ms:
                self._start_seq(random.choice(_GOOFY_POOL), elapsed_ms)
                self._next_goofy_ms = elapsed_ms + random.uniform(25000, 50000)

        t = self._t(elapsed_ms)
        return _Blend(self._prev, self._current, t)

    @property
    def state_label(self) -> str:
        if self._seq_active:
            return "seq"
        if self._looking_away:
            return "look"
        return "idle"


# ---------------------------------------------------------------------------
# Idle mouth controller
# ---------------------------------------------------------------------------

# Subtle idle expressions — appear frequently, short holds
_IDLE_MOUTH_SUBTLE: list[str] = ["on-side", "stunt", "stunt2"]
# Happy idle — occasional smiles
_IDLE_MOUTH_HAPPY: list[str] = ["big-smile", "wide-smile"]
# Rare goofy idle — tongue, laugh, etc.
_IDLE_MOUTH_GOOFY: list[str] = [
    "tongue-out", "tongue-out2", "laugh", "laugh2", "laugh3",
]
# Very rare dramatic idle
_IDLE_MOUTH_DRAMATIC: list[str] = ["scream"]


class MouthController:
    """Randomised idle mouth animations when the avatar is not speaking.

    Works on the same principle as EyeController: smooth cross-fades
    between mouth sprites on randomised timers.  Only active after a
    configurable idle delay (default 3 s).
    """

    IDLE_DELAY_MS: float = 3000.0  # start idle mouth after this much silence

    def __init__(self) -> None:
        # Current / previous sprite name (None = use speech viseme 0 / sil)
        self._current: str | None = None
        self._prev: str | None = None
        self._trans_start: float = 0.0
        self._trans_dur: float = 0.0
        self._in_trans: bool = False

        # When the avatar stopped speaking (set externally)
        self._idle_since_ms: float = 0.0
        self._idle: bool = False

        # Return-to-neutral timer
        self._return_ms: float = 0.0
        self._holding: bool = False

        # Randomised next-fire timers (offsets from idle start)
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

    # -- transition helpers ------------------------------------------------

    def _go(self, name: str | None, dur_ms: float, elapsed_ms: float) -> None:
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
        t = _smoothstep(min(1.0, raw))
        if t >= 1.0:
            self._in_trans = False
        return t

    # -- public API --------------------------------------------------------

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

    def get_idle_mouth(
        self, elapsed_ms: float, available: dict[str, pygame.Surface],
    ) -> tuple[str | None, str | None, float]:
        """Return (prev_name, current_name, blend_t).

        None means draw the default sil viseme. blend_t controls cross-fade
        between prev and current sprite.
        """
        if not self._idle:
            return None, None, 1.0

        # Don't start idle animations until delay has passed
        if elapsed_ms - self._idle_since_ms < self.IDLE_DELAY_MS:
            return None, None, 1.0

        # Return to neutral after hold
        if self._holding and elapsed_ms >= self._return_ms:
            self._holding = False
            self._go(None, 350.0, elapsed_ms)

        # Fire timers (priority: subtle > happy > goofy > dramatic)
        if not self._holding and not self._in_trans:
            if elapsed_ms >= self._next_subtle_ms:
                pool = [n for n in _IDLE_MOUTH_SUBTLE if n in available]
                if pool:
                    self._go(random.choice(pool), 300.0, elapsed_ms)
                    self._holding = True
                    self._return_ms = elapsed_ms + random.uniform(1200, 3000)
                self._next_subtle_ms = elapsed_ms + random.uniform(4000, 8000)

            elif elapsed_ms >= self._next_happy_ms:
                pool = [n for n in _IDLE_MOUTH_HAPPY if n in available]
                if pool:
                    self._go(random.choice(pool), 350.0, elapsed_ms)
                    self._holding = True
                    self._return_ms = elapsed_ms + random.uniform(2000, 4500)
                self._next_happy_ms = elapsed_ms + random.uniform(10000, 20000)

            elif elapsed_ms >= self._next_goofy_ms:
                pool = [n for n in _IDLE_MOUTH_GOOFY if n in available]
                if pool:
                    self._go(random.choice(pool), 280.0, elapsed_ms)
                    self._holding = True
                    self._return_ms = elapsed_ms + random.uniform(1500, 3500)
                self._next_goofy_ms = elapsed_ms + random.uniform(22000, 45000)

            elif elapsed_ms >= self._next_dramatic_ms:
                pool = [n for n in _IDLE_MOUTH_DRAMATIC if n in available]
                if pool:
                    self._go(random.choice(pool), 400.0, elapsed_ms)
                    self._holding = True
                    self._return_ms = elapsed_ms + random.uniform(1800, 3500)
                self._next_dramatic_ms = elapsed_ms + random.uniform(50000, 90000)

        t = self._t(elapsed_ms)
        return self._prev, self._current, t


# ---------------------------------------------------------------------------
# Coordinated emotes (eye + mouth together)
# ---------------------------------------------------------------------------

@dataclass
class _Emote:
    """A full-face emote: paired eye sequence + mouth sprite."""
    name: str
    # Eye sequence: list of (eye_idx, transition_ms, hold_ms)
    eye_seq: list[tuple[int, float, float]]
    # Mouth sprite name to show for the duration
    mouth: str
    # How long the mouth stays before returning to sil (ms)
    mouth_hold_ms: float


_EMOTES: list[_Emote] = [
    # 1. Big grin — squinting eyes + wide smile
    _Emote(
        name="grin",
        eye_seq=[(9, 250, 0)],  # squinting
        mouth="wide-smile",
        mouth_hold_ms=2800,
    ),
    # 2. Laugh — eyes closed + laugh mouth
    _Emote(
        name="laugh",
        eye_seq=[
            (3, 120, 80), (4, 100, 400), (3, 100, 80),
            (4, 100, 500), (0, 180, 0),
        ],
        mouth="laugh2",
        mouth_hold_ms=2200,
    ),
    # 3. Cheeky — side glance + tongue out
    _Emote(
        name="cheeky",
        eye_seq=[(11, 220, 0)],  # side glance
        mouth="tongue-out",
        mouth_hold_ms=2500,
    ),
    # 4. Shocked — large pupils + scream
    _Emote(
        name="shocked",
        eye_seq=[(2, 180, 0)],  # open large pupils
        mouth="scream",
        mouth_hold_ms=2200,
    ),
    # 5. Smug — sleepy/asymmetric eyes + on-side smirk
    _Emote(
        name="smug",
        eye_seq=[(5, 280, 0)],  # sleepy asymmetric
        mouth="on-side",
        mouth_hold_ms=3000,
    ),
    # 6. Derpy — crossed eyes + tongue out
    _Emote(
        name="derp",
        eye_seq=[(13, 200, 600), (4, 80, 100), (13, 150, 400), (0, 220, 0)],
        mouth="tongue-out2",
        mouth_hold_ms=2000,
    ),
    # 7. Hysterical — frantic eyes + big laugh
    _Emote(
        name="hysterical",
        eye_seq=[
            (2, 90, 70), (14, 90, 70), (2, 90, 70), (14, 90, 70),
            (9, 180, 400), (0, 200, 0),
        ],
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
        self._emote: _Emote | None = None
        self._start_ms: float = 0.0

    def notify_speaking(self) -> None:
        self._idle = False
        self._active = False
        self._emote = None

    def notify_idle(self, now_ms: float) -> None:
        if not self._idle:
            self._idle = True
            self._idle_since_ms = now_ms
            self._next_emote_ms = now_ms + self.IDLE_DELAY_MS + random.uniform(
                8000, 18000,
            )

    def update(
        self,
        elapsed_ms: float,
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

        # If an emote is playing, check if it's done
        if self._active and self._emote:
            total_eye_ms = sum(t + h for _, t, h in self._emote.eye_seq)
            emote_dur = max(total_eye_ms, self._emote.mouth_hold_ms)
            if elapsed_ms - self._start_ms > emote_dur:
                # Done — return to neutral
                self._active = False
                self._emote = None
                eye_ctrl._go(0, 250.0, elapsed_ms)
                mouth_ctrl._go(None, 350.0, elapsed_ms)
                mouth_ctrl._holding = False
                self._next_emote_ms = elapsed_ms + random.uniform(15000, 35000)
                return False
            return True

        # Fire next emote?
        if elapsed_ms >= self._next_emote_ms:
            # Pick a random emote whose mouth sprite is available
            pool = [e for e in _EMOTES if e.mouth in available_mouths]
            if pool:
                emote = random.choice(pool)
                self._emote = emote
                self._active = True
                self._start_ms = elapsed_ms
                # Drive eye
                eye_ctrl._start_seq(emote.eye_seq, elapsed_ms)
                # Drive mouth
                mouth_ctrl._go(emote.mouth, 300.0, elapsed_ms)
                mouth_ctrl._holding = True
                mouth_ctrl._return_ms = elapsed_ms + emote.mouth_hold_ms
                return True
            else:
                self._next_emote_ms = elapsed_ms + random.uniform(15000, 35000)

        return False


# ---------------------------------------------------------------------------
# Persistent avatar window
# ---------------------------------------------------------------------------

class AvatarWindow:
    """Long-lived pygame avatar window.

    Call :meth:`run_forever` from the **main thread** (required on macOS).
    Feed it work via :meth:`play` (thread-safe) and shut it down with
    :meth:`request_close` (thread-safe).
    """

    def __init__(self, *, oneshot: bool = False) -> None:
        self._oneshot: bool = oneshot

        pygame.init()
        self._screen: pygame.Surface = pygame.display.set_mode(
            (WINDOW_WIDTH, WINDOW_HEIGHT),
        )
        pygame.display.set_caption("Avatar Demo")
        self._clock: pygame.time.Clock = pygame.time.Clock()

        face_width: int = 530
        mouth_max_w: int = int(face_width * MOUTH_WIDTH_RATIO)
        mouth_max_h: int = int(face_width * MOUTH_HEIGHT_RATIO)
        eye_max_w: int = int(face_width * EYE_WIDTH_RATIO)
        eye_max_h: int = int(face_width * EYE_HEIGHT_RATIO)

        self._face: pygame.Surface | None = _load_face(face_width)
        self._viseme_images: dict[int, pygame.Surface] = _load_visemes(
            mouth_max_w, mouth_max_h,
        )
        self._eye_images: dict[int, pygame.Surface] = _load_eyes(
            eye_max_w, eye_max_h,
        )
        self._idle_mouth_images: dict[str, pygame.Surface] = _load_idle_mouths(
            mouth_max_w, mouth_max_h,
        )

        if not self._face or not self._viseme_images:
            logger.info("[AVT] No assets found — cannot render avatar")
            self._ready = False
            return
        self._ready = True

        if not self._eye_images:
            logger.warning("[AVT] No eye assets found — rendering without eyes")
        else:
            logger.info("[AVT] Loaded %d eye frames", len(self._eye_images))

        face_x: int = (WINDOW_WIDTH - self._face.get_width()) // 2
        face_y: int = 60
        self._face_pos = (face_x, face_y)
        self._mouth_cx: int = face_x + self._face.get_width() // 2
        self._mouth_cy: int = face_y + int(
            self._face.get_height() * MOUTH_Y_RATIO,
        )
        self._eye_cx: int = face_x + self._face.get_width() // 2
        self._eye_cy: int = face_y + int(
            self._face.get_height() * EYE_Y_RATIO,
        )

        if self._idle_mouth_images:
            logger.info("[AVT] Loaded %d idle mouth sprites", len(self._idle_mouth_images))

        pygame.mixer.init(frequency=16000, size=-16, channels=1)
        self._font: pygame.font.Font = pygame.font.SysFont("monospace", 16)
        self._eye_ctrl: EyeController = EyeController()
        self._mouth_ctrl: MouthController = MouthController()
        self._emote_ctrl: EmoteController = EmoteController()

        # Playback state
        self._visemes: list[VisemeEvent] = []
        self._audio_start_ms: float = 0.0
        self._playing: bool = False
        self._status_text: str = "Listening..."
        self._sound: pygame.mixer.Sound | None = None

        # Thread-safe communication
        self._play_queue: queue.Queue[PipelineResult] = queue.Queue()
        self._close_requested: bool = False

    @property
    def ready(self) -> bool:
        return self._ready

    # -- thread-safe API (called from background threads) ------------------

    def play(self, result: PipelineResult) -> None:
        """Enqueue a pipeline result to be played (thread-safe)."""
        self._play_queue.put(result)

    def request_close(self) -> None:
        """Signal the render loop to shut down (thread-safe)."""
        self._close_requested = True

    # -- main-thread only --------------------------------------------------

    def _start_playback(self, result: PipelineResult) -> None:
        """Begin playing a new result (must be called from main thread)."""
        self._visemes = result.tts.visemes
        self._status_text = result.response_text[:40]
        has_audio: bool = len(result.tts.audio_data) > 0
        if has_audio:
            self._sound = pygame.mixer.Sound(
                io.BytesIO(result.tts.audio_data),
            )
            self._sound.play()
        else:
            self._sound = None
        self._audio_start_ms = time.time() * 1000
        self._playing = True
        self._mouth_ctrl.notify_speaking()
        self._emote_ctrl.notify_speaking()
        logger.debug(
            "[AVT] Playing — %d visemes, audio=%s",
            len(self._visemes),
            "yes" if has_audio else "no",
        )

    def _resolve_mouth(self, name: str | None) -> pygame.Surface | None:
        """Map a mouth name to a surface. None -> sil viseme."""
        if name is None:
            return self._viseme_images.get(0)
        return self._idle_mouth_images.get(name)

    def _draw_idle_mouth(
        self, prev_name: str | None, cur_name: str | None, t: float,
    ) -> None:
        """Draw idle mouth with cross-fade between prev and current."""
        prev_surf = self._resolve_mouth(prev_name)
        cur_surf = self._resolve_mouth(cur_name)

        def _blit(surf: pygame.Surface, alpha: int = 255) -> None:
            mx = self._mouth_cx - surf.get_width() // 2
            my = self._mouth_cy - surf.get_height() // 2
            if alpha >= 255:
                self._screen.blit(surf, (mx, my))
            else:
                surf.set_alpha(alpha)
                self._screen.blit(surf, (mx, my))
                surf.set_alpha(255)

        if t >= 1.0 or prev_name == cur_name:
            if cur_surf:
                _blit(cur_surf)
        elif t >= 0.5:
            # Second half: current at full, previous fading out
            if cur_surf:
                _blit(cur_surf)
            if prev_surf and prev_surf is not cur_surf:
                _blit(prev_surf, int((1.0 - t) * 2 * 255))
        else:
            # First half: previous at full, current fading in
            if prev_surf:
                _blit(prev_surf)
            if cur_surf and cur_surf is not prev_surf:
                _blit(cur_surf, int(t * 2 * 255))

    def run_forever(self) -> None:
        """Main render loop — blocks until close is requested or window is closed.

        Must be called from the main thread on macOS.
        """
        if not self._ready:
            pygame.quit()
            return

        global_start_ms: float = time.time() * 1000
        running: bool = True

        while running:
            # -- events ----------------------------------------------------
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            if self._close_requested:
                running = False
                continue

            # -- consume queued playback requests --------------------------
            try:
                result = self._play_queue.get_nowait()
                self._start_playback(result)
            except queue.Empty:
                pass

            # -- timing ----------------------------------------------------
            now_ms: float = time.time() * 1000
            eye_elapsed_ms: float = now_ms - global_start_ms

            if self._playing:
                audio_elapsed_ms: float = now_ms - self._audio_start_ms
                active_viseme: int = _get_active_viseme(
                    self._visemes, audio_elapsed_ms,
                )
                # Check if playback finished
                audio_busy = (
                    self._sound is not None and pygame.mixer.get_busy()
                )
                if not audio_busy and audio_elapsed_ms > 500:
                    self._playing = False
                    active_viseme = 0  # return to silent mouth
                    self._mouth_ctrl.notify_idle(eye_elapsed_ms)
                    self._emote_ctrl.notify_idle(eye_elapsed_ms)
                    if self._oneshot:
                        running = False
            else:
                active_viseme = 0
                self._mouth_ctrl.notify_idle(eye_elapsed_ms)
                self._emote_ctrl.notify_idle(eye_elapsed_ms)

            # Coordinated emotes drive both eye + mouth when active
            emote_active = self._emote_ctrl.update(
                eye_elapsed_ms, self._eye_ctrl, self._mouth_ctrl,
                self._idle_mouth_images,
            )

            blend: _Blend = self._eye_ctrl.get_blend(eye_elapsed_ms)

            # -- draw ------------------------------------------------------
            self._screen.fill(BG_COLOR)
            self._screen.blit(self._face, self._face_pos)

            if self._eye_images:
                if blend.t >= 1.0 or blend.from_idx == blend.to_idx:
                    if blend.to_idx in self._eye_images:
                        _blit_eye(self._screen, self._eye_images[blend.to_idx],
                                  self._eye_cx, self._eye_cy, 255)
                elif blend.t >= 0.5:
                    if blend.to_idx in self._eye_images:
                        _blit_eye(self._screen, self._eye_images[blend.to_idx],
                                  self._eye_cx, self._eye_cy, 255)
                    if blend.from_idx in self._eye_images:
                        _blit_eye(self._screen, self._eye_images[blend.from_idx],
                                  self._eye_cx, self._eye_cy,
                                  int((1.0 - blend.t) * 2 * 255))
                else:
                    if blend.from_idx in self._eye_images:
                        _blit_eye(self._screen, self._eye_images[blend.from_idx],
                                  self._eye_cx, self._eye_cy, 255)
                    if blend.to_idx in self._eye_images:
                        _blit_eye(self._screen, self._eye_images[blend.to_idx],
                                  self._eye_cx, self._eye_cy,
                                  int(blend.t * 2 * 255))

            # -- mouth -----------------------------------------------------
            if self._playing:
                # Speech viseme
                if active_viseme in self._viseme_images:
                    mouth = self._viseme_images[active_viseme]
                    mx = self._mouth_cx - mouth.get_width() // 2
                    my = self._mouth_cy - mouth.get_height() // 2
                    self._screen.blit(mouth, (mx, my))
                mouth_label = (
                    VISEME_LABELS[active_viseme]
                    if active_viseme < len(VISEME_LABELS) else "?"
                )
            else:
                # Idle mouth animation
                idle_prev, idle_cur, idle_t = self._mouth_ctrl.get_idle_mouth(
                    eye_elapsed_ms, self._idle_mouth_images,
                )
                self._draw_idle_mouth(idle_prev, idle_cur, idle_t)
                mouth_label = idle_cur or "sil"

            # Status bar
            state: str = "Speaking" if self._playing else "Listening..."
            status: str = (
                f"{state} | Mouth:{mouth_label}"
                f" | Eye:{blend.to_idx:2d}({self._eye_ctrl.state_label})"
                f" | {self._status_text}"
            )
            self._screen.blit(
                self._font.render(status, True, (200, 200, 200)),
                (10, WINDOW_HEIGHT - 30),
            )

            pygame.display.flip()
            self._clock.tick(60)

        pygame.mixer.quit()
        pygame.quit()
        logger.debug("Avatar window closed")


# ---------------------------------------------------------------------------
# Main render entry point (one-shot, used by non-interactive modes)
# ---------------------------------------------------------------------------

def render_avatar(result: PipelineResult) -> None:
    """Open a pygame window, play audio, animate, then close."""
    window = AvatarWindow(oneshot=True)
    if not window.ready:
        return
    window.play(result)
    window.run_forever()


# ---------------------------------------------------------------------------
# Sprite test viewer  (--test-sprites)
# ---------------------------------------------------------------------------

def test_sprites() -> None:
    """Interactive sprite viewer: shows each eye and viseme overlaid on the face.

    Controls:
      Left / Right  — previous / next sprite
      E             — switch to eye sprites
      V             — switch to viseme sprites
      Space         — toggle auto-cycle (2 s per frame)
      Esc / Q       — quit
    """
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Sprite Test Viewer")
    clock = pygame.time.Clock()

    face_width: int = 530
    mouth_max_w = int(face_width * MOUTH_WIDTH_RATIO)
    mouth_max_h = int(face_width * MOUTH_HEIGHT_RATIO)
    eye_max_w = int(face_width * EYE_WIDTH_RATIO)
    eye_max_h = int(face_width * EYE_HEIGHT_RATIO)

    face = _load_face(face_width)
    viseme_images = _load_visemes(mouth_max_w, mouth_max_h)
    eye_images = _load_eyes(eye_max_w, eye_max_h)

    if not face:
        print("ERROR: avatar-base.png not found")
        pygame.quit()
        return

    # Also load raw (un-trimmed, un-scaled) eyes for debug info
    raw_eye_sizes: dict[int, tuple[int, int]] = {}
    eyes_dir = ASSETS_DIR / "eyes"
    if eyes_dir.exists():
        for path in sorted(eyes_dir.glob("eye-*.png")):
            try:
                idx = int(path.name.split("-")[1])
                raw = pygame.image.load(str(path)).convert_alpha()
                raw_eye_sizes[idx] = raw.get_size()
            except Exception:
                pass

    # Build a unified sprite list: (name, index, surface, kind)
    eye_list = [(f"eye-{i:02d}", i, eye_images[i], "eye") for i in sorted(eye_images)]
    vis_list = [
        (f"vis-{i:02d}-{VISEME_LABELS[i]}", i, viseme_images[i], "viseme")
        for i in sorted(viseme_images)
    ]

    sprites = eye_list  # start with eyes
    sprite_idx = 0
    auto_cycle = False
    last_cycle_ms: float = 0.0

    face_x = (WINDOW_WIDTH - face.get_width()) // 2
    face_y = 60
    mouth_cx = face_x + face.get_width() // 2
    mouth_cy = face_y + int(face.get_height() * MOUTH_Y_RATIO)
    eye_cx = face_x + face.get_width() // 2
    eye_cy = face_y + int(face.get_height() * EYE_Y_RATIO)

    font = pygame.font.SysFont("monospace", 15)
    font_big = pygame.font.SysFont("monospace", 18, bold=True)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_RIGHT:
                    sprite_idx = (sprite_idx + 1) % max(1, len(sprites))
                elif event.key == pygame.K_LEFT:
                    sprite_idx = (sprite_idx - 1) % max(1, len(sprites))
                elif event.key == pygame.K_e:
                    sprites = eye_list
                    sprite_idx = 0
                elif event.key == pygame.K_v:
                    sprites = vis_list
                    sprite_idx = 0
                elif event.key == pygame.K_SPACE:
                    auto_cycle = not auto_cycle
                    last_cycle_ms = time.time() * 1000

        now_ms = time.time() * 1000
        if auto_cycle and sprites and now_ms - last_cycle_ms > 2000:
            sprite_idx = (sprite_idx + 1) % len(sprites)
            last_cycle_ms = now_ms

        screen.fill(BG_COLOR)
        screen.blit(face, (face_x, face_y))

        if sprites:
            name, idx, surf, kind = sprites[sprite_idx]
            if kind == "eye":
                cx, cy = eye_cx, eye_cy
            else:
                cx, cy = mouth_cx, mouth_cy

            x = cx - surf.get_width() // 2
            y = cy - surf.get_height() // 2
            screen.blit(surf, (x, y))

            # Draw crosshair at centre point
            pygame.draw.line(screen, (255, 0, 0, 120), (cx - 12, cy), (cx + 12, cy), 1)
            pygame.draw.line(screen, (255, 0, 0, 120), (cx, cy - 12), (cx, cy + 12), 1)

            # Info overlay
            raw_info = ""
            if kind == "eye" and idx in raw_eye_sizes:
                rw, rh = raw_eye_sizes[idx]
                raw_info = f"  raw={rw}x{rh}"
            lines = [
                f"{name}  [{sprite_idx + 1}/{len(sprites)}]  ({'EYES' if kind == 'eye' else 'VISEMES'})",
                f"scaled={surf.get_width()}x{surf.get_height()}{raw_info}",
                f"pos=({x},{y})  centre=({cx},{cy})",
                f"face={face.get_width()}x{face.get_height()}  eye_max={eye_max_w}x{eye_max_h}",
                "",
                "Left/Right=prev/next  E=eyes  V=visemes",
                f"Space=auto-cycle ({'ON' if auto_cycle else 'OFF'})  Esc=quit",
            ]
            for i, line in enumerate(lines):
                f = font_big if i == 0 else font
                color = (255, 255, 100) if i == 0 else (200, 200, 200)
                screen.blit(f.render(line, True, color), (10, WINDOW_HEIGHT - 140 + i * 19))
        else:
            screen.blit(font_big.render("No sprites loaded!", True, (255, 80, 80)), (10, WINDOW_HEIGHT - 40))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


# ---------------------------------------------------------------------------
# Animation test viewer  (--test-animations)
# ---------------------------------------------------------------------------

# Catalog of all browsable animations, grouped by category.
_EYE_SEQ_CATALOG: list[tuple[str, list[tuple[int, float, float]]]] = [
    ("blink", _SEQ_BLINK),
    ("slow-blink", _SEQ_SLOW_BLINK),
    ("double-blink", _SEQ_DOUBLE_BLINK),
    ("spin", _SEQ_SPIN),
    ("frantic", _SEQ_FRANTIC),
    ("crosseyed", _SEQ_CROSSEYED),
    ("shock-squint", _SEQ_SHOCK_SQUINT),
    ("confused", _SEQ_CONFUSED),
]

_IDLE_MOUTH_CATALOG: list[str] = [
    n for n in (
        "on-side", "stunt2", "big-smile", "wide-smile",
        "tongue-out", "tongue-out2",
        "laugh", "laugh2", "laugh3", "scream",
    )
]


def test_animations() -> None:
    """Interactive animation browser: play eye sequences, idle mouths, and emotes.

    Controls:
      1 / 2 / 3   — switch category (eyes / mouths / emotes)
      Left / Right — select animation
      Space        — play / replay selected animation
      A            — toggle auto-cycle
      Esc / Q      — quit

    Uses lightweight manual state instead of EyeController / MouthController
    so that no autonomous timers fire — only user-triggered animations play.
    """
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Animation Test Viewer")
    clock = pygame.time.Clock()

    face_width: int = 530
    mouth_max_w = int(face_width * MOUTH_WIDTH_RATIO)
    mouth_max_h = int(face_width * MOUTH_HEIGHT_RATIO)
    eye_max_w = int(face_width * EYE_WIDTH_RATIO)
    eye_max_h = int(face_width * EYE_HEIGHT_RATIO)

    face = _load_face(face_width)
    viseme_images = _load_visemes(mouth_max_w, mouth_max_h)
    eye_images = _load_eyes(eye_max_w, eye_max_h)
    idle_mouth_images = _load_idle_mouths(mouth_max_w, mouth_max_h)

    if not face:
        print("ERROR: avatar-base.png not found")
        pygame.quit()
        return

    face_x = (WINDOW_WIDTH - face.get_width()) // 2
    face_y = 60
    mouth_cx = face_x + face.get_width() // 2
    mouth_cy = face_y + int(face.get_height() * MOUTH_Y_RATIO)
    eye_cx = face_x + face.get_width() // 2
    eye_cy = face_y + int(face.get_height() * EYE_Y_RATIO)

    font = pygame.font.SysFont("monospace", 15)
    font_big = pygame.font.SysFont("monospace", 18, bold=True)

    # Build category lists
    cat_names = ["Eye Sequences", "Idle Mouths", "Emotes"]
    cat_items: list[list[str]] = [
        [name for name, _ in _EYE_SEQ_CATALOG],
        [n for n in _IDLE_MOUTH_CATALOG if n in idle_mouth_images],
        [e.name for e in _EMOTES if e.mouth in idle_mouth_images],
    ]

    cat_idx = 0
    item_idx = 0
    auto_cycle = False
    auto_timer_ms: float = 0.0
    AUTO_DELAY_MS: float = 4000.0

    # --- Manual eye sequence state (no autonomous timers) ---
    eye_seq: list[tuple[int, float, float]] = []
    eye_seq_step: int = 0
    eye_seq_step_start: float = 0.0
    eye_seq_active: bool = False
    # Current cross-fade
    eye_prev: int = 0
    eye_cur: int = 0
    eye_trans_start: float = 0.0
    eye_trans_dur: float = 0.0
    eye_in_trans: bool = False

    def _eye_go(idx: int, dur_ms: float, now: float) -> None:
        nonlocal eye_prev, eye_cur, eye_trans_start, eye_trans_dur, eye_in_trans
        if idx == eye_cur and not eye_in_trans:
            return
        # Snap to whichever is dominant
        eye_prev = eye_cur if _eye_t(now) >= 0.5 else eye_prev
        eye_cur = idx
        eye_trans_start = now
        eye_trans_dur = dur_ms
        eye_in_trans = True

    def _eye_t(now: float) -> float:
        nonlocal eye_in_trans
        if not eye_in_trans:
            return 1.0
        raw = (now - eye_trans_start) / max(1.0, eye_trans_dur)
        t = _smoothstep(min(1.0, raw))
        if t >= 1.0:
            eye_in_trans = False
        return t

    def _eye_start_seq(seq: list[tuple[int, float, float]], now: float) -> None:
        nonlocal eye_seq, eye_seq_step, eye_seq_step_start, eye_seq_active
        eye_seq = seq
        eye_seq_step = 0
        eye_seq_step_start = now
        eye_seq_active = True
        idx, trans_ms, _ = seq[0]
        _eye_go(idx, trans_ms, now)

    def _eye_advance(now: float) -> None:
        nonlocal eye_seq_step, eye_seq_step_start, eye_seq_active
        if not eye_seq_active:
            return
        _, trans_ms, hold_ms = eye_seq[eye_seq_step]
        if now - eye_seq_step_start >= trans_ms + hold_ms:
            eye_seq_step += 1
            if eye_seq_step >= len(eye_seq):
                eye_seq_active = False
                _eye_go(0, 200.0, now)  # return to neutral
                return
            nidx, ntrans, _ = eye_seq[eye_seq_step]
            _eye_go(nidx, ntrans, now)
            eye_seq_step_start = now

    # --- Manual mouth state (no autonomous timers) ---
    mouth_cur: str | None = None
    mouth_prev: str | None = None
    mouth_trans_start: float = 0.0
    mouth_trans_dur: float = 0.0
    mouth_in_trans: bool = False
    mouth_holding: bool = False
    mouth_return_ms: float = 0.0

    def _mouth_go(name: str | None, dur_ms: float, now: float) -> None:
        nonlocal mouth_prev, mouth_cur, mouth_trans_start, mouth_trans_dur, mouth_in_trans
        visible = mouth_cur if _mouth_t(now) >= 0.5 else mouth_prev
        if name == visible:
            return
        mouth_prev = visible
        mouth_cur = name
        mouth_trans_start = now
        mouth_trans_dur = dur_ms
        mouth_in_trans = True

    def _mouth_t(now: float) -> float:
        nonlocal mouth_in_trans
        if not mouth_in_trans:
            return 1.0
        raw = (now - mouth_trans_start) / max(1.0, mouth_trans_dur)
        t = _smoothstep(min(1.0, raw))
        if t >= 1.0:
            mouth_in_trans = False
        return t

    # --- Playback tracking ---
    playing = False
    play_start_ms: float = 0.0
    play_name: str = ""

    def _trigger(cat: int, idx: int, now: float) -> None:
        nonlocal playing, play_start_ms, play_name, mouth_holding, mouth_return_ms

        playing = True
        play_start_ms = now

        if cat == 0:  # eye sequence
            name, seq = _EYE_SEQ_CATALOG[idx]
            play_name = name
            _eye_start_seq(seq, now)

        elif cat == 1:  # idle mouth
            name = cat_items[1][idx]
            play_name = name
            _mouth_go(name, 300.0, now)
            mouth_holding = True
            mouth_return_ms = now + 2500.0

        elif cat == 2:  # emote
            emote = [e for e in _EMOTES if e.mouth in idle_mouth_images][idx]
            play_name = emote.name
            _eye_start_seq(emote.eye_seq, now)
            _mouth_go(emote.mouth, 300.0, now)
            mouth_holding = True
            mouth_return_ms = now + emote.mouth_hold_ms

    global_start_ms = time.time() * 1000
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_1:
                    cat_idx, item_idx = 0, 0
                elif event.key == pygame.K_2:
                    cat_idx, item_idx = 1, 0
                elif event.key == pygame.K_3:
                    cat_idx, item_idx = 2, 0
                elif event.key == pygame.K_RIGHT:
                    if cat_items[cat_idx]:
                        item_idx = (item_idx + 1) % len(cat_items[cat_idx])
                elif event.key == pygame.K_LEFT:
                    if cat_items[cat_idx]:
                        item_idx = (item_idx - 1) % len(cat_items[cat_idx])
                elif event.key == pygame.K_SPACE:
                    if cat_items[cat_idx]:
                        elapsed = time.time() * 1000 - global_start_ms
                        _trigger(cat_idx, item_idx, elapsed)
                elif event.key == pygame.K_a:
                    auto_cycle = not auto_cycle
                    auto_timer_ms = time.time() * 1000

        now_ms = time.time() * 1000
        elapsed_ms = now_ms - global_start_ms

        # Auto-cycle
        if auto_cycle and cat_items[cat_idx] and now_ms - auto_timer_ms > AUTO_DELAY_MS:
            _trigger(cat_idx, item_idx, elapsed_ms)
            item_idx = (item_idx + 1) % len(cat_items[cat_idx])
            auto_timer_ms = now_ms

        # Check if playing animation is done
        if playing and elapsed_ms - play_start_ms > 4000:
            playing = False

        # Advance eye sequence
        _eye_advance(elapsed_ms)

        # Mouth return-to-neutral
        if mouth_holding and elapsed_ms >= mouth_return_ms:
            mouth_holding = False
            _mouth_go(None, 350.0, elapsed_ms)

        # Compute blend values
        et = _eye_t(elapsed_ms)
        mt = _mouth_t(elapsed_ms)

        # -- draw --
        screen.fill(BG_COLOR)
        screen.blit(face, (face_x, face_y))

        # Eyes
        if eye_images:
            if et >= 1.0 or eye_prev == eye_cur:
                if eye_cur in eye_images:
                    _blit_eye(screen, eye_images[eye_cur], eye_cx, eye_cy, 255)
            elif et >= 0.5:
                if eye_cur in eye_images:
                    _blit_eye(screen, eye_images[eye_cur], eye_cx, eye_cy, 255)
                if eye_prev in eye_images:
                    _blit_eye(screen, eye_images[eye_prev], eye_cx, eye_cy,
                              int((1.0 - et) * 2 * 255))
            else:
                if eye_prev in eye_images:
                    _blit_eye(screen, eye_images[eye_prev], eye_cx, eye_cy, 255)
                if eye_cur in eye_images:
                    _blit_eye(screen, eye_images[eye_cur], eye_cx, eye_cy,
                              int(et * 2 * 255))

        # Mouth
        def _get_mouth_surf(name: str | None) -> pygame.Surface | None:
            if name is None:
                return viseme_images.get(0)
            return idle_mouth_images.get(name)

        cur_surf = _get_mouth_surf(mouth_cur)
        prev_surf = _get_mouth_surf(mouth_prev)

        def _blit_mouth(surf: pygame.Surface, alpha: int = 255) -> None:
            mx = mouth_cx - surf.get_width() // 2
            my = mouth_cy - surf.get_height() // 2
            if alpha >= 255:
                screen.blit(surf, (mx, my))
            else:
                surf.set_alpha(alpha)
                screen.blit(surf, (mx, my))
                surf.set_alpha(255)

        if mt >= 1.0 or mouth_prev == mouth_cur:
            if cur_surf:
                _blit_mouth(cur_surf)
        elif mt >= 0.5:
            if cur_surf:
                _blit_mouth(cur_surf)
            if prev_surf and prev_surf is not cur_surf:
                _blit_mouth(prev_surf, int((1.0 - mt) * 2 * 255))
        else:
            if prev_surf:
                _blit_mouth(prev_surf)
            if cur_surf and cur_surf is not prev_surf:
                _blit_mouth(cur_surf, int(mt * 2 * 255))

        # Info overlay
        cat_label = cat_names[cat_idx]
        items = cat_items[cat_idx]
        item_label = items[item_idx] if items else "(empty)"
        count = len(items)

        lines = [
            f"{cat_label}:  {item_label}  [{item_idx + 1}/{count}]",
            f"Playing: {play_name}" if playing else "Idle",
            f"Eye:{eye_cur:2d}  Mouth:{mouth_cur or 'sil'}",
            "",
            "1/2/3=category  Left/Right=select  Space=play",
            f"A=auto-cycle ({'ON' if auto_cycle else 'OFF'})  Esc=quit",
        ]
        for i, line in enumerate(lines):
            f = font_big if i == 0 else font
            color = (255, 255, 100) if i == 0 else (200, 200, 200)
            screen.blit(f.render(line, True, color), (10, WINDOW_HEIGHT - 130 + i * 19))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
