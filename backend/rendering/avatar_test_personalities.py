"""Interactive personality switcher: compare avatars and motion."""

from __future__ import annotations

import logging
import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.config import Settings
from backend.models import PipelineResult
from backend.personalities import list_personality_ids, load_personality
from backend.rendering.avatar_window import AvatarWindow
from backend.services.tts import AzureTtsService

logger = logging.getLogger("backend.avatar_test_personalities")

DEMO_TEXT = (
    "Yo, listen up, here's a story "
    "About a little guy that lives in a blue world "
    "And all day and all night "
    "And everything he sees is just blue "
    "Like him inside and outside "
    "Blue his house "
    "With a blue little window "
    "And a blue Corvette "
    "And everything is blue for him "
    "And himself and everybody around "
    "'Cause he ain't got nobody to listen (to listen) "
    "I'm blue"
)


def test_personalities(initial_personality_id: str, settings: Settings) -> None:
    """Open the avatar window, cycle personas, and play demo speech on Space (Azure TTS).

    Controls:
      Left / Right — previous / next personality
      Space        — synthesize and speak the demo line (``DEMO_TEXT``)
      Esc / Q      — quit
    """
    ids = list_personality_ids()
    if not ids:
        print("No personalities found under backend/personalities/")
        return

    if initial_personality_id not in ids:
        initial_personality_id = ids[0]

    idx = ids.index(initial_personality_id)
    personality = load_personality(ids[idx])
    window = AvatarWindow(personality, oneshot=False)
    if not window.ready:
        print("ERROR: avatar assets missing for personality", ids[idx])
        return

    font = pygame.font.SysFont("monospace", 15)
    font_big = pygame.font.SysFont("monospace", 18, bold=True)

    def on_after_draw(screen: pygame.Surface) -> None:
        h = screen.get_height()
        lines = [
            f"Personality: {personality.display_name} ({ids[idx]})  [{idx + 1}/{len(ids)}]",
            "",
            "Left/Right = switch   Space = demo TTS   Esc/Q = quit",
        ]
        y0 = h - 120
        for i, line in enumerate(lines):
            f = font_big if i == 0 else font
            color = (255, 255, 100) if i == 0 else (200, 200, 200)
            screen.blit(f.render(line, True, color), (10, y0 + i * 19))

    def on_keydown(event: pygame.event.Event) -> bool:
        nonlocal idx, personality
        if event.key in (pygame.K_ESCAPE, pygame.K_q):
            window.request_close()
            return True
        if window.is_playing:
            return True
        if event.key == pygame.K_LEFT:
            idx = (idx - 1) % len(ids)
            personality = load_personality(ids[idx])
            window.apply_personality(personality)
            return True
        if event.key == pygame.K_RIGHT:
            idx = (idx + 1) % len(ids)
            personality = load_personality(ids[idx])
            window.apply_personality(personality)
            return True
        if event.key == pygame.K_SPACE:
            voice = settings.azure_voice_name
            tts = AzureTtsService(
                speech_key=settings.azure_speech_key,
                speech_region=settings.azure_speech_region,
                voice_name=voice,
            )
            try:
                tts_result = tts.synthesize(DEMO_TEXT)
            except Exception as e:
                logger.warning("TTS failed: %s", e)
                return True
            window.play(
                PipelineResult(
                    user_text="(personality demo)",
                    response_text=DEMO_TEXT[:200],
                    tts=tts_result,
                )
            )
            return True
        return False

    window.run_forever(on_keydown=on_keydown, on_after_draw=on_after_draw)
