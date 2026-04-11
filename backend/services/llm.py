import logging

from backend.models import LlmResult

logger: logging.Logger = logging.getLogger("backend.llm")


class EchoLlmService:
    """Dummy LLM that echoes input as output. Drop-in replacement for a real LLM."""

    def __init__(self, *, system_prompt: str | None = None) -> None:
        self._system_prompt: str | None = system_prompt

    def generate(self, user_text: str) -> LlmResult:
        if self._system_prompt:
            logger.debug("Echo (system prompt set, %d chars) user: %s", len(self._system_prompt), user_text[:80])
        logger.debug('Echo response: "%s"', user_text)
        return LlmResult(response=user_text)
