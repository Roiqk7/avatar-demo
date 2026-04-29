"""Avatar rendering configuration.

This module contains only static configuration and constants used by the
pygame avatar renderer (window sizing, asset locations, sprite labels, and
layout ratios).

Keeping these values centralized makes it easier to tweak visuals without
touching rendering logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

WINDOW_WIDTH: int = 600
WINDOW_HEIGHT: int = 700
BG_COLOR: tuple[int, int, int] = (40, 40, 50)

ASSETS_DIR: Path = Path(__file__).resolve().parents[2] / "assets"
"""Project `assets` directory (faces, shared visemes/eyes, optional packs)."""

DEFAULT_SPRITES_ROOT: Path = ASSETS_DIR
"""Default root for shared ``visemes/`` and ``eyes/`` (face bases live under ``assets/faces/``)."""

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

# Retired / disallowed idle mouth sprite stems (viseme-{name}.png may still exist on disk).
# The personality loader strips these from YAML pools so new avatars never pick them up.
DISALLOWED_IDLE_MOUTH_NAMES: frozenset[str] = frozenset({"cry", "cry2", "sad", "sad2", "stunt"})

# Additional non-TTS mouth sprites used during idle/emotes.
IDLE_MOUTH_NAMES: tuple[str, ...] = (
    "big-smile",
    "wide-smile",
    "on-side",
    "stunt2",
    "tongue-out",
    "tongue-out2",
    "laugh",
    "laugh2",
    "laugh3",
    "scream",
)

# Face-relative mouth placement and sizing.
MOUTH_WIDTH_RATIO: float = 0.55
MOUTH_HEIGHT_RATIO: float = 0.35
MOUTH_Y_RATIO: float = 0.72

# Eye overlay placement and sizing.
# Fine-tune these if the eye overlay doesn't land on the face's eye sockets.
EYE_Y_RATIO: float = 0.36  # fraction of face height from top → eye centre
EYE_WIDTH_RATIO: float = 0.72  # max eye width as fraction of face width
EYE_HEIGHT_RATIO: float = 0.45  # max eye height as fraction of face width


@dataclass(frozen=True, slots=True)
class FaceLayoutRatios:
    """Face-relative placement and max scale for shared eye/mouth sprites.

    Used by the pygame compositor; personalities with non-standard base art
    (e.g. hats, hair) can override subsets via YAML ``face_layout``.
    """

    mouth_width_ratio: float
    mouth_height_ratio: float
    mouth_y_ratio: float
    eye_y_ratio: float
    eye_width_ratio: float
    eye_height_ratio: float


def default_face_layout_ratios() -> FaceLayoutRatios:
    return FaceLayoutRatios(
        mouth_width_ratio=MOUTH_WIDTH_RATIO,
        mouth_height_ratio=MOUTH_HEIGHT_RATIO,
        mouth_y_ratio=MOUTH_Y_RATIO,
        eye_y_ratio=EYE_Y_RATIO,
        eye_width_ratio=EYE_WIDTH_RATIO,
        eye_height_ratio=EYE_HEIGHT_RATIO,
    )


def face_layout_ratios_from_mapping(mapping: dict[str, Any] | None) -> FaceLayoutRatios:
    """Merge optional YAML ``face_layout`` keys onto :func:`default_face_layout_ratios`."""
    base = default_face_layout_ratios()
    if not mapping:
        return base

    def pick(key: str, fallback: float) -> float:
        raw = mapping.get(key)
        if raw is None:
            return fallback
        return float(raw)

    return FaceLayoutRatios(
        mouth_width_ratio=pick("mouth_width_ratio", base.mouth_width_ratio),
        mouth_height_ratio=pick("mouth_height_ratio", base.mouth_height_ratio),
        mouth_y_ratio=pick("mouth_y_ratio", base.mouth_y_ratio),
        eye_y_ratio=pick("eye_y_ratio", base.eye_y_ratio),
        eye_width_ratio=pick("eye_width_ratio", base.eye_width_ratio),
        eye_height_ratio=pick("eye_height_ratio", base.eye_height_ratio),
    )
