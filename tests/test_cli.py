import pytest

from backend.cli import parse_args


def _parse(monkeypatch: pytest.MonkeyPatch, argv: list[str]):
    monkeypatch.setattr("sys.argv", ["prog", *argv])
    return parse_args()


def test_parse_defaults(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, [])
    assert args.text is None
    assert args.audio is None
    assert args.file is None
    assert args.render is False
    assert args.test is False
    assert args.test_sprites is False
    assert args.test_animations is False
    assert args.test_personalities is False
    assert args.log_level == "INFO"
    assert args.output is None
    assert args.personality == "peter"


@pytest.mark.parametrize(
    ("flag", "value", "field"),
    [
        ("--text", "hello", "text"),
        ("--audio", "sample.wav", "audio"),
        ("--file", "in.txt", "file"),
    ],
)
def test_parse_input_flags(monkeypatch: pytest.MonkeyPatch, flag: str, value: str, field: str):
    args = _parse(monkeypatch, [flag, value])
    assert getattr(args, field) == value


def test_parse_render(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, ["--render"])
    assert args.render is True


def test_parse_test_flag(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, ["--test"])
    assert args.test is True


def test_parse_test_sprites(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, ["--test-sprites"])
    assert args.test_sprites is True


def test_parse_test_animations(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, ["--test-animations"])
    assert args.test_animations is True


def test_parse_test_personalities(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, ["--test-personalities"])
    assert args.test_personalities is True


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_parse_log_levels(monkeypatch: pytest.MonkeyPatch, level: str):
    args = _parse(monkeypatch, ["--log-level", level])
    assert args.log_level == level


def test_parse_output(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, ["--output", "outdir"])
    assert args.output == "outdir"


def test_parse_personality(monkeypatch: pytest.MonkeyPatch):
    args = _parse(monkeypatch, ["--personality", "Emma"])
    assert args.personality == "emma"


def test_parse_combined_flags(monkeypatch: pytest.MonkeyPatch):
    args = _parse(
        monkeypatch,
        [
            "--text",
            "hello",
            "--render",
            "--test",
            "--test-sprites",
            "--test-animations",
            "--test-personalities",
            "--log-level",
            "DEBUG",
            "--output",
            "tmp",
            "--personality",
            "trevor",
        ],
    )
    assert args.text == "hello"
    assert args.render is True
    assert args.test is True
    assert args.test_sprites is True
    assert args.test_animations is True
    assert args.test_personalities is True
    assert args.log_level == "DEBUG"
    assert args.output == "tmp"
    assert args.personality == "trevor"


@pytest.mark.parametrize(
    "argv",
    [
        ["--text", "x", "--audio", "a.wav"],
        ["--text", "x", "--file", "f.txt"],
        ["--audio", "a.wav", "--file", "f.txt"],
    ],
)
def test_mutually_exclusive_inputs_fail(monkeypatch: pytest.MonkeyPatch, argv: list[str]):
    with pytest.raises(SystemExit):
        _parse(monkeypatch, argv)

