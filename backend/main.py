import logging
import os
import sys

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from backend.cli import parse_args
from backend.config import Settings
from backend.log import setup_logging
from backend.pipeline import Pipeline
from backend.services.llm import EchoLlmService
from backend.services.stt import WhisperSttService
from backend.services.tts import AzureTtsService

logger = logging.getLogger("backend.main")


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    if args.test_sprites:
        from backend.rendering.avatar import test_sprites
        test_sprites()
        return

    try:
        settings = Settings.load()
    except KeyError as e:
        logger.error("Missing required env var: %s", e)
        logger.error("Copy .env.example to .env and fill in your keys")
        sys.exit(1)

    logger.info("System ready")

    # Assemble services — swap implementations here
    stt = WhisperSttService(api_key=settings.openai_api_key)
    llm = EchoLlmService()
    tts = AzureTtsService(
        speech_key=settings.azure_speech_key,
        speech_region=settings.azure_speech_region,
        voice_name=settings.azure_voice_name,
    )

    pipeline = Pipeline(stt=stt, llm=llm, tts=tts)
    pipeline.run(args)


if __name__ == "__main__":
    main()
