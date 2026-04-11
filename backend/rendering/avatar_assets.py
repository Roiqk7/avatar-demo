"""Asset loading for the pygame avatar renderer."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.rendering.avatar_config import DEFAULT_SPRITES_ROOT, VISEME_LABELS
from backend.rendering.avatar_utils import scale_to_fit

logger: logging.Logger = logging.getLogger("backend.avatar")


def load_face(pack_root: Path, face_width: int, *, face_filename: str = "avatar-base.png") -> pygame.Surface | None:
    """Load and scale the base avatar face image from a sprite pack root."""
    path: Path = pack_root / face_filename
    if not path.exists():
        return None
    return scale_to_fit(pygame.image.load(str(path)).convert_alpha(), face_width, face_width)


def load_visemes(
    pack_root: Path,
    max_w: int,
    max_h: int,
    *,
    visemes_dir: str = "visemes",
    labels: tuple[str, ...] | None = None,
) -> dict[int, pygame.Surface]:
    """Load TTS viseme images, scaled to fit max_w x max_h."""
    lab: tuple[str, ...] = labels if labels is not None else VISEME_LABELS
    images: dict[int, pygame.Surface] = {}
    base = pack_root / visemes_dir
    for i, label in enumerate(lab):
        path = base / f"viseme-{i:02d}-{label}.png"
        if path.exists():
            images[i] = scale_to_fit(
                pygame.image.load(str(path)).convert_alpha(),
                max_w,
                max_h,
            )
    return images


def load_idle_mouths(
    pack_root: Path,
    names: Iterable[str],
    max_w: int,
    max_h: int,
    *,
    visemes_dir: str = "visemes",
) -> dict[str, pygame.Surface]:
    """Load non-viseme mouth sprites used during idle/emotes."""
    images: dict[str, pygame.Surface] = {}
    base = pack_root / visemes_dir
    for name in names:
        path = base / f"viseme-{name}.png"
        if path.exists():
            images[name] = scale_to_fit(
                pygame.image.load(str(path)).convert_alpha(),
                max_w,
                max_h,
            )
    return images


def load_eyes(
    pack_root: Path,
    max_w: int,
    max_h: int,
    *,
    eyes_dir: str = "eyes",
) -> dict[int, pygame.Surface]:
    """Load eyes scaled to fit within max_w x max_h (preserving aspect ratio)."""
    images: dict[int, pygame.Surface] = {}
    eyes_path: Path = pack_root / eyes_dir
    if not eyes_path.exists():
        return images

    for path in sorted(eyes_path.glob("eye-*.png")):
        try:
            idx = int(path.name.split("-")[1])
            raw = pygame.image.load(str(path)).convert_alpha()
            images[idx] = scale_to_fit(raw, max_w, max_h)
        except Exception as exc:
            logger.debug("Skipping eye %s: %s", path.name, exc)

    return images


def default_sprites_root() -> Path:
    """Shared sprite root (visemes + eyes) for tests and tooling."""
    return DEFAULT_SPRITES_ROOT
