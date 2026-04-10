import io
import logging
import os
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
    (3, 75, 35), (4, 55, 55), (3, 55, 35), (0, 95, 0),
]
_SEQ_SLOW_BLINK: list[tuple[int, float, float]] = [
    (3, 115, 60), (4, 90, 90), (12, 80, 520), (3, 85, 50), (0, 140, 0),
]
_SEQ_DOUBLE_BLINK: list[tuple[int, float, float]] = [
    (3, 65, 28), (4, 50, 45), (3, 50, 28), (0, 60, 190),
    (3, 65, 28), (4, 50, 45), (3, 50, 28), (0, 100, 0),
]

_SEQ_SPIN: list[tuple[int, float, float]] = [
    (8, 115, 75), (10, 105, 65), (1, 105, 65), (11, 105, 65), (0, 155, 0),
]
_SEQ_FRANTIC: list[tuple[int, float, float]] = [
    (2, 75, 55), (14, 75, 55), (2, 75, 55), (14, 75, 55), (0, 160, 0),
]
_SEQ_CROSSEYED: list[tuple[int, float, float]] = [
    (13, 185, 360), (4, 60, 65), (13, 125, 310), (0, 210, 0),
]
_SEQ_SHOCK_SQUINT: list[tuple[int, float, float]] = [
    (2, 125, 390), (9, 225, 600), (0, 195, 0),
]
_SEQ_CONFUSED: list[tuple[int, float, float]] = [
    (10, 165, 200), (1, 145, 200), (5, 185, 420), (0, 185, 0),
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
            self._go(0, 220.0, elapsed_ms)

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
                self._go(random.choice([1, 8, 10, 11]), 145.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(170, 370)
                self._next_micro_ms = elapsed_ms + random.uniform(2800, 5800)

            elif elapsed_ms >= self._next_glance_ms:
                self._go(random.choice([1, 8, 11]), 240.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(700, 1500)
                self._next_glance_ms = elapsed_ms + random.uniform(6500, 15000)

            elif elapsed_ms >= self._next_expr_ms:
                self._go(random.choice([9, 12, 5, 7]), 280.0, elapsed_ms)
                self._looking_away = True
                self._look_return_ms = elapsed_ms + random.uniform(1000, 2600)
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
# Main render entry point
# ---------------------------------------------------------------------------

def render_avatar(result: PipelineResult) -> None:
    """Open a pygame window, play audio, and animate mouth and eyes in sync."""
    pygame.init()
    screen: pygame.Surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Avatar Demo")
    clock: pygame.time.Clock = pygame.time.Clock()

    # Fill most of the window width (600 px) with ~35 px margins each side.
    face_width: int = 530
    mouth_max_w: int = int(face_width * MOUTH_WIDTH_RATIO)
    mouth_max_h: int = int(face_width * MOUTH_HEIGHT_RATIO)
    eye_max_w: int = int(face_width * EYE_WIDTH_RATIO)
    eye_max_h: int = int(face_width * EYE_HEIGHT_RATIO)

    face: pygame.Surface | None = _load_face(face_width)
    viseme_images: dict[int, pygame.Surface] = _load_visemes(mouth_max_w, mouth_max_h)
    eye_images: dict[int, pygame.Surface] = _load_eyes(eye_max_w, eye_max_h)

    if not face or not viseme_images:
        logger.info("[AVT] No assets found — cannot render avatar")
        pygame.quit()
        return

    if not eye_images:
        logger.warning("[AVT] No eye assets found — rendering without eyes")
    else:
        logger.info("[AVT] Loaded %d eye frames", len(eye_images))

    face_x: int = (WINDOW_WIDTH - face.get_width()) // 2
    face_y: int = 60
    mouth_cx: int = face_x + face.get_width() // 2
    mouth_cy: int = face_y + int(face.get_height() * MOUTH_Y_RATIO)
    eye_cx: int = face_x + face.get_width() // 2
    eye_cy: int = face_y + int(face.get_height() * EYE_Y_RATIO)

    logger.info("[AVT] Rendering with %d viseme events", len(result.tts.visemes))

    has_audio: bool = len(result.tts.audio_data) > 0
    sound: pygame.mixer.Sound | None = None
    if has_audio:
        pygame.mixer.init(frequency=16000, size=-16, channels=1)
        sound = pygame.mixer.Sound(io.BytesIO(result.tts.audio_data))

    font: pygame.font.Font = pygame.font.SysFont("monospace", 16)
    eye_ctrl: EyeController = EyeController()

    if sound:
        sound.play()
    start_time_ms: float = time.time() * 1000

    running: bool = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        elapsed_ms: float = time.time() * 1000 - start_time_ms
        active_viseme: int = _get_active_viseme(result.tts.visemes, elapsed_ms)
        blend: _Blend = eye_ctrl.get_blend(elapsed_ms)

        screen.fill(BG_COLOR)
        screen.blit(face, (face_x, face_y))

        # Cross-fade between eye states
        if eye_images:
            if blend.t < 0.98 and blend.from_idx in eye_images:
                _blit_eye(screen, eye_images[blend.from_idx], eye_cx, eye_cy,
                          int((1.0 - blend.t) * 255))
            if blend.to_idx in eye_images:
                _blit_eye(screen, eye_images[blend.to_idx], eye_cx, eye_cy,
                          int(blend.t * 255))

        if active_viseme in viseme_images:
            mouth: pygame.Surface = viseme_images[active_viseme]
            mx: int = mouth_cx - mouth.get_width() // 2
            my: int = mouth_cy - mouth.get_height() // 2
            screen.blit(mouth, (mx, my))

        viseme_label: str = VISEME_LABELS[active_viseme] if active_viseme < len(VISEME_LABELS) else "?"
        status: str = (
            f"Viseme:{active_viseme:2d}({viseme_label}) | Eye:{blend.to_idx:2d}({eye_ctrl.state_label})"
            f" | {elapsed_ms / 1000:.1f}s | \"{result.response_text[:26]}\""
        )
        screen.blit(font.render(status, True, (200, 200, 200)), (10, WINDOW_HEIGHT - 30))

        pygame.display.flip()
        clock.tick(60)

        audio_busy: bool = has_audio and pygame.mixer.get_busy()
        if not audio_busy and elapsed_ms > 500:
            time.sleep(0.5)
            running = False

    if has_audio:
        pygame.mixer.quit()
    pygame.quit()
    logger.debug("Avatar window closed")


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
