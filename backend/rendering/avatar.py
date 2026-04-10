import io
import logging
import os
import time
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.models import PipelineResult, VisemeEvent

logger: logging.Logger = logging.getLogger("backend.avatar")

WINDOW_WIDTH: int = 600
WINDOW_HEIGHT: int = 700
BG_COLOR: tuple[int, int, int] = (40, 40, 50)

ASSETS_DIR: Path = Path(__file__).parent.parent / "assets"
VISEME_COUNT: int = 22

FACE_SCALE: float = 1.4
MOUTH_WIDTH_RATIO: float = 0.55
MOUTH_HEIGHT_RATIO: float = 0.35
MOUTH_Y_RATIO: float = 0.72


def _scale_to_fit(surface: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    """Scale a surface to fit within max_w x max_h, preserving aspect ratio."""
    orig_w: int = surface.get_width()
    orig_h: int = surface.get_height()
    ratio: float = min(max_w / orig_w, max_h / orig_h)
    new_size: tuple[int, int] = (int(orig_w * ratio), int(orig_h * ratio))
    return pygame.transform.smoothscale(surface, new_size)


def _load_face(face_width: int) -> pygame.Surface | None:
    """Load and scale the base face image."""
    path: Path = ASSETS_DIR / "face-base.png"
    if not path.exists():
        return None
    img: pygame.Surface = pygame.image.load(str(path)).convert_alpha()
    return _scale_to_fit(img, face_width, face_width)


def _load_visemes(max_w: int, max_h: int) -> dict[int, pygame.Surface]:
    """Load all viseme mouth images, scaled to fit within max_w x max_h."""
    images: dict[int, pygame.Surface] = {}
    viseme_dir: Path = ASSETS_DIR / "visemes"
    for i in range(VISEME_COUNT):
        path: Path = viseme_dir / f"viseme-{i:02d}.png"
        if path.exists():
            img: pygame.Surface = pygame.image.load(str(path)).convert_alpha()
            images[i] = _scale_to_fit(img, max_w, max_h)
    return images


def _get_active_viseme(visemes: list[VisemeEvent], elapsed_ms: float) -> int:
    """Find the active viseme ID for the given elapsed time."""
    active_id: int = 0
    for v in visemes:
        if v.offset_ms <= elapsed_ms:
            active_id = v.id
        else:
            break
    return active_id


def render_avatar(result: PipelineResult) -> None:
    """Open a pygame window, play audio, and animate mouth in sync with visemes."""
    pygame.init()
    screen: pygame.Surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Avatar Demo")
    clock: pygame.time.Clock = pygame.time.Clock()

    face_width: int = int(345 * FACE_SCALE)
    mouth_max_w: int = int(face_width * MOUTH_WIDTH_RATIO)
    mouth_max_h: int = int(face_width * MOUTH_HEIGHT_RATIO)

    face: pygame.Surface | None = _load_face(face_width)
    viseme_images: dict[int, pygame.Surface] = _load_visemes(mouth_max_w, mouth_max_h)

    if not face or not viseme_images:
        logger.info("[AVT] No assets found — cannot render avatar")
        pygame.quit()
        return

    face_x: int = (WINDOW_WIDTH - face.get_width()) // 2
    face_y: int = 60

    mouth_cx: int = face_x + face.get_width() // 2
    mouth_cy: int = face_y + int(face.get_height() * MOUTH_Y_RATIO)

    logger.info("[AVT] Rendering with %d viseme events", len(result.tts.visemes))

    has_audio: bool = len(result.tts.audio_data) > 0
    sound: pygame.mixer.Sound | None = None
    if has_audio:
        pygame.mixer.init(frequency=16000, size=-16, channels=1)
        sound = pygame.mixer.Sound(io.BytesIO(result.tts.audio_data))

    font: pygame.font.Font = pygame.font.SysFont("monospace", 16)

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

        screen.fill(BG_COLOR)
        screen.blit(face, (face_x, face_y))

        if active_viseme in viseme_images:
            mouth: pygame.Surface = viseme_images[active_viseme]
            mx: int = mouth_cx - mouth.get_width() // 2
            my: int = mouth_cy - mouth.get_height() // 2
            screen.blit(mouth, (mx, my))

        status: str = f'Viseme: {active_viseme:2d} | Time: {elapsed_ms / 1000:.1f}s | "{result.response_text[:40]}"'
        status_surface: pygame.Surface = font.render(status, True, (200, 200, 200))
        screen.blit(status_surface, (10, WINDOW_HEIGHT - 30))

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
