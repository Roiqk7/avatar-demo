"""Small utilities for avatar rendering."""

from __future__ import annotations

import logging
import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

logger: logging.Logger = logging.getLogger("backend.avatar")


def smoothstep(t: float) -> float:
    """Ease-in-out curve for natural-feeling transitions."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def scale_to_fit(surface: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    """Scale surface to fit within max_w x max_h, preserving aspect ratio."""
    ow, oh = surface.get_size()
    r = min(max_w / ow, max_h / oh)
    return pygame.transform.smoothscale(surface, (int(ow * r), int(oh * r)))


def scale_to_width(surface: pygame.Surface, target_w: int) -> pygame.Surface:
    """Scale to a fixed width, letting height vary proportionally."""
    ow, oh = surface.get_size()
    r = target_w / ow
    return pygame.transform.smoothscale(surface, (int(ow * r), int(oh * r)))


def trim_to_content(surf: pygame.Surface, pad: int = 8) -> pygame.Surface:
    """Remove transparent border pixels, keeping a small padding around content.

    Eye PNGs extracted from a sprite sheet can carry silent transparent rows from
    cell boundaries. Trimming ensures the visual eye content lands at eye_cy
    rather than the geometric centre of a padded canvas.

    Uses numpy (available in this project) to scan the alpha channel.
    Returns the original surface unchanged if anything goes wrong.
    """

    try:
        import numpy as np

        alpha = pygame.surfarray.pixels_alpha(surf)  # shape (W, H)
        col_has = np.any(alpha > 15, axis=1)  # (W,) — column has content
        row_has = np.any(alpha > 15, axis=0)  # (H,) — row    has content
        del alpha  # release the surface lock

        if not (col_has.any() and row_has.any()):
            return surf

        x_idx = np.where(col_has)[0]
        y_idx = np.where(row_has)[0]
        x0 = max(0, int(x_idx[0]) - pad)
        x1 = min(surf.get_width() - 1, int(x_idx[-1]) + pad)
        y0 = max(0, int(y_idx[0]) - pad)
        y1 = min(surf.get_height() - 1, int(y_idx[-1]) + pad)

        if x1 <= x0 or y1 <= y0:
            return surf

        return surf.subsurface(pygame.Rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)).copy()
    except Exception:
        return surf


def blit_centered(
    screen: pygame.Surface,
    surf: pygame.Surface,
    cx: int,
    cy: int,
    *,
    alpha: int = 255,
) -> None:
    """Blit a surface centered at (cx, cy) with optional per-surface alpha."""
    if alpha <= 0:
        return

    x = cx - surf.get_width() // 2
    y = cy - surf.get_height() // 2

    if alpha >= 255:
        screen.blit(surf, (x, y))
        return

    surf.set_alpha(alpha)
    screen.blit(surf, (x, y))
    surf.set_alpha(255)
