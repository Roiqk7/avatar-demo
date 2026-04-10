"""Avatar rendering configuration.

This module contains only static configuration and constants used by the
pygame avatar renderer (window sizing, asset locations, sprite labels, and
layout ratios).

Keeping these values centralized makes it easier to tweak visuals without
touching rendering logic.
"""

from __future__ import annotations

from pathlib import Path

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
