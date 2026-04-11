import json
import logging
import os
from pathlib import Path

from backend.cli import Args
from backend.models import PipelineResult, SessionUsage, TtsResult
from backend.personalities import Personality
from backend.services import LlmService, SttService, TtsService

# OpenAI Whisper pricing: $0.006 per minute of audio
_WHISPER_COST_PER_MS: float = 0.006 / 60_000
# Azure Neural TTS pricing: $16 per 1M characters
_AZURE_TTS_COST_PER_CHAR: float = 16.0 / 1_000_000

logger: logging.Logger = logging.getLogger("backend.pipeline")


class Pipeline:
    """Orchestrates: input -> STT -> LLM -> TTS, then hands off to rendering."""

    def __init__(self, stt: SttService, llm: LlmService, tts: TtsService) -> None:
        self._stt: SttService = stt
        self._llm: LlmService = llm
        self._tts: TtsService = tts
        self._usage: SessionUsage = SessionUsage()

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

        result = PipelineResult(
            user_text=text,
            response_text=llm_result.response,
            tts=tts_result,
            llm_prompt_tokens=llm_result.prompt_tokens,
            llm_completion_tokens=llm_result.completion_tokens,
        )
        self._log_summary(result)
        self._usage.add(result)
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

        result = PipelineResult(
            user_text=stt_result.text,
            response_text=llm_result.response,
            tts=tts_result,
            stt_duration_ms=stt_result.duration_ms,
            llm_prompt_tokens=llm_result.prompt_tokens,
            llm_completion_tokens=llm_result.completion_tokens,
        )
        self._log_summary(result)
        self._usage.add(result)
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

    def run(self, args: Args, personality: Personality) -> None:
        """Run the pipeline based on CLI arguments."""
        from backend.rendering.audio import play_audio

        if args.text:
            result: PipelineResult = self.process_text(args.text)
            self._output_result(result, args)
            if args.render:
                from backend.rendering.avatar import render_avatar
                render_avatar(result, personality)
            else:
                play_audio(result.tts)

        elif args.audio:
            result = self.process_audio(args.audio)
            self._output_result(result, args)
            if args.render:
                from backend.rendering.avatar import render_avatar
                render_avatar(result, personality)
            else:
                play_audio(result.tts)

        elif args.file:
            results: list[PipelineResult] = self.process_file(args.file)
            for r in results:
                self._output_result(r, args)
                if args.render:
                    from backend.rendering.avatar import render_avatar
                    render_avatar(r, personality)
                else:
                    play_audio(r.tts)

        else:
            self._interactive(args, personality)

        self._print_usage_report()

    def _interactive(self, args: Args, personality: Personality) -> None:
        """Interactive text input loop."""
        if args.render:
            self._interactive_render(args, personality)
        else:
            self._interactive_text(args)

    def _interactive_text(self, args: Args) -> None:
        """Interactive loop without avatar — just plays audio."""
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
            play_audio(result.tts)

    def _interactive_render(self, args: Args, personality: Personality) -> None:
        """Interactive loop with a persistent avatar window.

        Pygame must run on the main thread (macOS requirement), so we read
        stdin on a daemon thread and feed results to the avatar window via
        its thread-safe :meth:`play` method.
        """
        import threading

        from backend.rendering.avatar import AvatarWindow

        window = AvatarWindow(personality)
        if not window.ready:
            logger.warning("Avatar assets not found — falling back to text mode")
            self._interactive_text(args)
            return

        logger.info("Interactive mode (avatar) — type a message, or 'quit' to exit")

        def _input_loop() -> None:
            """Read stdin in a background thread, process, enqueue results."""
            while True:
                try:
                    user_input: str = input("\nYou > ").strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not user_input or user_input.lower() in ("quit", "exit", "q"):
                    break

                result: PipelineResult = self.process_text(user_input)
                self._output_result(result, args)
                window.play(result)

            logger.info("Exiting")
            window.request_close()

        input_thread = threading.Thread(target=_input_loop, daemon=True)
        input_thread.start()

        # Main thread — runs the pygame render loop until closed.
        window.run_forever()

    def _print_usage_report(self) -> None:
        """Print a session-wide API usage and estimated cost summary."""
        u = self._usage
        if u.call_count == 0:
            return

        stt_seconds: float = u.stt_audio_ms / 1000
        stt_cost: float = u.stt_audio_ms * _WHISPER_COST_PER_MS
        llm_total_tokens: int = u.llm_prompt_tokens + u.llm_completion_tokens
        tts_cost: float = u.tts_characters * _AZURE_TTS_COST_PER_CHAR
        total_cost: float = stt_cost + tts_cost

        logger.info("─── Usage (%d call%s) ───", u.call_count, "" if u.call_count == 1 else "s")
        if stt_seconds > 0:
            logger.info("STT  %7.1f s audio   ~$%.4f", stt_seconds, stt_cost)
        else:
            logger.info("STT  — (text input only)")
        if llm_total_tokens > 0:
            logger.info(
                "LLM  %7d tokens  ~$%.4f  (%d prompt + %d completion)",
                llm_total_tokens, 0.0, u.llm_prompt_tokens, u.llm_completion_tokens,
            )
        else:
            logger.info("LLM  — (echo, no API calls)")
        logger.info("TTS  %7d chars   ~$%.4f", u.tts_characters, tts_cost)
        logger.info("Total                ~$%.4f", total_cost)
        logger.info("Note: costs are estimates based on standard pricing and may not reflect your actual billing (e.g. free tier).")

    @staticmethod
    def _log_summary(result: PipelineResult) -> None:
        """Log a clean summary of the pipeline result."""
        has_audio: bool = len(result.tts.audio_data) > 0
        audio_info: str = f"{result.tts.duration_ms / 1000:.1f}s, {len(result.tts.visemes)} visemes" if has_audio else "None"
        logger.info("─── Result ───")
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
