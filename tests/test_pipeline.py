import json
from pathlib import Path

import pytest

from backend.cli import Args
from backend.models import LlmResult, PipelineResult, SttResult, TtsResult, VisemeEvent
from backend.personalities import load_personality
from backend.pipeline import Pipeline

_PETER = load_personality("peter")


class _Stt:
    def __init__(self, result: SttResult):
        self.result = result
        self.calls = []

    def transcribe(self, audio: bytes, audio_format: str) -> SttResult:
        self.calls.append((audio, audio_format))
        return self.result


class _Llm:
    def __init__(self, result: LlmResult):
        self.result = result
        self.calls: list[tuple[str, list | None]] = []

    def generate(self, user_text: str, *, history=None) -> LlmResult:
        self.calls.append((user_text, history))
        return self.result


class _Tts:
    def __init__(self, result: TtsResult | None = None, error: Exception | None = None):
        self.result = result if result is not None else TtsResult(audio_data=b"")
        self.error = error
        self.calls = []

    def synthesize(self, text: str) -> TtsResult:
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return self.result


def _args(**overrides):
    base = dict(
        text=None,
        audio=None,
        file=None,
        render=False,
        test=False,
        test_sprites=False,
        test_animations=False,
        test_personalities=False,
        log_level="INFO",
        output=None,
        personality="peter",
        llm_backend="echo",
    )
    base.update(overrides)
    return Args(**base)


def _pipeline():
    return Pipeline(
        stt=_Stt(SttResult(text="stt-text", duration_ms=123.0)),
        llm=_Llm(LlmResult(response="llm-response", prompt_tokens=7, completion_tokens=11)),
        tts=_Tts(
            TtsResult(
                audio_data=b"audio",
                visemes=[VisemeEvent(id=1, offset_ms=10.0)],
                duration_ms=500.0,
                characters_synthesized=12,
            )
        ),
    )


def test_safe_synthesize_success():
    p = _pipeline()
    out = p._safe_synthesize("hello")
    assert out.audio_data == b"audio"


def test_safe_synthesize_failure_returns_empty_tts():
    p = Pipeline(stt=_Stt(SttResult(text="x")), llm=_Llm(LlmResult(response="y")), tts=_Tts(error=RuntimeError("boom")))
    out = p._safe_synthesize("hello")
    assert out.audio_data == b""
    assert out.visemes == []
    assert out.duration_ms == 0.0


def test_process_text_happy_path():
    p = _pipeline()
    result = p.process_text("user-msg")
    assert result.user_text == "user-msg"
    assert result.response_text == "llm-response"
    assert result.tts.characters_synthesized == 12
    assert p._usage.call_count == 1
    assert p._usage.tts_characters == 12


def test_process_text_passes_chat_history_to_llm():
    p = _pipeline()
    p.process_text("first")
    p.process_text("second")
    assert p._llm.calls[0] == ("first", [])
    assert p._llm.calls[1][0] == "second"
    assert p._llm.calls[1][1] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "llm-response"},
    ]


def test_process_text_trims_history_to_last_three_turns():
    p = _pipeline()
    for k in range(4):
        p.process_text(f"m{k}")
    assert len(p._llm.calls[3][1]) == 6
    assert p._llm.calls[3][1][0] == {"role": "user", "content": "m0"}

    p.process_text("m4")
    h = p._llm.calls[4][1]
    assert len(h) == 6
    assert h[0] == {"role": "user", "content": "m1"}
    assert h[-2] == {"role": "user", "content": "m3"}


def test_process_audio_file_not_found():
    p = _pipeline()
    with pytest.raises(FileNotFoundError):
        p.process_audio("missing-does-not-exist.wav")


def test_process_audio_happy_path(tmp_path: Path):
    p = _pipeline()
    audio = tmp_path / "input.wav"
    audio.write_bytes(b"123")
    result = p.process_audio(str(audio))
    assert result.user_text == "stt-text"
    assert result.response_text == "llm-response"
    assert result.stt_duration_ms == 123.0
    assert p._usage.call_count == 1


