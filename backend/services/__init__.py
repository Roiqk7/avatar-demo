from typing import Protocol

from backend.models import LlmResult, SttResult, TtsResult


class SttService(Protocol):
    """Speech-to-text interface. Swap implementations without touching the pipeline."""

    def transcribe(self, audio: bytes, audio_format: str) -> SttResult: ...


class LlmService(Protocol):
    """LLM interface. Swap implementations without touching the pipeline."""

    def generate(self, user_text: str) -> LlmResult: ...


class TtsService(Protocol):
    """TTS + viseme interface. Swap implementations without touching the pipeline."""

    def synthesize(self, text: str) -> TtsResult: ...
