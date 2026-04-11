from dataclasses import dataclass, field
from typing import Literal, TypedDict


class ChatTurn(TypedDict):
    """One message in multi-turn chat (OpenAI-style roles)."""

    role: Literal["user", "assistant"]
    content: str


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
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class TtsResult:
    """Result from text-to-speech synthesis including viseme data."""

    audio_data: bytes
    visemes: list[VisemeEvent] = field(default_factory=list)
    duration_ms: float = 0.0
    characters_synthesized: int = 0


@dataclass(frozen=True)
class PipelineResult:
    """Complete result from a single pipeline run."""

    user_text: str
    response_text: str
    tts: TtsResult
    stt_duration_ms: float = 0.0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0


@dataclass
class SessionUsage:
    """Accumulated API usage statistics across all pipeline calls in a session."""

    stt_audio_ms: float = 0.0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    tts_characters: int = 0
    call_count: int = 0

    def add(self, result: "PipelineResult") -> None:
        self.stt_audio_ms += result.stt_duration_ms
        self.llm_prompt_tokens += result.llm_prompt_tokens
        self.llm_completion_tokens += result.llm_completion_tokens
        self.tts_characters += result.tts.characters_synthesized
        self.call_count += 1