def test_process_audio_uses_suffix_without_dot(tmp_path: Path):
    stt = _Stt(SttResult(text="spoken"))
    p = Pipeline(stt=stt, llm=_Llm(LlmResult(response="r")), tts=_Tts(TtsResult(audio_data=b"a")))
    audio = tmp_path / "input.mp3"
    audio.write_bytes(b"x")
    p.process_audio(str(audio))
    assert stt.calls[0][1] == "mp3"


def test_process_file_not_found():
    p = _pipeline()
    with pytest.raises(FileNotFoundError):
        p.process_file("missing-lines.txt")


def test_process_file_ignores_blank_lines(tmp_path: Path):
    p = _pipeline()
    fp = tmp_path / "lines.txt"
    fp.write_text("a\n\n  \nb\n")
    results = p.process_file(str(fp))
    assert len(results) == 2
    assert [r.user_text for r in results] == ["a", "b"]


def test_output_result_no_output_dir(tmp_path: Path):
    p = _pipeline()
    result = p.process_text("x")
    p._output_result(result, _args(output=None))
    assert not (tmp_path / "output.wav").exists()


def test_output_result_writes_files(tmp_path: Path):
    p = _pipeline()
    result = p.process_text("x")
    p._output_result(result, _args(output=str(tmp_path)))
    audio_path = tmp_path / "output.wav"
    viseme_path = tmp_path / "visemes.json"
    assert audio_path.read_bytes() == b"audio"
    visemes = json.loads(viseme_path.read_text())
    assert visemes == [{"id": 1, "offset_ms": 10.0}]


