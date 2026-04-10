import io
import logging
import os
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.models import TtsResult

logger: logging.Logger = logging.getLogger("backend.audio")

_mixer_initialized: bool = False


def _ensure_mixer() -> None:
    """Initialize pygame mixer once."""
    global _mixer_initialized
    if not _mixer_initialized:
        pygame.mixer.init(frequency=16000, size=-16, channels=1)
        _mixer_initialized = True


def play_audio(tts_result: TtsResult) -> None:
    """Play TTS audio through speakers and block until finished."""
    if not tts_result.audio_data:
        return

    _ensure_mixer()

    sound: pygame.mixer.Sound = pygame.mixer.Sound(io.BytesIO(tts_result.audio_data))
    duration_sec: float = sound.get_length()
    logger.info("Playing audio (%.1fs)...", duration_sec)

    sound.play()

    while pygame.mixer.get_busy():
        time.sleep(0.05)

    logger.debug("Audio playback finished")
