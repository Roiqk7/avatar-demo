import io
import logging
import wave

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
}


class WhisperSttService:
    """OpenAI Whisper API wrapper for speech-to-text."""

    def __init__(self, api_key: str) -> None:
        self._client: OpenAI = OpenAI(api_key=api_key)

    def transcribe(self, audio: bytes, audio_format: str = "wav") -> SttResult:
        """Transcribe audio bytes to text using OpenAI Whisper."""
        extension: str = FORMAT_TO_EXTENSION.get(audio_format, audio_format)
        filename: str = f"audio.{extension}"

        logger.debug("Transcribing %d bytes of %s audio", len(audio), audio_format)

        audio_file: io.BytesIO = io.BytesIO(audio)
        audio_file.name = filename

        response = self._client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )

        text: str = response.text.strip()
        logger.debug('Transcribed: "%s"', text[:100])

        duration_ms: float = 0.0
        if audio_format == "wav":
            try:
                with wave.open(io.BytesIO(audio)) as wf:
                    duration_ms = wf.getnframes() / wf.getframerate() * 1000
            except Exception:
                pass

        return SttResult(text=text, duration_ms=duration_ms)
