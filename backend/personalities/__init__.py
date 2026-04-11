"""Avatar personalities (YAML-driven look, motion, voice, LLM prompt)."""

from __future__ import annotations

from backend.personalities.loader import (
    DEFAULT_PERSONALITY_ID,
    list_personality_ids,
    load_personality,
)
from backend.personalities.models import AssetPaths, Personality

__all__ = [
    "AssetPaths",
    "DEFAULT_PERSONALITY_ID",
    "Personality",
    "list_personality_ids",
    "load_personality",
]
