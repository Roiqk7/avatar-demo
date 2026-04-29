from __future__ import annotations

import logging
from dataclasses import dataclass

import azure.cognitiveservices.speech as speechsdk

logger = logging.getLogger("backend.voice_catalog")


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    short_name: str
    locale: str
    gender: str | None = None

    @property
    def language(self) -> str:
        # locale like "fr-FR" -> "fr"
        return self.locale.split("-", 1)[0].lower()


class AzureSpeechVoiceCatalog:
    """Cached list of voices available in the configured Azure Speech region."""

    def __init__(self, *, speech_key: str, speech_region: str) -> None:
        self._speech_key = speech_key
        self._speech_region = speech_region
        self._loaded = False
        self._last_error: str | None = None
        self._voices: list[VoiceInfo] = []
        self.by_locale: dict[str, list[VoiceInfo]] = {}
        self.by_language: dict[str, list[VoiceInfo]] = {}

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def load(self) -> None:
        """Fetch voices once and build locale/language indexes."""
        try:
            config = speechsdk.SpeechConfig(subscription=self._speech_key, region=self._speech_region)
            synth = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
            result = synth.get_voices_async().get()
            voices = getattr(result, "voices", None) or []

            parsed: list[VoiceInfo] = []
            for v in voices:
                short_name = getattr(v, "short_name", None) or getattr(v, "name", None)
                locale = getattr(v, "locale", None)
                if not short_name or not locale:
                    continue
                gender = getattr(v, "gender", None)
                # gender may be an enum; keep readable str
                gender_s = str(gender) if gender is not None else None
                parsed.append(VoiceInfo(short_name=str(short_name), locale=str(locale), gender=gender_s))

            # stable ordering
            parsed.sort(key=lambda x: (x.locale.lower(), x.short_name.lower()))

            by_locale: dict[str, list[VoiceInfo]] = {}
            by_language: dict[str, list[VoiceInfo]] = {}
            for info in parsed:
                by_locale.setdefault(info.locale, []).append(info)
                by_language.setdefault(info.language, []).append(info)

            self._voices = parsed
            self.by_locale = by_locale
            self.by_language = by_language
            self._loaded = True
            self._last_error = None
            logger.info("Loaded %d Azure voices (%d locales)", len(parsed), len(by_locale))
        except Exception as e:
            self._loaded = False
            self._voices = []
            self.by_locale = {}
            self.by_language = {}
            self._last_error = f"{type(e).__name__}: {e}"
            logger.warning("Failed to load Azure voice catalog: %s", self._last_error)

