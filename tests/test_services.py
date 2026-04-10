import io
import types
import wave
from dataclasses import dataclass

import pytest

from backend.models import LlmResult
from backend.services.llm import EchoLlmService
from backend.services.stt import WhisperSttService
from backend.services.tts import AZURE_TICKS_PER_MS, AzureTtsService


def _make_wav_bytes(duration_sec: float = 0.2, sample_rate: int = 16000) -> bytes:
    frames = int(duration_sec * sample_rate)
    raw = b"\x00\x00" * frames
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)
    return buf.getvalue()


def test_echo_llm_returns_input():
    service = EchoLlmService()
    result = service.generate("hello")
    assert isinstance(result, LlmResult)
    assert result.response == "hello"
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0


class _FakeTranscriptions:
    def __init__(self, text: str):
        self._text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(text=self._text)


class _FakeAudio:
    def __init__(self, text: str):
        self.transcriptions = _FakeTranscriptions(text)


class _FakeClient:
    def __init__(self, text: str):
        self.audio = _FakeAudio(text)


def test_whisper_init_constructs_openai_client(monkeypatch: pytest.MonkeyPatch):
    seen = {}

    def _fake_openai(api_key: str):
        seen["api_key"] = api_key
        return _FakeClient("x")

    monkeypatch.setattr("backend.services.stt.OpenAI", _fake_openai)
    service = WhisperSttService(api_key="secret")
    assert seen["api_key"] == "secret"
    assert isinstance(service._client, _FakeClient)


@pytest.mark.parametrize(
    ("audio_format", "expected_name"),
    [
        ("wav", "audio.wav"),
        ("mp3", "audio.mp3"),
        ("webm", "audio.webm"),
        ("ogg", "audio.ogg"),
        ("m4a", "audio.m4a"),
        ("flac", "audio.flac"),
        ("aac", "audio.aac"),
    ],
)
def test_whisper_transcribe_uses_expected_filename(audio_format: str, expected_name: str):
    service = WhisperSttService.__new__(WhisperSttService)
    fake_client = _FakeClient(" transcribed ")
    service._client = fake_client

    wav_bytes = _make_wav_bytes()
    result = service.transcribe(wav_bytes, audio_format)

    call = fake_client.audio.transcriptions.calls[0]
    assert call["model"] == "whisper-1"
    assert call["file"].name == expected_name
    assert result.text == "transcribed"


def test_whisper_transcribe_calculates_wav_duration():
    service = WhisperSttService.__new__(WhisperSttService)
    service._client = _FakeClient("x")
    wav_bytes = _make_wav_bytes(duration_sec=0.5)
    result = service.transcribe(wav_bytes, "wav")
    assert 490.0 <= result.duration_ms <= 510.0


def test_whisper_transcribe_non_wav_duration_zero():
    service = WhisperSttService.__new__(WhisperSttService)
    service._client = _FakeClient("x")
    result = service.transcribe(b"not-a-real-mp3", "mp3")
    assert result.duration_ms == 0.0


def test_whisper_transcribe_bad_wav_falls_back_to_zero_duration():
    service = WhisperSttService.__new__(WhisperSttService)
    service._client = _FakeClient("x")
    result = service.transcribe(b"bad-wav", "wav")
    assert result.duration_ms == 0.0


@dataclass
class _FakeCancellation:
    reason: str
    error_details: str = ""


@dataclass
class _FakeResult:
    reason: str
    audio_data: bytes
    cancellation_details: _FakeCancellation


class _FakeEventHook:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class _FakeSynthesizer:
    def __init__(self, result: _FakeResult, viseme_events: list[tuple[int, int]]):
        self._result = result
        self._viseme_events = viseme_events
        self.viseme_received = _FakeEventHook()

    def speak_text(self, text: str):
        assert text
        for viseme_id, audio_offset in self._viseme_events:
            evt = types.SimpleNamespace(viseme_id=viseme_id, audio_offset=audio_offset)
            self.viseme_received.callback(evt)
        return self._result


def _make_fake_speechsdk(result: _FakeResult, viseme_events: list[tuple[int, int]]):
    class _SpeechConfig:
        def __init__(self, subscription: str, region: str):
            self.subscription = subscription
            self.region = region
            self.speech_synthesis_voice_name = None
            self.output_format = None

        def set_speech_synthesis_output_format(self, fmt):
            self.output_format = fmt

    class _SpeechSynthesizer:
        def __init__(self, speech_config, audio_config):
            assert audio_config is None
            self._inner = _FakeSynthesizer(result, viseme_events)
            self.viseme_received = self._inner.viseme_received

        def speak_text(self, text):
            return self._inner.speak_text(text)

    return types.SimpleNamespace(
        SpeechConfig=_SpeechConfig,
        SpeechSynthesizer=_SpeechSynthesizer,
        SpeechSynthesisResult=object,
        SessionEventArgs=object,
        CancellationDetails=object,
        ResultReason=types.SimpleNamespace(SynthesizingAudioCompleted="ok"),
        SpeechSynthesisOutputFormat=types.SimpleNamespace(Riff16Khz16BitMonoPcm="fmt"),
    )


def test_azure_tts_synthesize_success(monkeypatch: pytest.MonkeyPatch):
    audio_data = b"\x00\x00" * 16000  # 1 second at 16kHz 16-bit mono
    result = _FakeResult(
        reason="ok",
        audio_data=audio_data,
        cancellation_details=_FakeCancellation(reason="none"),
    )
    fake_sdk = _make_fake_speechsdk(
        result,
        viseme_events=[(1, 10 * AZURE_TICKS_PER_MS), (2, 25 * AZURE_TICKS_PER_MS)],
    )
    monkeypatch.setattr("backend.services.tts.speechsdk", fake_sdk)

    service = AzureTtsService("k", "r", "voice")
    out = service.synthesize("hello world")

    assert out.audio_data == audio_data
    assert len(out.visemes) == 2
    assert out.visemes[0].id == 1
    assert out.visemes[0].offset_ms == 10
    assert out.visemes[1].offset_ms == 25
    assert 999 <= out.duration_ms <= 1001
    assert out.characters_synthesized == len("hello world")


@pytest.mark.parametrize(
    ("reason", "details"),
    [
        ("error", ""),
        ("canceled", "network"),
        ("denied", "bad key"),
    ],
)
def test_azure_tts_synthesize_failure_raises(monkeypatch: pytest.MonkeyPatch, reason: str, details: str):
    result = _FakeResult(
        reason="not-ok",
        audio_data=b"",
        cancellation_details=_FakeCancellation(reason=reason, error_details=details),
    )
    fake_sdk = _make_fake_speechsdk(result, viseme_events=[])
    monkeypatch.setattr("backend.services.tts.speechsdk", fake_sdk)

    service = AzureTtsService("k", "r", "voice")
    with pytest.raises(RuntimeError) as exc:
        service.synthesize("x")

    assert "TTS synthesis failed" in str(exc.value)
    assert reason in str(exc.value)
    if details:
        assert details in str(exc.value)

