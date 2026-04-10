import logging

from backend.models import LlmResult

logger: logging.Logger = logging.getLogger("backend.llm")


class EchoLlmService:
    """Dummy LLM that echoes input as output. Drop-in replacement for a real LLM."""

    def generate(self, user_text: str) -> LlmResult:
        logger.debug('Echo response: "%s"', user_text)
        return LlmResult(response=user_text)
