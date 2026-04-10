import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Args:
    """Parsed CLI arguments."""

    text: str | None
    audio: str | None
    file: str | None
    render: bool
    test: bool
    test_sprites: bool
    test_animations: bool
    log_level: str
    output: str | None


def parse_args() -> Args:
    """Parse command-line arguments into a typed Args object."""
    parser = argparse.ArgumentParser(
        description="Avatar Demo — full pipeline from terminal",
    )

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--text", type=str, help="Direct text input")
    input_group.add_argument("--audio", type=str, help="Audio file path (runs through STT)")
    input_group.add_argument("--file", type=str, help="Text file path to read input from")

    parser.add_argument("--render", action="store_true", help="Open pygame avatar window")
    parser.add_argument("--test", action="store_true", help="Run all unit tests and exit")
    parser.add_argument("--test-sprites", action="store_true", help="Open sprite test viewer (no pipeline needed)")
    parser.add_argument("--test-animations", action="store_true", help="Browse and play all animations (no pipeline needed)")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    parser.add_argument("--output", type=str, help="Directory to save audio + viseme JSON")

    ns = parser.parse_args()
    return Args(
        text=ns.text,
        audio=ns.audio,
        file=ns.file,
        render=ns.render,
        test=ns.test,
        test_sprites=ns.test_sprites,
        test_animations=ns.test_animations,
        log_level=ns.log_level,
        output=ns.output,
    )
