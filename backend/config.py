import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Middle section only; header/footer are added by compose_llm_system_prompt() in main.
_DEFAULT_LLM_SYSTEM_PROMPT = (
    "You are a generic Signosoft demo assistant. Be clear, friendly, and accurate. "
    "Do not impersonate any real person or fictional character."
)


def _llm_max_completion_tokens() -> int:
    raw: str = os.getenv("LLM_MAX_COMPLETION_TOKENS", "").strip()
    if not raw:
        return 512
    return max(1, int(raw))


@dataclass(frozen=True)
class Settings:
    """Application configuration loaded from .env file."""

    openai_api_key: str
    azure_speech_key: str
    azure_speech_region: str
    azure_voice_name: str
    azure_translator_key: str | None
    azure_translator_region: str | None
    azure_translator_endpoint: str
    llm_system_prompt: str
    llm_model: str
    llm_max_completion_tokens: int

    @staticmethod
    def load() -> "Settings":
        """Load settings from .env file. Raises KeyError for missing required vars."""
        load_dotenv()
        return Settings(
            openai_api_key=os.environ["OPENAI_API_KEY"],
            azure_speech_key=os.environ["AZURE_SPEECH_KEY"],
            azure_speech_region=os.getenv("AZURE_SPEECH_REGION", "eastus"),
            azure_voice_name=os.getenv("AZURE_VOICE_NAME", "en-US-GuyNeural"),
            azure_translator_key=os.getenv("AZURE_TRANSLATOR_KEY", "").strip() or None,
            azure_translator_region=os.getenv("AZURE_TRANSLATOR_REGION", "").strip() or None,
            azure_translator_endpoint=os.getenv(
                "AZURE_TRANSLATOR_ENDPOINT",
                "https://api.cognitive.microsofttranslator.com",
            ).strip(),
            llm_system_prompt=os.getenv("LLM_SYSTEM_PROMPT", _DEFAULT_LLM_SYSTEM_PROMPT),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_max_completion_tokens=_llm_max_completion_tokens(),
        )
