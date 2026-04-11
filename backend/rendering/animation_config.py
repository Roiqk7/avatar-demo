"""Configurable animation timing and behaviour for avatar controllers.

Presets map to named personalities (Ted / Emma / Peter / Trevor). YAML uses
``animation.preset`` for mouth timing + emote timing, and optionally
``animation.eye_preset`` for eyes (defaults to the same name as ``preset``).

**Blinking** is part of every eye preset. To tune it without Python changes::

    animation:
      preset: moderate
      eyes:
        blink:
          initial_ms: [2500, 5000]   # ms until first blink after idle starts
          after_ms: [2800, 5500]    # ms between blinks

**Per-channel toggles** (merge onto the chosen ``eye_preset``)::

    animation:
      eye_preset: stoic
      eyes:
        micro_glance: false
        long_glance: true
        expression_glance: false
        goofy_sequences: false

**Drop specific eye sprite indices** from glance pools, goofy eye sequences, and emote eye tracks::

    animation:
      eyes:
        exclude_eye_indices: [11]
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class EyeAnimationConfig:
    """Parameters for :class:`EyeController`."""

    enable_micro_glance: bool
    enable_long_glance: bool
    enable_expr_glance: bool
    enable_goofy_sequences: bool

    blink_initial_ms: tuple[float, float]
    blink_after_ms: tuple[float, float]

    micro_initial_ms: tuple[float, float]
    micro_after_ms: tuple[float, float]
    micro_glance_indices: tuple[int, ...]
    micro_return_ms: tuple[float, float]

    glance_initial_ms: tuple[float, float]
    glance_after_ms: tuple[float, float]
    glance_indices: tuple[int, ...]
    glance_return_ms: tuple[float, float]

    expr_initial_ms: tuple[float, float]
    expr_after_ms: tuple[float, float]
    expr_indices: tuple[int, ...]
    expr_return_ms: tuple[float, float]

    goofy_initial_ms: tuple[float, float]
    goofy_after_ms: tuple[float, float]

    micro_transition_ms: float
    glance_transition_ms: float
    expr_transition_ms: float

    forbidden_eye_indices: frozenset[int] = field(default_factory=frozenset)
    """Eye sprite indices that must never be shown (goofy sequences + emotes respect this too)."""


@dataclass(frozen=True, slots=True)
class MouthIdlePools:
    """Sprite names per idle tier (must exist in the pack's visemes folder)."""

    subtle: tuple[str, ...]
    happy: tuple[str, ...]
    goofy: tuple[str, ...]
    dramatic: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MouthTimingConfig:
    """Timers and transition defaults for :class:`MouthController`."""

    idle_delay_ms: float
    subtle_next_initial: tuple[float, float]
    subtle_next_after: tuple[float, float]
    happy_next_initial: tuple[float, float]
    happy_next_after: tuple[float, float]
    goofy_next_initial: tuple[float, float]
    goofy_next_after: tuple[float, float]
    dramatic_next_initial: tuple[float, float]
    dramatic_next_after: tuple[float, float]
    subtle_transition_ms: float
    subtle_hold_ms: tuple[float, float]
    happy_transition_ms: float
    happy_hold_ms: tuple[float, float]
    goofy_transition_ms: float
    goofy_hold_ms: tuple[float, float]
    dramatic_transition_ms: float
    dramatic_hold_ms: tuple[float, float]
    return_transition_ms: float


@dataclass(frozen=True, slots=True)
class EmoteTimingConfig:
    """Timers for :class:`EmoteController`."""

    enabled: bool
    idle_delay_ms: float
    first_emote_after_ms: tuple[float, float]
    emote_after_ms: tuple[float, float]


EYE_PRESETS: dict[str, EyeAnimationConfig] = {
    "boring": EyeAnimationConfig(
        enable_micro_glance=False,
        enable_long_glance=False,
        enable_expr_glance=False,
        enable_goofy_sequences=False,
        blink_initial_ms=(3200.0, 6400.0),
        blink_after_ms=(4000.0, 9000.0),
        micro_initial_ms=(0.0, 0.0),
        micro_after_ms=(0.0, 0.0),
        micro_glance_indices=(),
        micro_return_ms=(0.0, 0.0),
        glance_initial_ms=(0.0, 0.0),
        glance_after_ms=(0.0, 0.0),
        glance_indices=(),
        glance_return_ms=(0.0, 0.0),
        expr_initial_ms=(0.0, 0.0),
        expr_after_ms=(0.0, 0.0),
        expr_indices=(),
        expr_return_ms=(0.0, 0.0),
        goofy_initial_ms=(0.0, 0.0),
        goofy_after_ms=(0.0, 0.0),
        micro_transition_ms=174.0,
        glance_transition_ms=288.0,
        expr_transition_ms=336.0,
    ),
    # Blink + slow sideways/up glances only — no micro-darts, no “expression” or goofy eye sequences.
    "stoic": EyeAnimationConfig(
        enable_micro_glance=False,
        enable_long_glance=True,
        enable_expr_glance=False,
        enable_goofy_sequences=False,
        blink_initial_ms=(4000.0, 8000.0),
        blink_after_ms=(4500.0, 10000.0),
        micro_initial_ms=(0.0, 0.0),
        micro_after_ms=(0.0, 0.0),
        micro_glance_indices=(),
        micro_return_ms=(0.0, 0.0),
        glance_initial_ms=(16000.0, 32000.0),
        glance_after_ms=(22000.0, 48000.0),
        glance_indices=(1, 8),
        glance_return_ms=(1000.0, 2400.0),
        expr_initial_ms=(0.0, 0.0),
        expr_after_ms=(0.0, 0.0),
        expr_indices=(),
        expr_return_ms=(0.0, 0.0),
        goofy_initial_ms=(0.0, 0.0),
        goofy_after_ms=(0.0, 0.0),
        micro_transition_ms=174.0,
        glance_transition_ms=320.0,
        expr_transition_ms=336.0,
    ),
    "moderate": EyeAnimationConfig(
        enable_micro_glance=True,
        enable_long_glance=True,
        enable_expr_glance=True,
        enable_goofy_sequences=False,
        blink_initial_ms=(2000.0, 4200.0),
        blink_after_ms=(2200.0, 5000.0),
        micro_initial_ms=(2800.0, 5600.0),
        micro_after_ms=(3200.0, 7200.0),
        micro_glance_indices=(1, 8, 10, 11),
        micro_return_ms=(240.0, 520.0),
        glance_initial_ms=(7000.0, 13000.0),
        glance_after_ms=(8000.0, 16000.0),
        glance_indices=(1, 8, 11),
        glance_return_ms=(900.0, 2000.0),
        expr_initial_ms=(14000.0, 26000.0),
        expr_after_ms=(16000.0, 32000.0),
        expr_indices=(9, 12, 5, 7),
        expr_return_ms=(1200.0, 2800.0),
        goofy_initial_ms=(0.0, 0.0),
        goofy_after_ms=(0.0, 0.0),
        micro_transition_ms=174.0,
        glance_transition_ms=288.0,
        expr_transition_ms=336.0,
    ),
    "hyperactive": EyeAnimationConfig(
        enable_micro_glance=True,
        enable_long_glance=True,
        enable_expr_glance=True,
        enable_goofy_sequences=True,
        blink_initial_ms=(1500.0, 3500.0),
        blink_after_ms=(1800.0, 4200.0),
        micro_initial_ms=(2200.0, 5000.0),
        micro_after_ms=(2800.0, 5800.0),
        micro_glance_indices=(1, 8, 10, 11),
        micro_return_ms=(204.0, 444.0),
        glance_initial_ms=(6000.0, 12000.0),
        glance_after_ms=(6500.0, 15000.0),
        glance_indices=(1, 8, 11),
        glance_return_ms=(840.0, 1800.0),
        expr_initial_ms=(12000.0, 24000.0),
        expr_after_ms=(14000.0, 30000.0),
        expr_indices=(9, 12, 5, 7),
        expr_return_ms=(1200.0, 3120.0),
        goofy_initial_ms=(24000.0, 42000.0),
        goofy_after_ms=(25000.0, 50000.0),
        micro_transition_ms=174.0,
        glance_transition_ms=288.0,
        expr_transition_ms=336.0,
    ),
    "extreme": EyeAnimationConfig(
        enable_micro_glance=True,
        enable_long_glance=True,
        enable_expr_glance=True,
        enable_goofy_sequences=True,
        blink_initial_ms=(900.0, 2200.0),
        blink_after_ms=(1100.0, 2800.0),
        micro_initial_ms=(1200.0, 3200.0),
        micro_after_ms=(1600.0, 4000.0),
        micro_glance_indices=(1, 2, 8, 10, 11, 14),
        micro_return_ms=(120.0, 360.0),
        glance_initial_ms=(3500.0, 8000.0),
        glance_after_ms=(4200.0, 10000.0),
        glance_indices=(1, 8, 10, 11),
        glance_return_ms=(600.0, 1400.0),
        expr_initial_ms=(7000.0, 15000.0),
        expr_after_ms=(9000.0, 20000.0),
        expr_indices=(2, 5, 7, 9, 12, 14),
        expr_return_ms=(800.0, 2400.0),
        goofy_initial_ms=(12000.0, 22000.0),
        goofy_after_ms=(14000.0, 28000.0),
        micro_transition_ms=120.0,
        glance_transition_ms=220.0,
        expr_transition_ms=260.0,
    ),
}

MOUTH_TIMING_PRESETS: dict[str, MouthTimingConfig] = {
    "boring": MouthTimingConfig(
        idle_delay_ms=5000.0,
        subtle_next_initial=(6000.0, 12000.0),
        subtle_next_after=(8000.0, 16000.0),
        happy_next_initial=(20000.0, 40000.0),
        happy_next_after=(25000.0, 50000.0),
        goofy_next_initial=(1.0, 2.0),
        goofy_next_after=(1.0, 2.0),
        dramatic_next_initial=(1.0, 2.0),
        dramatic_next_after=(1.0, 2.0),
        subtle_transition_ms=380.0,
        subtle_hold_ms=(2000.0, 4500.0),
        happy_transition_ms=400.0,
        happy_hold_ms=(2500.0, 5000.0),
        goofy_transition_ms=280.0,
        goofy_hold_ms=(1500.0, 3500.0),
        dramatic_transition_ms=400.0,
        dramatic_hold_ms=(1800.0, 3500.0),
        return_transition_ms=400.0,
    ),
    "moderate": MouthTimingConfig(
        idle_delay_ms=4000.0,
        subtle_next_initial=(4000.0, 8000.0),
        subtle_next_after=(5000.0, 10000.0),
        happy_next_initial=(12000.0, 22000.0),
        happy_next_after=(14000.0, 26000.0),
        goofy_next_initial=(35000.0, 60000.0),
        goofy_next_after=(40000.0, 70000.0),
        dramatic_next_initial=(60000.0, 100000.0),
        dramatic_next_after=(70000.0, 110000.0),
        subtle_transition_ms=320.0,
        subtle_hold_ms=(1400.0, 3200.0),
        happy_transition_ms=360.0,
        happy_hold_ms=(2200.0, 4200.0),
        goofy_transition_ms=300.0,
        goofy_hold_ms=(1600.0, 3400.0),
        dramatic_transition_ms=420.0,
        dramatic_hold_ms=(2000.0, 3800.0),
        return_transition_ms=380.0,
    ),
    "hyperactive": MouthTimingConfig(
        idle_delay_ms=3000.0,
        subtle_next_initial=(3000.0, 6000.0),
        subtle_next_after=(4000.0, 8000.0),
        happy_next_initial=(8000.0, 16000.0),
        happy_next_after=(10000.0, 20000.0),
        goofy_next_initial=(20000.0, 40000.0),
        goofy_next_after=(22000.0, 45000.0),
        dramatic_next_initial=(45000.0, 80000.0),
        dramatic_next_after=(50000.0, 90000.0),
        subtle_transition_ms=300.0,
        subtle_hold_ms=(1200.0, 3000.0),
        happy_transition_ms=350.0,
        happy_hold_ms=(2000.0, 4500.0),
        goofy_transition_ms=280.0,
        goofy_hold_ms=(1500.0, 3500.0),
        dramatic_transition_ms=400.0,
        dramatic_hold_ms=(1800.0, 3500.0),
        return_transition_ms=350.0,
    ),
    "extreme": MouthTimingConfig(
        idle_delay_ms=1800.0,
        subtle_next_initial=(1800.0, 4000.0),
        subtle_next_after=(2200.0, 5000.0),
        happy_next_initial=(5000.0, 10000.0),
        happy_next_after=(6000.0, 12000.0),
        goofy_next_initial=(10000.0, 22000.0),
        goofy_next_after=(12000.0, 26000.0),
        dramatic_next_initial=(22000.0, 40000.0),
        dramatic_next_after=(26000.0, 48000.0),
        subtle_transition_ms=220.0,
        subtle_hold_ms=(800.0, 2200.0),
        happy_transition_ms=260.0,
        happy_hold_ms=(1200.0, 3200.0),
        goofy_transition_ms=200.0,
        goofy_hold_ms=(900.0, 2600.0),
        dramatic_transition_ms=320.0,
        dramatic_hold_ms=(1200.0, 2800.0),
        return_transition_ms=280.0,
    ),
}

EMOTE_TIMING_PRESETS: dict[str, EmoteTimingConfig] = {
    "boring": EmoteTimingConfig(
        enabled=False,
        idle_delay_ms=0.0,
        first_emote_after_ms=(0.0, 0.0),
        emote_after_ms=(0.0, 0.0),
    ),
    "moderate": EmoteTimingConfig(
        enabled=True,
        idle_delay_ms=6000.0,
        first_emote_after_ms=(12000.0, 28000.0),
        emote_after_ms=(22000.0, 45000.0),
    ),
    "hyperactive": EmoteTimingConfig(
        enabled=True,
        idle_delay_ms=5000.0,
        first_emote_after_ms=(8000.0, 18000.0),
        emote_after_ms=(15000.0, 35000.0),
    ),
    "extreme": EmoteTimingConfig(
        enabled=True,
        idle_delay_ms=3500.0,
        first_emote_after_ms=(4000.0, 10000.0),
        emote_after_ms=(8000.0, 20000.0),
    ),
}


def resolve_eye_preset(name: str) -> EyeAnimationConfig:
    key = name.strip().lower()
    if key not in EYE_PRESETS:
        known = ", ".join(sorted(EYE_PRESETS))
        raise ValueError(f"Unknown eye animation preset {name!r}. Expected one of: {known}")
    return EYE_PRESETS[key]


def _pair_ms(raw: Any, field: str) -> tuple[float, float] | None:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"animation.eyes: expected {field} as [min_ms, max_ms]")
    return (float(raw[0]), float(raw[1]))


