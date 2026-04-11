"""Runtime personality model (loaded from YAML)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.rendering.animation_config import (
    EmoteTimingConfig,
    EyeAnimationConfig,
    MouthIdlePools,
    MouthTimingConfig,
)
from backend.rendering.avatar_config import FaceLayoutRatios, default_face_layout_ratios
from backend.rendering.emote_catalog import Emote


@dataclass(frozen=True, slots=True)
class AssetPaths:
    """Sprite locations: face in `face_root`; shared visemes/eyes under `sprites_root`."""

    face_root: Path
    sprites_root: Path
    face_filename: str = "avatar-base.png"
    visemes_dir: str = "visemes"
    eyes_dir: str = "eyes"


@dataclass(frozen=True, slots=True)
class Personality:
    """A selectable avatar persona: look, motion, voice, and LLM instructions."""

    id: str
    display_name: str
    window_title: str
    azure_voice_name: str
    llm_system_prompt: str  # body only; main wraps with shared LLM header/footer
    assets: AssetPaths
    idle_mouth_pools: MouthIdlePools
    eye_config: EyeAnimationConfig
    mouth_timing: MouthTimingConfig
    emotes: tuple[Emote, ...]
    emote_timing: EmoteTimingConfig
    mouth_idle_enabled: bool = True
    """When False, idle mouth stays neutral (sil) — no subtle/happy/goofy/dramatic holds."""
    face_layout: FaceLayoutRatios = field(default_factory=default_face_layout_ratios)
    """Eye/mouth scale and anchor ratios for this face art (defaults match Peter/Ted bases)."""
    viseme_labels: tuple[str, ...] = field(default_factory=tuple)
    """If empty, renderer uses global :data:`backend.rendering.avatar_config.VISEME_LABELS`."""

    @property
    def effective_viseme_labels(self) -> tuple[str, ...]:
        from backend.rendering.avatar_config import VISEME_LABELS

        return self.viseme_labels if self.viseme_labels else VISEME_LABELS

    def all_idle_mouth_asset_names(self) -> tuple[str, ...]:
        """Union of idle pool sprite ids and emote mouths (for loading PNGs)."""
        s: set[str] = set()
        p = self.idle_mouth_pools
        for pool in (p.subtle, p.happy, p.goofy, p.dramatic):
            s.update(pool)
        for e in self.emotes:
            s.add(e.mouth)
        return tuple(sorted(s))
