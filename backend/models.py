from dataclasses import dataclass, field


@dataclass(frozen=True)
class VisemeEvent:
    """A single viseme event from TTS synthesis."""

    id: int
    """Viseme ID (0-21 for Azure), each mapping to a distinct mouth shape."""

    offset_ms: float
    """Milliseconds from the start of the audio."""


@dataclass(frozen=True)
class SttResult:
    """Result from speech-to-text transcription."""

    text: str
    language: str | None = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class LlmResult:
    """Result from LLM text generation."""

    response: str


@dataclass(frozen=True)
class TtsResult:
    """Result from text-to-speech synthesis including viseme data."""

    audio_data: bytes
    visemes: list[VisemeEvent] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass(frozen=True)
class PipelineResult:
    """Complete result from a single pipeline run."""

    user_text: str
    response_text: str
    tts: TtsResult