def _filter_eye_indices(indices: tuple[int, ...], forbidden: frozenset[int]) -> tuple[int, ...]:
    return tuple(i for i in indices if i not in forbidden)


def build_eye_config(anim: dict[str, Any] | None) -> EyeAnimationConfig:
    """Build eye config from the YAML ``animation`` mapping.

    - ``preset`` / ``eye_preset``: named eye preset (``eye_preset`` wins if set).
    - ``eyes``: optional overrides — booleans for each channel, optional ``blink`` timings,
      optional ``exclude_eye_indices`` (stored as ``forbidden_eye_indices``) for glances, goofy
      sequences, and emote eye sequences.
    """
    if anim is None:
        anim = {}
    base_preset = str(anim.get("preset") or "hyperactive").strip().lower()
    eye_name = str(anim.get("eye_preset") or base_preset).strip().lower()
    cfg = resolve_eye_preset(eye_name)

    eyes = anim.get("eyes")
    if not isinstance(eyes, dict) or not eyes:
        return cfg

    kwargs: dict[str, Any] = {}
    if "micro_glance" in eyes:
        kwargs["enable_micro_glance"] = bool(eyes["micro_glance"])
    if "long_glance" in eyes:
        kwargs["enable_long_glance"] = bool(eyes["long_glance"])
    if "expression_glance" in eyes:
        kwargs["enable_expr_glance"] = bool(eyes["expression_glance"])
    if "goofy_sequences" in eyes:
        kwargs["enable_goofy_sequences"] = bool(eyes["goofy_sequences"])

    blink = eyes.get("blink")
    if isinstance(blink, dict):
        ini = _pair_ms(blink.get("initial_ms"), "blink.initial_ms")
        if ini is not None:
            kwargs["blink_initial_ms"] = ini
        aft = _pair_ms(blink.get("after_ms"), "blink.after_ms")
        if aft is not None:
            kwargs["blink_after_ms"] = aft

    merged = replace(cfg, **kwargs) if kwargs else cfg

    raw_excl = eyes.get("exclude_eye_indices")
    if raw_excl is not None:
        if not isinstance(raw_excl, (list, tuple)):
            raise ValueError("animation.eyes.exclude_eye_indices must be a list of integers")
        forbidden = frozenset(int(x) for x in raw_excl)
        extra: dict[str, Any] = {
            "micro_glance_indices": _filter_eye_indices(merged.micro_glance_indices, forbidden),
            "glance_indices": _filter_eye_indices(merged.glance_indices, forbidden),
            "expr_indices": _filter_eye_indices(merged.expr_indices, forbidden),
        }
        if not extra["micro_glance_indices"]:
            extra["enable_micro_glance"] = False
        if not extra["glance_indices"]:
            extra["enable_long_glance"] = False
        if not extra["expr_indices"]:
            extra["enable_expr_glance"] = False
        return replace(merged, **extra, forbidden_eye_indices=forbidden)

    return merged


def resolve_mouth_timing_preset(name: str) -> MouthTimingConfig:
    key = name.strip().lower()
    if key not in MOUTH_TIMING_PRESETS:
        known = ", ".join(sorted(MOUTH_TIMING_PRESETS))
        raise ValueError(f"Unknown mouth timing preset {name!r}. Expected one of: {known}")
    return MOUTH_TIMING_PRESETS[key]


def resolve_emote_timing_preset(name: str) -> EmoteTimingConfig:
    key = name.strip().lower()
    if key not in EMOTE_TIMING_PRESETS:
        known = ", ".join(sorted(EMOTE_TIMING_PRESETS))
        raise ValueError(f"Unknown emote timing preset {name!r}. Expected one of: {known}")
    return EMOTE_TIMING_PRESETS[key]
