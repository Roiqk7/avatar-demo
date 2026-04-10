from dataclasses import FrozenInstanceError

import pytest

from backend.models import LlmResult, PipelineResult, SessionUsage, SttResult, TtsResult, VisemeEvent


@pytest.mark.parametrize("viseme_id", list(range(22)))
def test_viseme_event_stores_fields(viseme_id: int):
    evt = VisemeEvent(id=viseme_id, offset_ms=12.5)
    assert evt.id == viseme_id
    assert evt.offset_ms == 12.5


def test_viseme_event_is_frozen():
    evt = VisemeEvent(id=1, offset_ms=1.0)
    with pytest.raises(FrozenInstanceError):
        evt.id = 2  # type: ignore[misc]


@pytest.mark.parametrize("text", ["", "hello", "ascii-only", "  spaced  "])
def test_stt_result_defaults_and_text(text: str):
    result = SttResult(text=text)
    assert result.text == text
    assert result.language is None
    assert result.duration_ms == 0.0


@pytest.mark.parametrize(
    ("response", "prompt_tokens", "completion_tokens"),
    [
        ("ok", 0, 0),
        ("result", 1, 2),
        ("long answer", 100, 250),
    ],
)
def test_llm_result_fields(response: str, prompt_tokens: int, completion_tokens: int):
    result = LlmResult(response=response, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    assert result.response == response
    assert result.prompt_tokens == prompt_tokens
    assert result.completion_tokens == completion_tokens


def test_tts_result_defaults():
    tts = TtsResult(audio_data=b"abc")
    assert tts.audio_data == b"abc"
    assert tts.visemes == []
    assert tts.duration_ms == 0.0
    assert tts.characters_synthesized == 0


@pytest.mark.parametrize("chars", [0, 1, 10, 1000])
def test_tts_result_character_count(chars: int):
    tts = TtsResult(audio_data=b"", characters_synthesized=chars)
    assert tts.characters_synthesized == chars


def test_pipeline_result_defaults():
    tts = TtsResult(audio_data=b"")
    result = PipelineResult(user_text="u", response_text="r", tts=tts)
    assert result.stt_duration_ms == 0.0
    assert result.llm_prompt_tokens == 0
    assert result.llm_completion_tokens == 0


@pytest.mark.parametrize(
    ("stt_ms", "prompt", "completion", "chars"),
    [
        (0.0, 0, 0, 0),
        (250.0, 3, 4, 10),
        (1000.5, 22, 33, 500),
        (42.0, 1, 1, 1),
        (99999.0, 2000, 2000, 12000),
    ],
)
def test_session_usage_add_single_result(stt_ms: float, prompt: int, completion: int, chars: int):
    usage = SessionUsage()
    result = PipelineResult(
        user_text="a",
        response_text="b",
        tts=TtsResult(audio_data=b"", characters_synthesized=chars),
        stt_duration_ms=stt_ms,
        llm_prompt_tokens=prompt,
        llm_completion_tokens=completion,
    )
    usage.add(result)
    assert usage.stt_audio_ms == stt_ms
    assert usage.llm_prompt_tokens == prompt
    assert usage.llm_completion_tokens == completion
    assert usage.tts_characters == chars
    assert usage.call_count == 1


def test_session_usage_add_multiple_results_accumulates():
    usage = SessionUsage()
    r1 = PipelineResult(
        user_text="u1",
        response_text="r1",
        tts=TtsResult(audio_data=b"", characters_synthesized=5),
        stt_duration_ms=100.0,
        llm_prompt_tokens=1,
        llm_completion_tokens=2,
    )
    r2 = PipelineResult(
        user_text="u2",
        response_text="r2",
        tts=TtsResult(audio_data=b"", characters_synthesized=7),
        stt_duration_ms=300.0,
        llm_prompt_tokens=4,
        llm_completion_tokens=8,
    )
    usage.add(r1)
    usage.add(r2)
    assert usage.stt_audio_ms == 400.0
    assert usage.llm_prompt_tokens == 5
    assert usage.llm_completion_tokens == 10
    assert usage.tts_characters == 12
    assert usage.call_count == 2

