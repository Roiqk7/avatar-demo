import json
import logging
import os
from pathlib import Path

from backend.cli import Args
from backend.models import PipelineResult, TtsResult
from backend.services import LlmService, SttService, TtsService

logger: logging.Logger = logging.getLogger("backend.pipeline")


class Pipeline:
    """Orchestrates: input -> STT -> LLM -> TTS, then hands off to rendering."""

    def __init__(self, stt: SttService, llm: LlmService, tts: TtsService) -> None:
        self._stt: SttService = stt
        self._llm: LlmService = llm
        self._tts: TtsService = tts

    def _safe_synthesize(self, text: str) -> TtsResult:
        """Run TTS, returning empty result on failure so the pipeline continues."""
        try:
            result: TtsResult = self._tts.synthesize(text)
            logger.info("[TTS] OK — %.1fs, %d visemes", result.duration_ms / 1000, len(result.visemes))
            return result
        except Exception as e:
            logger.info("[TTS] Failed (use --log-level DEBUG for details)")
            logger.debug("TTS error details: %s", e)
            return TtsResult(audio_data=b"", visemes=[], duration_ms=0.0)

    def process_text(self, text: str) -> PipelineResult:
        """Run the full pipeline from text input (skipping STT)."""
        logger.info("[STT] Skipped (text input)")
        llm_result = self._llm.generate(text)
        logger.info('[LLM] OK — "%s"', llm_result.response[:80])
        tts_result = self._safe_synthesize(llm_result.response)

        result = PipelineResult(user_text=text, response_text=llm_result.response, tts=tts_result)
        self._log_summary(result)
        return result

    def process_audio(self, audio_path: str) -> PipelineResult:
        """Run the full pipeline from an audio file (STT -> LLM -> TTS)."""
        path: Path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        audio_format: str = path.suffix.lstrip(".")
        audio_data: bytes = path.read_bytes()
        logger.debug("Loaded audio file: %s (%d bytes)", path.name, len(audio_data))

        stt_result = self._stt.transcribe(audio_data, audio_format)
        logger.info('[STT] OK — "%s"', stt_result.text[:80])
        llm_result = self._llm.generate(stt_result.text)
        logger.info('[LLM] OK — "%s"', llm_result.response[:80])
        tts_result = self._safe_synthesize(llm_result.response)

        result = PipelineResult(user_text=stt_result.text, response_text=llm_result.response, tts=tts_result)
        self._log_summary(result)
        return result

    def process_file(self, file_path: str) -> list[PipelineResult]:
        """Run the pipeline for each non-empty line in a text file."""
        path: Path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Text file not found: {file_path}")

        lines: list[str] = [
            line.strip() for line in path.read_text().splitlines() if line.strip()
        ]
        logger.info("Loaded %d lines from %s", len(lines), path.name)

        results: list[PipelineResult] = []
        for i, line in enumerate(lines, 1):
            logger.info("Processing line %d/%d: %s", i, len(lines), line[:60])
            results.append(self.process_text(line))

        return results

    def run(self, args: Args) -> None:
        """Run the pipeline based on CLI arguments."""
        from backend.rendering.audio import play_audio

        if args.text:
            result: PipelineResult = self.process_text(args.text)
            self._output_result(result, args)
            if args.render:
                from backend.rendering.avatar import render_avatar
                render_avatar(result)
            else:
                play_audio(result.tts)

        elif args.audio:
            result = self.process_audio(args.audio)
            self._output_result(result, args)
            if args.render:
                from backend.rendering.avatar import render_avatar
                render_avatar(result)
            else:
                play_audio(result.tts)

        elif args.file:
            results: list[PipelineResult] = self.process_file(args.file)
            for r in results:
                self._output_result(r, args)
                if args.render:
                    from backend.rendering.avatar import render_avatar
                    render_avatar(r)
                else:
                    play_audio(r.tts)

        else:
            self._interactive(args)

    def _interactive(self, args: Args) -> None:
        """Interactive text input loop."""
        from backend.rendering.audio import play_audio

        logger.info("Interactive mode — type a message, or 'quit' to exit")
        while True:
            try:
                user_input: str = input("\nYou > ").strip()
            except (EOFError, KeyboardInterrupt):
                logger.info("Exiting")
                break

            if not user_input or user_input.lower() in ("quit", "exit", "q"):
                logger.info("Exiting")
                break

            result: PipelineResult = self.process_text(user_input)
            self._output_result(result, args)

            if args.render:
                from backend.rendering.avatar import render_avatar
                render_avatar(result)
            else:
                play_audio(result.tts)

    @staticmethod
    def _log_summary(result: PipelineResult) -> None:
        """Log a clean summary of the pipeline result."""
        has_audio: bool = len(result.tts.audio_data) > 0
        audio_info: str = f"{result.tts.duration_ms / 1000:.1f}s, {len(result.tts.visemes)} visemes" if has_audio else "None"
        logger.info("———")
        logger.info('Input:  "%s"', result.user_text)
        logger.info('Output: "%s"', result.response_text)
        logger.info("Audio:  %s", audio_info)

    @staticmethod
    def _output_result(result: PipelineResult, args: Args) -> None:
        """Save pipeline output to disk if --output is specified."""
        if not args.output:
            return

        out_dir: Path = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)

        audio_path: Path = out_dir / "output.wav"
        audio_path.write_bytes(result.tts.audio_data)
        logger.info("Saved audio to %s", audio_path)

        viseme_data: list[dict[str, float | int]] = [
            {"id": v.id, "offset_ms": v.offset_ms} for v in result.tts.visemes
        ]
        viseme_path: Path = out_dir / "visemes.json"
        viseme_path.write_text(json.dumps(viseme_data, indent=2))
        logger.info("Saved viseme data to %s", viseme_path)
