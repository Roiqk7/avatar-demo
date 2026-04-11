"""Load personality definitions from YAML files in this package.

Quick checklist for a new client avatar (copy ``_template.yaml``)::

    id, display_name, window_title (optional)
    voice.azure_voice_name
    llm.system_prompt
    assets.face  — path under assets/, e.g. faces/my_base.png

Motion (pick one style)::

    animation.vibe: calm | balanced | playful | wild

    - calm     → preset boring, eye_preset stoic, mouth_idle_enabled false by default
    - balanced → preset moderate (eyes follow preset)
    - playful  → preset hyperactive
    - wild     → preset extreme

Explicit ``animation.preset``, ``eye_preset``, ``mouth_idle_enabled``, and
``animation.eyes`` always override what ``vibe`` would set.

Idle mouths (optional)::

    idle_mouth_profile: none | minimal | standard | full

Fills the four tiers from curated defaults; any ``idle_mouths.<tier>`` list in
YAML replaces that tier (use ``[]`` to clear).

Or omit ``idle_mouth_profile`` and set ``idle_mouths`` manually per tier.

**Disallowed idle mouth stems** (never reference in YAML; loader strips them if
present) — see :data:`backend.rendering.avatar_config.DISALLOWED_IDLE_MOUTH_NAMES`.

Eye tweaks (under ``animation.eyes``)::

    blink.initial_ms / after_ms  — [min, max] ms
    micro_glance, long_glance, expression_glance, goofy_sequences — bool
    exclude_eye_indices — e.g. [11] to forbid that eye sprite for glances, goofy sequences,
      and emote eye tracks
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from backend.rendering.animation_config import (
    MouthIdlePools,
    build_eye_config,
    resolve_emote_timing_preset,
    resolve_mouth_timing_preset,
)
from backend.rendering.avatar_config import (
    ASSETS_DIR,
    DISALLOWED_IDLE_MOUTH_NAMES,
    face_layout_ratios_from_mapping,
)
from backend.rendering.emote_catalog import resolve_emotes

from backend.personalities.models import AssetPaths, Personality

logger: logging.Logger = logging.getLogger("backend.personalities")

PERSONALITIES_DIR: Path = Path(__file__).resolve().parent
DEFAULT_PERSONALITY_ID: str = "peter"

_VIBE_DEFAULTS: dict[str, dict[str, str]] = {
    "calm": {"preset": "boring", "eye_preset": "stoic"},
    "balanced": {"preset": "moderate"},
    "playful": {"preset": "hyperactive"},
    "wild": {"preset": "extreme"},
}

_IDLE_MOUTH_PROFILES: dict[str, MouthIdlePools] = {
    "none": MouthIdlePools((), (), (), ()),
    "minimal": MouthIdlePools(
        subtle=("stunt2",),
        happy=("big-smile", "wide-smile"),
        goofy=(),
        dramatic=(),
    ),
    "standard": MouthIdlePools(
        subtle=("stunt2",),
        happy=("big-smile", "wide-smile"),
        goofy=("laugh", "laugh2"),
        dramatic=(),
    ),
    "full": MouthIdlePools(
        subtle=("on-side", "stunt2"),
        happy=("big-smile", "wide-smile"),
        goofy=("tongue-out", "tongue-out2", "laugh", "laugh2", "laugh3"),
        dramatic=("scream",),
    ),
}


def _under_assets(raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    return ASSETS_DIR / raw


def _merge_animation_vibe(data: dict[str, Any], personality_key: str) -> None:
    raw_anim = data.get("animation")
    anim: dict[str, Any] = dict(raw_anim) if isinstance(raw_anim, dict) else {}
    vibe = str(anim.get("vibe") or "").strip().lower()
    if vibe:
        defaults = _VIBE_DEFAULTS.get(vibe)
        if defaults is None:
            known = ", ".join(sorted(_VIBE_DEFAULTS))
            raise ValueError(f"personality {personality_key}: unknown animation.vibe {vibe!r}; use one of: {known}")
        for k, v in defaults.items():
            if k not in anim:
                anim[k] = v
        if vibe == "calm" and "mouth_idle_enabled" not in data:
            data["mouth_idle_enabled"] = False
    data["animation"] = anim


def _strip_disallowed_idle_mouths(pools: MouthIdlePools, personality_key: str) -> MouthIdlePools:
    def filt(names: tuple[str, ...]) -> tuple[str, ...]:
        kept: list[str] = []
        stripped: list[str] = []
        for n in names:
            if n in DISALLOWED_IDLE_MOUTH_NAMES:
                stripped.append(n)
            else:
                kept.append(n)
        if stripped:
            logger.warning(
                "personality %s: removed disallowed idle mouth sprite(s) from YAML: %s",
                personality_key,
                ", ".join(sorted(set(stripped))),
            )
        return tuple(kept)

    return MouthIdlePools(
        subtle=filt(pools.subtle),
        happy=filt(pools.happy),
        goofy=filt(pools.goofy),
        dramatic=filt(pools.dramatic),
    )


def _mouth_pools(data: dict[str, Any], personality_key: str) -> MouthIdlePools:
    profile_key = str(data.get("idle_mouth_profile") or "").strip().lower()
    im = data.get("idle_mouths")
    if profile_key:
        base = _IDLE_MOUTH_PROFILES.get(profile_key)
        if base is None:
            known = ", ".join(sorted(_IDLE_MOUTH_PROFILES))
            raise ValueError(
                f"personality {personality_key}: unknown idle_mouth_profile {profile_key!r}; use one of: {known}",
            )
        tiers: dict[str, list[str]] = {
            "subtle": list(base.subtle),
            "happy": list(base.happy),
            "goofy": list(base.goofy),
            "dramatic": list(base.dramatic),
        }
        if isinstance(im, dict):
            for tier in tiers:
                if tier in im:
                    raw = im[tier]
                    tiers[tier] = list(raw) if raw else []
        pools = MouthIdlePools(
            subtle=tuple(tiers["subtle"]),
            happy=tuple(tiers["happy"]),
            goofy=tuple(tiers["goofy"]),
            dramatic=tuple(tiers["dramatic"]),
        )
    else:
        im = im or {}
        if not isinstance(im, dict):
            raise ValueError(f"personality {personality_key}: `idle_mouths` must be a mapping")
        pools = MouthIdlePools(
            subtle=tuple(im.get("subtle") or ()),
            happy=tuple(im.get("happy") or ()),
            goofy=tuple(im.get("goofy") or ()),
            dramatic=tuple(im.get("dramatic") or ()),
        )
    return _strip_disallowed_idle_mouths(pools, personality_key)


def _resolve_assets(assets: dict, *, personality_key: str) -> AssetPaths:
    """Resolve paths.

    - ``pack``: single folder under ``assets/`` containing face + visemes + eyes (full custom set).
    - Otherwise ``face``: path under ``assets/`` to the base face image (e.g. ``faces/regular_emoji_base.png``).
      Shared ``visemes/`` and ``eyes/`` live at ``assets/`` unless ``sprites_root`` is set.
    """
    pack = assets.get("pack")
    face_rel = assets.get("face")

    vis_dir = str(assets.get("visemes_dir") or "visemes")
    eyes_dir = str(assets.get("eyes_dir") or "eyes")
    spr = assets.get("sprites_root")
    if spr is None or str(spr).strip() in (".", ""):
        sprites_root = ASSETS_DIR
    else:
        sprites_root = _under_assets(str(spr).strip())

    if pack is not None:
        root = _under_assets(str(pack).strip())
        ff = assets.get("face_filename")
        if ff is not None:
            face_fn = str(ff)
        elif face_rel is not None and "/" not in str(face_rel) and "\\" not in str(face_rel):
            face_fn = str(face_rel).strip()
        else:
            face_fn = "avatar-base.png"
        return AssetPaths(
            face_root=root,
            sprites_root=root,
            face_filename=face_fn,
            visemes_dir=vis_dir,
            eyes_dir=eyes_dir,
        )

    if not face_rel or not str(face_rel).strip():
        raise ValueError(
            f"personality {personality_key}: set `assets.face` to a path under assets/, "
            "e.g. `faces/regular_emoji_base.png`, or use `assets.pack` for a single-folder layout.",
        )

    face_path = _under_assets(str(face_rel).strip())
    try:
        face_path.relative_to(ASSETS_DIR.resolve())
    except ValueError as exc:
        raise ValueError(
            f"personality {personality_key}: `assets.face` must be under {ASSETS_DIR}",
        ) from exc

    return AssetPaths(
        face_root=face_path.parent,
        face_filename=face_path.name,
        sprites_root=sprites_root,
        visemes_dir=vis_dir,
        eyes_dir=eyes_dir,
    )


def load_personality(person_id: str) -> Personality:
    """Load ``<person_id>.yaml`` from the personalities directory."""
    key = person_id.strip().lower()
    path = PERSONALITIES_DIR / f"{key}.yaml"
    if not path.is_file():
        available = list_personality_ids()
        choices = ", ".join(available) if available else "(none found)"
        raise FileNotFoundError(f"Unknown personality {person_id!r}. Available: {choices}")

    raw_text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid personality file {path}: expected a mapping at top level")

    pid = str(data.get("id", key)).strip().lower()
    if pid != key:
        logger.warning("Personality file %s: `id` %r does not match filename; using filename key %r", path.name, pid, key)

    _merge_animation_vibe(data, key)

    display_name = str(data.get("display_name") or key.title())
    window_title = str(data.get("window_title") or f"Avatar Demo — {display_name}")

    voice = data.get("voice") or {}
    llm = data.get("llm") or {}
    assets = data.get("assets") or {}
    anim = data.get("animation") or {}
    preset = str(anim.get("preset") or "hyperactive").strip().lower()

    mouth_idle_enabled = data.get("mouth_idle_enabled")
    if mouth_idle_enabled is None:
        mouth_idle_enabled = True
    elif not isinstance(mouth_idle_enabled, bool):
        raise ValueError(f"personality {key}: `mouth_idle_enabled` must be a boolean")

    emote_ids = data.get("emotes")
    if emote_ids is None:
        emote_list: list[str] = []
    elif not isinstance(emote_ids, list):
        raise ValueError(f"personality {key}: `emotes` must be a list of strings")
    else:
        emote_list = [str(x) for x in emote_ids]

    personality = Personality(
        id=key,
        display_name=display_name,
        window_title=window_title,
        azure_voice_name=str(voice.get("azure_voice_name") or "").strip(),
        llm_system_prompt=str(llm.get("system_prompt") or "").strip(),
        assets=_resolve_assets(assets, personality_key=key),
        idle_mouth_pools=_mouth_pools(data, key),
        eye_config=build_eye_config(anim),
        mouth_timing=resolve_mouth_timing_preset(preset),
        emotes=tuple(resolve_emotes(emote_list)),
        emote_timing=resolve_emote_timing_preset(preset),
        mouth_idle_enabled=mouth_idle_enabled,
        face_layout=face_layout_ratios_from_mapping(data.get("face_layout")),
        viseme_labels=tuple(data["viseme_labels"]) if data.get("viseme_labels") else (),
    )
    return personality


def list_personality_ids() -> list[str]:
    """Return sorted personality ids (YAML stem names)."""
    out: list[str] = []
    for path in sorted(PERSONALITIES_DIR.glob("*.yaml")):
        stem = path.stem.strip().lower()
        if stem and not stem.startswith("_"):
            out.append(stem)
    return out
