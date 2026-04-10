import logging
import sys


class PipelineFormatter(logging.Formatter):
    """Clean formatter: [LEVEL] message (module shown only at DEBUG)"""

    LEVEL_WIDTH: int = 5

    def format(self, record: logging.LogRecord) -> str:
        level: str = record.levelname.ljust(self.LEVEL_WIDTH)
        module: str = record.name.split(".")[-1].upper()
        if record.levelno <= logging.DEBUG:
            return f"[{level} {module}] {record.getMessage()}"
        return f"[{level}] {record.getMessage()}"


def setup_logging(level: str = "INFO") -> None:
    """Configure the backend logger with the pipeline formatter."""
    root: logging.Logger = logging.getLogger("backend")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(PipelineFormatter())
        root.addHandler(handler)
