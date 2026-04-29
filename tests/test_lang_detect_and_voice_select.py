import pytest

from backend.services.lang_detect import _parse_translator_detect
from backend.services.azure_voice_catalog import VoiceInfo
from backend.services.voice_select import ENGLISH_PREFERRED_VOICE, choose_voice


def test_parse_translator_detect_happy_path():
    detected = _parse_translator_detect([{"language": "cs", "score": 0.99}])
    assert detected is not None
    assert detected.language == "cs"
    assert detected.score == 0.99


@pytest.mark.parametrize("payload", [None, [], {}, [{"nope": 1}], [{"language": ""}], [{"language": None}]])
def test_parse_translator_detect_invalid_payload_returns_none(payload):
    assert _parse_translator_detect(payload) is None


_MALE = "SynthesisVoiceGender.Male"
_FEMALE = "SynthesisVoiceGender.Female"


class _FakeCatalog:
    loaded = True

    def __init__(self):
        self.by_language = {
            "cs": [VoiceInfo(short_name="cs-CZ-VlastaNeural", locale="cs-CZ", gender=_FEMALE)],
            "fr": [
                VoiceInfo(short_name="fr-CA-SylvieNeural", locale="fr-CA", gender=_FEMALE),
                VoiceInfo(short_name="fr-FR-DeniseNeural", locale="fr-FR", gender=_FEMALE),
            ],
        }


def test_choose_voice_picks_preferred_locale_when_available():
    sel = choose_voice(detected_language="fr", fallback_voice_name="en-US-JennyNeural", catalog=_FakeCatalog())
    assert sel.voice_name.startswith("fr-FR-")
    assert sel.locale == "fr-FR"


def test_choose_voice_falls_back_for_unknown_lang():
    sel = choose_voice(detected_language="xx", fallback_voice_name="en-US-JennyNeural", catalog=_FakeCatalog())
    assert sel.voice_name == "en-US-JennyNeural"


def test_choose_voice_falls_back_when_catalog_not_loaded():
    c = _FakeCatalog()
    c.loaded = False
    sel = choose_voice(detected_language="fr", fallback_voice_name="en-US-JennyNeural", catalog=c)
    assert sel.voice_name == "en-US-JennyNeural"


def test_choose_voice_prefers_male():
    class _MixedCatalog:
        loaded = True
        by_language = {
            "en": [
                VoiceInfo(short_name="en-US-JennyNeural", locale="en-US", gender=_FEMALE),
                VoiceInfo(short_name="en-US-GuyNeural", locale="en-US", gender=_MALE),
            ]
        }

    sel = choose_voice(detected_language="en", fallback_voice_name="en-US-JennyNeural", catalog=_MixedCatalog())
    assert sel.voice_name == ENGLISH_PREFERRED_VOICE


def test_choose_voice_falls_back_to_any_gender_when_no_male():
    class _FemaleOnlyCatalog:
        loaded = True
        by_language = {
            "fr": [
                VoiceInfo(short_name="fr-FR-DeniseNeural", locale="fr-FR", gender=_FEMALE),
            ]
        }

    sel = choose_voice(detected_language="fr", fallback_voice_name="en-US-GuyNeural", catalog=_FemaleOnlyCatalog())
    assert sel.voice_name == "fr-FR-DeniseNeural"

