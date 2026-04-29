import types

import pytest

from backend.models import PipelineResult, TtsResult, VisemeEvent
from backend.personalities.llm_baseline import compose_llm_system_prompt
from backend.personalities import load_personality
from backend.rendering.audio import _ensure_mixer, play_audio
from backend.rendering.avatar_window import get_active_viseme, render_avatar


@pytest.mark.parametrize(
    ("elapsed_ms", "expected"),
    [
        (0.0, 0),
        (5.0, 0),
        (10.0, 1),
        (15.0, 1),
        (20.0, 2),
        (99.0, 2),
    ],
)
def test_get_active_viseme(elapsed_ms: float, expected: int):
    visemes = [VisemeEvent(id=1, offset_ms=10.0), VisemeEvent(id=2, offset_ms=20.0)]
    assert get_active_viseme(visemes, elapsed_ms) == expected


def test_render_avatar_skips_when_not_ready(monkeypatch: pytest.MonkeyPatch):
    fake_window = types.SimpleNamespace(ready=False, play=lambda r: None, run_forever=lambda: None)
    monkeypatch.setattr(
        "backend.rendering.avatar_window.AvatarWindow",
        lambda personality, *, oneshot=False: fake_window,
    )
    render_avatar(
        PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"")),
        load_personality("peter"),
    )


def test_render_avatar_plays_when_ready(monkeypatch: pytest.MonkeyPatch):
    calls = {"play": 0, "run": 0}

    class _Window:
        ready = True

        def play(self, _):
            calls["play"] += 1

        def run_forever(self):
            calls["run"] += 1

    monkeypatch.setattr(
        "backend.rendering.avatar_window.AvatarWindow",
        lambda personality, *, oneshot=False: _Window(),
    )
    render_avatar(
        PipelineResult(user_text="u", response_text="r", tts=TtsResult(audio_data=b"")),
        load_personality("peter"),
    )
    assert calls == {"play": 1, "run": 1}


def test_avatar_module_getattr_exports():
    import backend.rendering.avatar as avatar

    assert avatar.__getattr__("AvatarWindow").__name__ == "AvatarWindow"
    assert callable(avatar.__getattr__("render_avatar"))
    assert callable(avatar.__getattr__("test_sprites"))
    assert callable(avatar.__getattr__("test_animations"))


def test_avatar_module_getattr_unknown():
    import backend.rendering.avatar as avatar

    with pytest.raises(AttributeError):
        avatar.__getattr__("does_not_exist")


def test_ensure_mixer_only_initializes_once(monkeypatch: pytest.MonkeyPatch):
    import backend.rendering.audio as audio_mod

    calls = {"init": 0}
    monkeypatch.setattr("pygame.mixer.init", lambda **kwargs: calls.__setitem__("init", calls["init"] + 1))
    audio_mod._mixer_initialized = False
    _ensure_mixer()
    _ensure_mixer()
    assert calls["init"] == 1
    audio_mod._mixer_initialized = False


def test_play_audio_no_data(monkeypatch: pytest.MonkeyPatch):
    calls = {"ensure": 0}
    monkeypatch.setattr("backend.rendering.audio._ensure_mixer", lambda: calls.__setitem__("ensure", calls["ensure"] + 1))
    play_audio(TtsResult(audio_data=b""))
    assert calls["ensure"] == 0


def test_play_audio_happy_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.rendering.audio._ensure_mixer", lambda: None)

    class _Sound:
        def get_length(self):
            return 0.1

        def play(self):
            return None

    monkeypatch.setattr("pygame.mixer.Sound", lambda *args, **kwargs: _Sound())
    busy = iter([True, False])
    monkeypatch.setattr("pygame.mixer.get_busy", lambda: next(busy))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    play_audio(TtsResult(audio_data=b"abc"))


def test_main_test_flag_runs_pytest(monkeypatch: pytest.MonkeyPatch):
    import backend.main as main_mod
    from backend.cli import Args

    args = Args(
        text=None,
        audio=None,
        file=None,
        render=False,
        test=True,
        test_sprites=False,
        test_animations=False,
        test_personalities=False,
        log_level="INFO",
        output=None,
        personality="peter",
        llm_backend="echo",
    )
    monkeypatch.setattr("backend.main.parse_args", lambda: args)
    monkeypatch.setattr("backend.main.setup_logging", lambda level: None)
    monkeypatch.setattr("pytest.main", lambda argv: 7)
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 7


def test_main_test_sprites_branch(monkeypatch: pytest.MonkeyPatch):
    import backend.main as main_mod
    from backend.cli import Args

    args = Args(
        text=None,
        audio=None,
        file=None,
        render=False,
        test=False,
        test_sprites=True,
        test_animations=False,
        test_personalities=False,
        log_level="INFO",
        output=None,
        personality="emma",
        llm_backend="echo",
    )
    calls = {"sprites": 0, "pid": None}

    def _fake_sprites(personality_id: str = "peter") -> None:
        calls["sprites"] += 1
        calls["pid"] = personality_id

    monkeypatch.setattr("backend.main.parse_args", lambda: args)
    monkeypatch.setattr("backend.main.setup_logging", lambda level: None)
    monkeypatch.setattr("backend.rendering.avatar.test_sprites", _fake_sprites)
    main_mod.main()
    assert calls["sprites"] == 1
    assert calls["pid"] == "emma"