def test_interactive_dispatch_render(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    calls = {"render": 0, "text": 0}
    monkeypatch.setattr(
        p,
        "_interactive_render",
        lambda args, personality: calls.__setitem__("render", calls["render"] + 1),
    )
    monkeypatch.setattr(p, "_interactive_text", lambda args: calls.__setitem__("text", calls["text"] + 1))
    p._interactive(_args(render=True), _PETER)
    assert calls["render"] == 1
    assert calls["text"] == 0


def test_interactive_dispatch_text(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    calls = {"render": 0, "text": 0}
    monkeypatch.setattr(
        p,
        "_interactive_render",
        lambda args, personality: calls.__setitem__("render", calls["render"] + 1),
    )
    monkeypatch.setattr(p, "_interactive_text", lambda args: calls.__setitem__("text", calls["text"] + 1))
    p._interactive(_args(render=False), _PETER)
    assert calls["render"] == 0
    assert calls["text"] == 1


@pytest.mark.parametrize("user_input", ["quit", "exit", "q", "", "   "])
def test_interactive_text_exits_on_terminators(monkeypatch: pytest.MonkeyPatch, user_input: str):
    p = _pipeline()
    monkeypatch.setattr("builtins.input", lambda _: user_input)
    played = []
    monkeypatch.setattr("backend.rendering.audio.play_audio", lambda tts: played.append(tts))
    p._interactive_text(_args())
    assert played == []


def test_interactive_text_processes_then_exits(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    inputs = iter(["hello", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    played = []
    monkeypatch.setattr("backend.rendering.audio.play_audio", lambda tts: played.append(tts.audio_data))
    outputs = []
    monkeypatch.setattr(p, "_output_result", lambda result, args: outputs.append(result.response_text))
    p._interactive_text(_args())
    assert played == [b"audio"]
    assert outputs == ["llm-response"]


@pytest.mark.parametrize("exception_type", [EOFError, KeyboardInterrupt])
def test_interactive_text_handles_terminal_exceptions(monkeypatch: pytest.MonkeyPatch, exception_type):
    p = _pipeline()

    def _raise(_):
        raise exception_type()

    monkeypatch.setattr("builtins.input", _raise)
    p._interactive_text(_args())


@pytest.mark.parametrize(
    ("kwargs", "expected_method"),
    [
        ({"text": "hello"}, "process_text"),
        ({"audio": "file.wav"}, "process_audio"),
        ({"file": "lines.txt"}, "process_file"),
    ],
)
def test_run_dispatches_to_correct_processor(monkeypatch: pytest.MonkeyPatch, kwargs: dict, expected_method: str):
    p = _pipeline()
    called = {"process_text": 0, "process_audio": 0, "process_file": 0, "interactive": 0, "output": 0, "play": 0}
    sample = PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"a"))

    monkeypatch.setattr(p, "process_text", lambda text: called.__setitem__("process_text", called["process_text"] + 1) or sample)
    monkeypatch.setattr(p, "process_audio", lambda path: called.__setitem__("process_audio", called["process_audio"] + 1) or sample)
    monkeypatch.setattr(p, "process_file", lambda path: called.__setitem__("process_file", called["process_file"] + 1) or [sample])
    monkeypatch.setattr(p, "_interactive", lambda args: called.__setitem__("interactive", called["interactive"] + 1))
    monkeypatch.setattr(p, "_output_result", lambda result, args: called.__setitem__("output", called["output"] + 1))
    monkeypatch.setattr("backend.rendering.audio.play_audio", lambda tts: called.__setitem__("play", called["play"] + 1))
    monkeypatch.setattr(p, "_print_usage_report", lambda: None)

    p.run(_args(**kwargs), _PETER)
    assert called[expected_method] == 1
    assert called["interactive"] == 0


def test_run_interactive_path(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    called = {"interactive": 0}
    monkeypatch.setattr(
        p,
        "_interactive",
        lambda args, personality: called.__setitem__("interactive", called["interactive"] + 1),
    )
    monkeypatch.setattr(p, "_print_usage_report", lambda: None)
    p.run(_args(), _PETER)
    assert called["interactive"] == 1


@pytest.mark.parametrize("render_enabled", [False, True])
def test_run_text_renders_or_plays(monkeypatch: pytest.MonkeyPatch, render_enabled: bool):
    p = _pipeline()
    sample = PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"a"))
    monkeypatch.setattr(p, "process_text", lambda text: sample)
    calls = {"play": 0, "render": 0}
    monkeypatch.setattr("backend.rendering.audio.play_audio", lambda tts: calls.__setitem__("play", calls["play"] + 1))
    monkeypatch.setattr(
        "backend.rendering.avatar.render_avatar",
        lambda result, personality: calls.__setitem__("render", calls["render"] + 1),
    )
    monkeypatch.setattr(p, "_print_usage_report", lambda: None)
    p.run(_args(text="x", render=render_enabled), _PETER)
    assert calls["render"] == (1 if render_enabled else 0)
    assert calls["play"] == (0 if render_enabled else 1)


def test_run_file_outputs_each_result(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    results = [
        PipelineResult(user_text="u1", response_text="r1", tts=TtsResult(audio_data=b"a")),
        PipelineResult(user_text="u2", response_text="r2", tts=TtsResult(audio_data=b"b")),
    ]
    monkeypatch.setattr(p, "process_file", lambda path: results)
    out_calls = []
    monkeypatch.setattr(p, "_output_result", lambda result, args: out_calls.append(result.response_text))
    monkeypatch.setattr("backend.rendering.audio.play_audio", lambda tts: None)
    monkeypatch.setattr(p, "_print_usage_report", lambda: None)
    p.run(_args(file="x.txt", render=False), _PETER)
    assert out_calls == ["r1", "r2"]


def test_run_audio_with_render(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    sample = PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"a"))
    monkeypatch.setattr(p, "process_audio", lambda path: sample)
    calls = {"render": 0, "play": 0}
    monkeypatch.setattr(
        "backend.rendering.avatar.render_avatar",
        lambda result, personality: calls.__setitem__("render", calls["render"] + 1),
    )
    monkeypatch.setattr("backend.rendering.audio.play_audio", lambda tts: calls.__setitem__("play", calls["play"] + 1))
    monkeypatch.setattr(p, "_print_usage_report", lambda: None)
    p.run(_args(audio="audio.wav", render=True), _PETER)
    assert calls == {"render": 1, "play": 0}


def test_run_file_with_render(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    results = [PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"a"))]
    monkeypatch.setattr(p, "process_file", lambda path: results)
    calls = {"render": 0, "play": 0}
    monkeypatch.setattr(
        "backend.rendering.avatar.render_avatar",
        lambda result, personality: calls.__setitem__("render", calls["render"] + 1),
    )
    monkeypatch.setattr("backend.rendering.audio.play_audio", lambda tts: calls.__setitem__("play", calls["play"] + 1))
    monkeypatch.setattr(p, "_print_usage_report", lambda: None)
    p.run(_args(file="lines.txt", render=True), _PETER)
    assert calls == {"render": 1, "play": 0}


def test_interactive_render_falls_back_when_window_not_ready(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    calls = {"fallback": 0}

    class _Window:
        ready = False

    monkeypatch.setattr("backend.rendering.avatar.AvatarWindow", lambda personality: _Window())
    monkeypatch.setattr(p, "_interactive_text", lambda args: calls.__setitem__("fallback", calls["fallback"] + 1))
    p._interactive_render(_args(render=True), _PETER)
    assert calls["fallback"] == 1


def test_interactive_render_processes_input_and_closes(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    played_results = []
    closed = {"value": False}
    sample = PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"a"))

    class _Window:
        ready = True

        def play(self, result):
            played_results.append(result)

        def request_close(self):
            closed["value"] = True

        def run_forever(self):
            return None

    class _ImmediateThread:
        def __init__(self, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            self._target()

    inputs = iter(["hello", "quit"])
    monkeypatch.setattr("backend.rendering.avatar.AvatarWindow", lambda personality: _Window())
    monkeypatch.setattr("threading.Thread", _ImmediateThread)
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(p, "process_text", lambda text: sample)
    monkeypatch.setattr(p, "_output_result", lambda result, args: None)
    p._interactive_render(_args(render=True), _PETER)
    assert played_results == [sample]
    assert closed["value"] is True


def test_interactive_render_terminal_exception_still_closes(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    closed = {"value": False}

    class _Window:
        ready = True

        def play(self, result):
            return None

        def request_close(self):
            closed["value"] = True

        def run_forever(self):
            return None

    class _ImmediateThread:
        def __init__(self, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            self._target()

    def _raise(_):
        raise EOFError()

    monkeypatch.setattr("backend.rendering.avatar.AvatarWindow", lambda personality: _Window())
    monkeypatch.setattr("threading.Thread", _ImmediateThread)
    monkeypatch.setattr("builtins.input", _raise)
    p._interactive_render(_args(render=True), _PETER)
    assert closed["value"] is True


@pytest.mark.parametrize("call_count", [0, 1, 3])
def test_print_usage_report_no_crash(call_count: int):
    p = _pipeline()
    p._usage.call_count = call_count
    if call_count:
        p._usage.stt_audio_ms = 1000
        p._usage.llm_prompt_tokens = 2
        p._usage.llm_completion_tokens = 3
        p._usage.tts_characters = 4
    p._print_usage_report()


def test_print_usage_report_text_only_branch(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    p._usage.call_count = 1
    p._usage.stt_audio_ms = 0.0
    p._usage.llm_prompt_tokens = 1
    p._usage.llm_completion_tokens = 2
    p._usage.tts_characters = 3
    logs = []
    monkeypatch.setattr("backend.pipeline.logger.info", lambda msg, *args: logs.append(msg % args if args else msg))
    p._print_usage_report()
    assert any("text input only" in msg for msg in logs)


def test_print_usage_report_zero_llm_tokens_branch(monkeypatch: pytest.MonkeyPatch):
    p = _pipeline()
    p._usage.call_count = 1
    p._usage.stt_audio_ms = 1000.0
    p._usage.llm_prompt_tokens = 0
    p._usage.llm_completion_tokens = 0
    p._usage.tts_characters = 3
    logs = []
    monkeypatch.setattr("backend.pipeline.logger.info", lambda msg, *args: logs.append(msg % args if args else msg))
    p._print_usage_report()
    assert any("no token usage recorded" in msg for msg in logs)

