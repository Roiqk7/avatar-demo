"""Asset loading for the pygame avatar renderer."""

from __future__ import annotations

import logging
import os
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.rendering.avatar_config import ASSETS_DIR, IDLE_MOUTH_NAMES, VISEME_LABELS
from backend.rendering.avatar_utils import scale_to_fit

logger: logging.Logger = logging.getLogger("backend.avatar")


def load_face(face_width: int) -> pygame.Surface | None:
    """Load and scale the base avatar face image."""
    path: Path = ASSETS_DIR / "avatar-base.png"
    if not path.exists():
        return None
    return scale_to_fit(pygame.image.load(str(path)).convert_alpha(), face_width, face_width)


def load_visemes(max_w: int, max_h: int) -> dict[int, pygame.Surface]:
    """Load TTS viseme images, scaled to fit max_w x max_h."""
    images: dict[int, pygame.Surface] = {}
    for i, label in enumerate(VISEME_LABELS):
        path = ASSETS_DIR / "visemes" / f"viseme-{i:02d}-{label}.png"
        if path.exists():
            images[i] = scale_to_fit(
                pygame.image.load(str(path)).convert_alpha(),
                max_w,
                max_h,
            )
    return images


def load_idle_mouths(max_w: int, max_h: int) -> dict[str, pygame.Surface]:
    """Load non-viseme mouth sprites used during idle/emotes."""
    images: dict[str, pygame.Surface] = {}
    for name in IDLE_MOUTH_NAMES:
        path = ASSETS_DIR / "visemes" / f"viseme-{name}.png"
        if path.exists():
            images[name] = scale_to_fit(
                pygame.image.load(str(path)).convert_alpha(),
                max_w,
                max_h,
            )
    return images


def load_eyes(max_w: int, max_h: int) -> dict[int, pygame.Surface]:
    """Load eyes scaled to fit within max_w x max_h (preserving aspect ratio)."""
    images: dict[int, pygame.Surface] = {}
    eyes_dir: Path = ASSETS_DIR / "eyes"
    if not eyes_dir.exists():
        return images

    for path in sorted(eyes_dir.glob("eye-*.png")):
        try:
            idx = int(path.name.split("-")[1])
            raw = pygame.image.load(str(path)).convert_alpha()
            images[idx] = scale_to_fit(raw, max_w, max_h)
        except Exception as exc:
            logger.debug("Skipping eye %s: %s", path.name, exc)

    return images
