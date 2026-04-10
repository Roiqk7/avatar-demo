import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Application configuration loaded from .env file."""

    openai_api_key: str
    azure_speech_key: str
    azure_speech_region: str
    azure_voice_name: str
    llm_system_prompt: str

    @staticmethod
    def load() -> "Settings":
        """Load settings from .env file. Raises KeyError for missing required vars."""
        load_dotenv()
        return Settings(
            openai_api_key=os.environ["OPENAI_API_KEY"],
            azure_speech_key=os.environ["AZURE_SPEECH_KEY"],
            azure_speech_region=os.getenv("AZURE_SPEECH_REGION", "eastus"),
            azure_voice_name=os.getenv("AZURE_VOICE_NAME", "en-US-JennyNeural"),
            llm_system_prompt=os.getenv("LLM_SYSTEM_PROMPT", "You are a helpful assistant."),
        )
