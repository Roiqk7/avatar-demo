import io
import logging
import wave

import httpx
from openai import OpenAI

from backend.models import SttResult

logger: logging.Logger = logging.getLogger("backend.stt")

FORMAT_TO_EXTENSION: dict[str, str] = {
    "wav": "wav",
    "mp3": "mp3",
    "webm": "webm",
    "ogg": "ogg",
    "m4a": "m4a",
    "flac": "flac",
    "mp4": "mp4",
}

DEFAULT_STT_MODEL: str = "gpt-4o-transcribe"

DEFAULT_STT_LANGUAGE: str | None = None

# Instruction-style prompt for gpt-4o-transcribe (understands English instructions well).
# Explicitly rejects Polish/Slovak — the two most common misdetections for Czech speech.
DEFAULT_STT_PROMPT: str | None = (
    "Transcribe ONLY in Czech, English, or Portuguese. "
)


class WhisperSttService:
    """OpenAI transcription wrapper.

    Default config is tuned for Czech-first, English-second, Portuguese-third demos:
    - model: gpt-4o-transcribe
    - language: auto (None), overridable via STT_LANGUAGE
    - prompt: trilingual bias string, overridable per-call for dynamic session prompts
    - temperature: 0 (deterministic)
    - http_client: httpx.Client with 30s keepalive to reuse TLS connections
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_STT_MODEL,
        language: str | None = DEFAULT_STT_LANGUAGE,
        prompt: str | None = DEFAULT_STT_PROMPT,
    ) -> None:
        # Shared httpx client with keepalive — reuses TCP+TLS connections across requests,
        # eliminating the ~100-300ms handshake overhead on each transcription call.
        http_client = httpx.Client(
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
                keepalive_expiry=30.0,
            ),
            timeout=60.0,
        )
        self._client: OpenAI = OpenAI(api_key=api_key, http_client=http_client)
        self._model: str = model
        self._language: str | None = language
        self._prompt: str | None = (prompt.strip() if prompt else None)

    def transcribe(
        self,
        audio: bytes,
        audio_format: str = "wav",
        prompt_override: str | None = None,
        language_override: str | None = None,
    ) -> SttResult:
        """Transcribe audio bytes to text.

        Args:
            audio: Raw audio bytes.
            audio_format: One of the keys in FORMAT_TO_EXTENSION.
            prompt_override: If set, replaces the default prompt for this call.
                Used by dynamic per-session language dictionary prompts.
            language_override: If set, forces the transcription language for this call.
                Strongest enforcement — prevents any cross-language confusion.
                Takes precedence over the instance-level language setting.
        """
        extension: str = FORMAT_TO_EXTENSION.get(audio_format, audio_format)
        filename: str = f"audio.{extension}"

        effective_language = language_override or self._language
        logger.debug(
            "Transcribing %d bytes of %s audio (model=%s, lang=%s)",
            len(audio), audio_format, self._model, effective_language or "auto",
        )

        audio_file: io.BytesIO = io.BytesIO(audio)
        audio_file.name = filename

        effective_prompt = prompt_override if prompt_override is not None else self._prompt

        kwargs: dict = {"model": self._model, "file": audio_file, "temperature": 0}
        if effective_language:
            kwargs["language"] = effective_language
        if effective_prompt:
            kwargs["prompt"] = effective_prompt

        response = self._client.audio.transcriptions.create(**kwargs)

        text: str = response.text.strip()
        logger.debug('Transcribed: "%s"', text[:100])

        duration_ms: float = _wav_duration_ms(audio) if audio_format == "wav" else 0.0
        return SttResult(text=text, duration_ms=duration_ms)


def _wav_duration_ms(audio: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio)) as wf:
            return wf.getnframes() / wf.getframerate() * 1000
    except Exception:
        return 0.0
