import logging

from openai import OpenAI

from backend.models import ChatTurn, LlmResult

logger: logging.Logger = logging.getLogger("backend.llm")

_DEFAULT_FALLBACK_SYSTEM = "You are a helpful assistant."


class EchoLlmService:
    """Dummy LLM that echoes input as output. Useful for tests and offline debugging."""

    def __init__(self, *, system_prompt: str | None = None) -> None:
        self._system_prompt: str | None = system_prompt

    def generate(self, user_text: str, *, history: list[ChatTurn] | None = None) -> LlmResult:
        if history:
            logger.debug("Echo (history %d turns ignored)", len(history))
        if self._system_prompt:
            logger.debug("Echo (system prompt set, %d chars) user: %s", len(self._system_prompt), user_text[:80])
        logger.debug('Echo response: "%s"', user_text)
        return LlmResult(response=user_text)


class OpenAiChatLlmService:
    """OpenAI Chat Completions: system prompt + user message → assistant reply for the avatar."""

    def __init__(
        self,
        *,
        api_key: str,
        system_prompt: str,
        model: str,
        max_completion_tokens: int | None = None,
    ) -> None:
        self._client: OpenAI = OpenAI(api_key=api_key)
        raw: str = (system_prompt or "").strip()
        self._system_prompt: str = raw if raw else _DEFAULT_FALLBACK_SYSTEM
        self._model: str = model
        self._max_completion_tokens: int | None = max_completion_tokens

    def generate(self, user_text: str, *, history: list[ChatTurn] | None = None) -> LlmResult:
        user: str = user_text.strip()
        if not user:
            logger.debug("Skipping LLM call (empty user message)")
            return LlmResult(response="", prompt_tokens=0, completion_tokens=0)

        prior: list[ChatTurn] = list(history) if history else []
        logger.debug(
            "LLM request model=%s user_chars=%d history_msgs=%d",
            self._model,
            len(user),
            len(prior),
        )

        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        for turn in prior:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role not in ("user", "assistant") or not content:
                continue
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user})

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
        }
        if self._max_completion_tokens is not None:
            kwargs["max_completion_tokens"] = self._max_completion_tokens

        response = self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = (choice.message.content or "").strip()

        usage = response.usage
        prompt_tokens: int = int(usage.prompt_tokens) if usage and usage.prompt_tokens is not None else 0
        completion_tokens: int = (
            int(usage.completion_tokens) if usage and usage.completion_tokens is not None else 0
        )

        if not content and choice.finish_reason == "length":
            logger.warning("LLM hit max_completion_tokens; reply may be truncated")
        elif not content:
            logger.warning("LLM returned empty content (finish_reason=%s)", choice.finish_reason)

        logger.debug('LLM response: "%s"', content[:120])
        return LlmResult(response=content, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
