"""Public avatar rendering API (compatibility façade).

The original implementation lived entirely in this module. For maintainability,
the implementation is now decomposed across several focused modules, while this
file keeps import paths stable:

- `backend.rendering.avatar_window`: main pygame window + render loop
- `backend.rendering.avatar_assets`: asset loading
- `backend.rendering.avatar_controllers`: eye/mouth/emote state machines
- `backend.rendering.avatar_test_sprites`: interactive sprite viewer
- `backend.rendering.avatar_test_animations`: interactive animation viewer
- `backend.rendering.avatar_test_personalities`: personality + voice demo (Azure TTS)

This façade uses lazy attribute access so importing `backend.rendering.avatar`
does not require `pygame` unless you actually access the rendering/test entrypoints.
"""

from __future__ import annotations

import os
from typing import Any

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

__all__ = [
    "AvatarWindow",
    "render_avatar",
    "test_animations",
    "test_personalities",
    "test_sprites",
]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name == "AvatarWindow":
        from backend.rendering.avatar_window import AvatarWindow

        return AvatarWindow
    if name == "render_avatar":
        from backend.rendering.avatar_window import render_avatar

        return render_avatar
    if name == "test_sprites":
        from backend.rendering.avatar_test_sprites import test_sprites

        return test_sprites
    if name == "test_animations":
        from backend.rendering.avatar_test_animations import test_animations

        return test_animations
    if name == "test_personalities":
        from backend.rendering.avatar_test_personalities import test_personalities

        return test_personalities
    raise AttributeError(name)
