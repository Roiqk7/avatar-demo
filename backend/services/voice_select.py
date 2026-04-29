from __future__ import annotations

from dataclasses import dataclass

from backend.services.azure_voice_catalog import AzureSpeechVoiceCatalog, VoiceInfo


@dataclass(frozen=True, slots=True)
class VoiceSelection:
    voice_name: str
    language: str | None = None
    locale: str | None = None
    candidates: int | None = None


ENGLISH_PREFERRED_VOICE: str = "en-US-Adam:DragonHDLatestNeural"

LOCALE_PREFERENCES: dict[str, list[str]] = {
    # Keep common languages explicit; everything else falls back to stable sorting.
    "en": ["en-US", "en-GB", "en-IE", "en-AU", "en-CA"],
    "fr": ["fr-FR", "fr-CA", "fr-BE", "fr-CH"],
    "de": ["de-DE", "de-AT", "de-CH"],
    "es": ["es-ES", "es-MX", "es-US"],
    "pt": ["pt-PT", "pt-BR"],
    "zh": ["zh-CN", "zh-HK", "zh-TW"],
    "cs": ["cs-CZ"],
    "sk": ["sk-SK"],
}


def choose_voice(
    *,
    detected_language: str | None,
    fallback_voice_name: str,
    catalog: AzureSpeechVoiceCatalog | None,
) -> VoiceSelection:
    """Choose a voice for any detected language using the Azure voice catalog."""
    lang = (detected_language or "").strip().lower()
    if lang == "en":
        return VoiceSelection(voice_name=ENGLISH_PREFERRED_VOICE, language=lang, locale="en-US")
    if not lang or catalog is None or not catalog.loaded:
        return VoiceSelection(voice_name=fallback_voice_name, language=lang or None)

    candidates = list(catalog.by_language.get(lang, ()))
    if not candidates:
        return VoiceSelection(voice_name=fallback_voice_name, language=lang)

    male_candidates = [v for v in candidates if v.gender and v.gender.lower().split(".")[-1] == "male"]
    if male_candidates:
        candidates = male_candidates

    locale = _choose_locale(lang, candidates)
    locale_candidates = [v for v in candidates if v.locale.lower() == locale.lower()]
    pick_from = locale_candidates or candidates
    chosen = pick_from[0]
    return VoiceSelection(
        voice_name=chosen.short_name,
        language=lang,
        locale=chosen.locale,
        candidates=len(candidates),
    )


def _choose_locale(lang: str, voices: list[VoiceInfo]) -> str:
    prefs = LOCALE_PREFERENCES.get(lang, [])
    locales = sorted({v.locale for v in voices}, key=lambda x: x.lower())
    for p in prefs:
        for loc in locales:
            if loc.lower() == p.lower():
                return loc
    return locales[0]

