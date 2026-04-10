import logging
import threading

import azure.cognitiveservices.speech as speechsdk

from backend.models import TtsResult, VisemeEvent

logger: logging.Logger = logging.getLogger("backend.tts")

AZURE_TICKS_PER_MS: int = 10_000


class AzureTtsService:
    """Azure Speech SDK TTS with viseme event collection."""

    def __init__(self, speech_key: str, speech_region: str, voice_name: str) -> None:
        self._speech_key: str = speech_key
        self._speech_region: str = speech_region
        self._voice_name: str = voice_name

    def synthesize(self, text: str) -> TtsResult:
        """Synthesize speech from text, returning audio bytes and viseme timeline."""
        config: speechsdk.SpeechConfig = speechsdk.SpeechConfig(
            subscription=self._speech_key,
            region=self._speech_region,
        )
        config.speech_synthesis_voice_name = self._voice_name
        config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm,
        )

        synthesizer: speechsdk.SpeechSynthesizer = speechsdk.SpeechSynthesizer(
            speech_config=config,
            audio_config=None,  # collect audio in memory, don't play directly
        )

        visemes: list[VisemeEvent] = []
        lock: threading.Lock = threading.Lock()

        def on_viseme(evt: speechsdk.SessionEventArgs) -> None:
            viseme = VisemeEvent(
                id=evt.viseme_id,
                offset_ms=evt.audio_offset / AZURE_TICKS_PER_MS,
            )
            with lock:
                visemes.append(viseme)

        synthesizer.viseme_received.connect(on_viseme)

        logger.debug("Synthesizing: %s", text[:80])
        result: speechsdk.SpeechSynthesisResult = synthesizer.speak_text(text)

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            audio_data: bytes = result.audio_data
            duration_ms: float = len(audio_data) / (16_000 * 2) * 1000  # 16kHz 16-bit mono

            logger.debug(
                "Synthesized %.1fs of audio, %d viseme events",
                duration_ms / 1000,
                len(visemes),
            )
            logger.debug(
                "Viseme timeline: %s",
                ", ".join(f"{v.offset_ms:.0f}ms:{v.id}" for v in visemes[:10]),
            )

            return TtsResult(
                audio_data=audio_data,
                visemes=visemes,
                duration_ms=duration_ms,
                characters_synthesized=len(text),
            )

        cancellation: speechsdk.CancellationDetails = result.cancellation_details
        error_msg: str = f"TTS synthesis failed: {cancellation.reason}"
        if cancellation.error_details:
            error_msg += f" — {cancellation.error_details}"
        logger.debug(error_msg)
        raise RuntimeError(error_msg)
