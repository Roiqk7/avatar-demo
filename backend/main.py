import logging
import os
import sys

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from backend.cli import parse_args
from backend.config import Settings
from backend.log import setup_logging
from backend.personalities import load_personality
from backend.personalities.llm_baseline import compose_llm_system_prompt
from backend.pipeline import Pipeline
from backend.services.llm import EchoLlmService, OpenAiChatLlmService
from backend.services.stt import WhisperSttService
from backend.services.tts import AzureTtsService

logger = logging.getLogger("backend.main")


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    if args.test:
        import pytest

        raise SystemExit(pytest.main(["-q", "tests"]))

    if args.test_sprites:
        from backend.rendering.avatar import test_sprites
        test_sprites(args.personality)
        return

    if args.test_animations:
        from backend.rendering.avatar import test_animations
        test_animations(args.personality)
        return

    if args.test_personalities:
        try:
            settings = Settings.load()
        except KeyError as e:
            logger.error("Missing required env var: %s", e)
            logger.error("Copy .env.example to .env and fill in your keys (Azure Speech required for demo TTS)")
            sys.exit(1)
        from backend.rendering.avatar import test_personalities

        test_personalities(args.personality, settings)
        return

    try:
        settings = Settings.load()
    except KeyError as e:
        logger.error("Missing required env var: %s", e)
        logger.error("Copy .env.example to .env and fill in your keys")
        sys.exit(1)

    personality = load_personality(args.personality)
    logger.info("Personality: %s (%s)", personality.id, personality.display_name)

    prompt_body = (personality.llm_system_prompt or settings.llm_system_prompt).strip()
    system_prompt = compose_llm_system_prompt(prompt_body)

    # Assemble services — swap implementations here
    stt = WhisperSttService(api_key=settings.openai_api_key)
    if args.llm_backend == "echo":
        logger.info("LLM backend: ECHO (input is repeated; no Chat Completions call)")
        llm = EchoLlmService(system_prompt=system_prompt)
    else:
        logger.info("LLM backend: OPENAI (model=%s)", settings.llm_model)
        llm = OpenAiChatLlmService(
            api_key=settings.openai_api_key,
            system_prompt=system_prompt,
            model=settings.llm_model,
            max_completion_tokens=settings.llm_max_completion_tokens,
        )
    tts = AzureTtsService(
        speech_key=settings.azure_speech_key,
        speech_region=settings.azure_speech_region,
        voice_name=settings.azure_voice_name,
    )

    pipeline = Pipeline(stt=stt, llm=llm, tts=tts)
    pipeline.run(args, personality)


if __name__ == "__main__":
    main()
