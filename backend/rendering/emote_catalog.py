"""Named coordinated emotes (eye sequence + mouth sprite).

Personalities reference emotes by id in YAML (e.g. `emotes: [grin, laugh]`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Emote:
    """A full-face emote: paired eye sequence + mouth sprite."""

    name: str
    eye_seq: list[tuple[int, float, float]]
    mouth: str
    mouth_hold_ms: float


EMOTES_BY_NAME: dict[str, Emote] = {
    "grin": Emote(
        name="grin",
        eye_seq=[(9, 250, 0)],
        mouth="wide-smile",
        mouth_hold_ms=2800,
    ),
    "laugh": Emote(
        name="laugh",
        eye_seq=[(3, 120, 80), (4, 100, 400), (3, 100, 80), (4, 100, 500), (0, 180, 0)],
        mouth="laugh2",
        mouth_hold_ms=2200,
    ),
    "cheeky": Emote(
        name="cheeky",
        eye_seq=[(11, 220, 0)],
        mouth="tongue-out",
        mouth_hold_ms=2500,
    ),
    "shocked": Emote(
        name="shocked",
        eye_seq=[(2, 180, 0)],
        mouth="scream",
        mouth_hold_ms=2200,
    ),
    "smug": Emote(
        name="smug",
        eye_seq=[(5, 280, 0)],
        mouth="on-side",
        mouth_hold_ms=3000,
    ),
    "smug_soft": Emote(
        name="smug_soft",
        eye_seq=[(5, 280, 0)],
        mouth="wide-smile",
        mouth_hold_ms=3000,
    ),
    "derp": Emote(
        name="derp",
        eye_seq=[(13, 200, 600), (4, 80, 100), (13, 150, 400), (0, 220, 0)],
        mouth="tongue-out2",
        mouth_hold_ms=2000,
    ),
    "hysterical": Emote(
        name="hysterical",
        eye_seq=[(2, 90, 70), (14, 90, 70), (2, 90, 70), (14, 90, 70), (9, 180, 400), (0, 200, 0)],
        mouth="laugh3",
        mouth_hold_ms=2400,
    ),
}


def resolve_emotes(names: list[str]) -> list[Emote]:
    """Map emote ids to :class:`Emote` instances; unknown ids raise ``ValueError``."""
    out: list[Emote] = []
    for raw in names:
        key = raw.strip()
        if not key:
            continue
        em = EMOTES_BY_NAME.get(key)
        if em is None:
            known = ", ".join(sorted(EMOTES_BY_NAME))
            raise ValueError(f"Unknown emote {raw!r}. Expected one of: {known}")
        out.append(em)
    return out
