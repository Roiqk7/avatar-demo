import logging
import pytest

from backend.config import Settings
from backend.log import PipelineFormatter, setup_logging


def test_settings_load_reads_required(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.config.load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azure-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "westus")
    monkeypatch.setenv("AZURE_VOICE_NAME", "voice")
    monkeypatch.setenv("LLM_SYSTEM_PROMPT", "prompt")

    settings = Settings.load()
    assert settings.openai_api_key == "openai-key"
    assert settings.azure_speech_key == "azure-key"
    assert settings.azure_speech_region == "westus"
    assert settings.azure_voice_name == "voice"
    assert settings.llm_system_prompt == "prompt"


def test_settings_load_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.config.load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azure-key")
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    monkeypatch.delenv("AZURE_VOICE_NAME", raising=False)
    monkeypatch.delenv("LLM_SYSTEM_PROMPT", raising=False)

    settings = Settings.load()
    assert settings.azure_speech_region == "eastus"
    assert settings.azure_voice_name == "en-US-JennyNeural"
    assert settings.llm_system_prompt == "You are a helpful assistant."


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "AZURE_SPEECH_KEY"])
def test_settings_load_missing_required_raises(monkeypatch: pytest.MonkeyPatch, missing: str):
    monkeypatch.setattr("backend.config.load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azure-key")
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(KeyError):
        Settings.load()


@pytest.mark.parametrize(
    ("level_no", "name", "expected"),
    [
        (logging.DEBUG, "backend.pipeline", "[DEBUG PIPELINE] message"),
        (logging.INFO, "backend.pipeline", "[INFO ] message"),
        (logging.WARNING, "backend.main", "[WARNING] message"),
        (logging.ERROR, "backend.tts", "[ERROR] message"),
    ],
)
def test_pipeline_formatter(level_no: int, name: str, expected: str):
    formatter = PipelineFormatter()
    record = logging.LogRecord(
        name=name,
        level=level_no,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )
    assert formatter.format(record) == expected


def test_setup_logging_sets_backend_level():
    root = logging.getLogger("backend")
    old_handlers = list(root.handlers)
    old_level = root.level
    root.handlers.clear()
    try:
        setup_logging("DEBUG")
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, PipelineFormatter)
    finally:
        root.handlers.clear()
        root.handlers.extend(old_handlers)
        root.setLevel(old_level)


@pytest.mark.parametrize(
    ("level_text", "expected_level"),
    [
        ("INFO", logging.INFO),
        ("warning", logging.WARNING),
        ("DOES_NOT_EXIST", logging.INFO),
    ],
)
def test_setup_logging_level_parsing(level_text: str, expected_level: int):
    root = logging.getLogger("backend")
    old_handlers = list(root.handlers)
    old_level = root.level
    root.handlers.clear()
    try:
        setup_logging(level_text)
        assert root.level == expected_level
    finally:
        root.handlers.clear()
        root.handlers.extend(old_handlers)
        root.setLevel(old_level)


def test_setup_logging_does_not_duplicate_handlers():
    root = logging.getLogger("backend")
    old_handlers = list(root.handlers)
    old_level = root.level
    root.handlers.clear()
    try:
        setup_logging("INFO")
        setup_logging("DEBUG")
        assert len(root.handlers) == 1
    finally:
        root.handlers.clear()
        root.handlers.extend(old_handlers)
        root.setLevel(old_level)