def test_main_test_animations_branch(monkeypatch: pytest.MonkeyPatch):
    import backend.main as main_mod
    from backend.cli import Args

    args = Args(
        text=None,
        audio=None,
        file=None,
        render=False,
        test=False,
        test_sprites=False,
        test_animations=True,
        test_personalities=False,
        log_level="INFO",
        output=None,
        personality="peter",
        llm_backend="echo",
    )
    calls = {"animations": 0}
    monkeypatch.setattr("backend.main.parse_args", lambda: args)
    monkeypatch.setattr("backend.main.setup_logging", lambda level: None)
    monkeypatch.setattr(
        "backend.rendering.avatar.test_animations",
        lambda personality_id="peter": calls.__setitem__("animations", calls["animations"] + 1),
    )
    main_mod.main()
    assert calls["animations"] == 1


def test_main_test_personalities_branch(monkeypatch: pytest.MonkeyPatch):
    import backend.main as main_mod
    from backend.cli import Args

    args = Args(
        text=None,
        audio=None,
        file=None,
        render=False,
        test=False,
        test_sprites=False,
        test_animations=False,
        test_personalities=True,
        log_level="INFO",
        output=None,
        personality="ted",
        llm_backend="echo",
    )
    calls = {"demo": 0, "pid": None, "settings": None}

    class _Settings:
        pass

    def _fake_demo(pid: str, settings) -> None:
        calls["demo"] += 1
        calls["pid"] = pid
        calls["settings"] = settings

    monkeypatch.setattr("backend.main.parse_args", lambda: args)
    monkeypatch.setattr("backend.main.setup_logging", lambda level: None)
    monkeypatch.setattr("backend.main.Settings.load", lambda: _Settings())
    monkeypatch.setattr("backend.rendering.avatar.test_personalities", _fake_demo)
    main_mod.main()
    assert calls["demo"] == 1
    assert calls["pid"] == "ted"
    assert isinstance(calls["settings"], _Settings)


def test_main_missing_settings_exits(monkeypatch: pytest.MonkeyPatch):
    import backend.main as main_mod
    from backend.cli import Args

    args = Args(
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
    monkeypatch.setattr("backend.main.parse_args", lambda: args)
    monkeypatch.setattr("backend.main.setup_logging", lambda level: None)
    monkeypatch.setattr("backend.main.Settings.load", lambda: (_ for _ in ()).throw(KeyError("OPENAI_API_KEY")))
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 1


def test_main_constructs_pipeline_and_runs(monkeypatch: pytest.MonkeyPatch):
    import backend.main as main_mod
    from backend.cli import Args

    args = Args(
        text="x",
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
        llm_backend="openai",
    )
    calls = {"run": 0}
    fake_personality = types.SimpleNamespace(
        id="peter",
        display_name="Peter",
        llm_system_prompt="",
    )
    settings = types.SimpleNamespace(
        openai_api_key="ok",
        azure_speech_key="az",
        azure_speech_region="eastus",
        azure_voice_name="voice",
        llm_system_prompt="You are a helpful assistant.",
        llm_model="gpt-4o-mini",
        llm_max_completion_tokens=512,
    )
    monkeypatch.setattr("backend.main.parse_args", lambda: args)
    monkeypatch.setattr("backend.main.setup_logging", lambda level: None)
    monkeypatch.setattr("backend.main.Settings.load", lambda: settings)
    monkeypatch.setattr("backend.main.load_personality", lambda pid: fake_personality)
    monkeypatch.setattr("backend.main.WhisperSttService", lambda api_key: object())
    monkeypatch.setattr("backend.main.OpenAiChatLlmService", lambda **kwargs: object())
    monkeypatch.setattr("backend.main.AzureTtsService", lambda speech_key, speech_region, voice_name: object())

    class _Pipeline:
        def __init__(self, stt, llm, tts):
            self.stt = stt
            self.llm = llm
            self.tts = tts

        def run(self, arg_obj, personality):
            calls["run"] += 1
            assert arg_obj is args
            assert personality is fake_personality

    monkeypatch.setattr("backend.main.Pipeline", _Pipeline)
    main_mod.main()
    assert calls["run"] == 1


def test_main_echo_llm_skips_openai_service(monkeypatch: pytest.MonkeyPatch):
    import backend.main as main_mod
    from backend.cli import Args

    args = Args(
        text="x",
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
    fake_personality = types.SimpleNamespace(
        id="peter",
        display_name="Peter",
        llm_system_prompt="sys",
    )
    settings = types.SimpleNamespace(
        openai_api_key="ok",
        azure_speech_key="az",
        azure_speech_region="eastus",
        azure_voice_name="voice",
        llm_system_prompt="You are a helpful assistant.",
        llm_model="gpt-4o-mini",
        llm_max_completion_tokens=512,
    )
    echo_calls: list[dict] = []
    openai_calls: list[dict] = []

    def _echo(**kwargs):
        echo_calls.append(kwargs)
        return object()

    def _openai(**kwargs):
        openai_calls.append(kwargs)
        return object()

    monkeypatch.setattr("backend.main.parse_args", lambda: args)
    monkeypatch.setattr("backend.main.setup_logging", lambda level: None)
    monkeypatch.setattr("backend.main.Settings.load", lambda: settings)
    monkeypatch.setattr("backend.main.load_personality", lambda pid: fake_personality)
    monkeypatch.setattr("backend.main.WhisperSttService", lambda api_key: object())
    monkeypatch.setattr("backend.main.EchoLlmService", _echo)
    monkeypatch.setattr("backend.main.OpenAiChatLlmService", _openai)
    monkeypatch.setattr("backend.main.AzureTtsService", lambda speech_key, speech_region, voice_name: object())
    monkeypatch.setattr(
        "backend.main.Pipeline",
        lambda stt, llm, tts: types.SimpleNamespace(run=lambda a, p: None),
    )
    main_mod.main()
    assert echo_calls == [{"system_prompt": compose_llm_system_prompt("sys")}]
    assert openai_calls == []

