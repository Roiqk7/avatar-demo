from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable
import io
import wave
from xml.sax.saxutils import escape as _xml_escape

from backend.models import TtsResult, VisemeEvent
from backend.services.lang_detect import DetectedLanguage


@dataclass(frozen=True, slots=True)
class TextSegment:
    text: str
    language: str | None


_CLAUSE_RE = re.compile(r".+?(?:[.!?]+|[,;:]+|\n+|$)", flags=re.DOTALL)

# Unicode-ish “word” definition without external deps (good enough for cs/en mix).
# - includes Latin letters with diacritics up to 'ž' (covers Czech/Slovak, most EU Latin scripts)
# - allows apostrophes inside words
_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž]+(?:'[A-Za-zÀ-ÖØ-öø-ÿĀ-ž]+)?", flags=re.UNICODE)


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def segment_text_by_language(
    text: str,
    *,
    detect_language: Callable[[str], DetectedLanguage | None] | None,
    min_words_detect: int = 3,
    max_detect_calls: int = 6,
) -> list[TextSegment]:
    """Split text into ordered language segments.

    Rules:
    - Only detect language for clauses with >= min_words_detect words.
    - Clauses with < min_words_detect words inherit the previous segment language.
      If there is no previous segment language, they merge into the next detected segment.
    - Adjacent segments with the same resolved language are merged.
    - If the number of detection calls would exceed max_detect_calls, return a single segment (language=None).
    """
    raw = (text or "").strip()
    if not raw:
        return []

    clauses = [m.group(0) for m in _CLAUSE_RE.finditer(raw)]
    if not clauses:
        clauses = [raw]

    detectable = [c for c in clauses if _word_count(c) >= min_words_detect]
    if detect_language is None or len(detectable) > max_detect_calls:
        return [TextSegment(text=raw, language=None)]

    pieces: list[TextSegment] = []
    for c in clauses:
        if _word_count(c) < min_words_detect:
            pieces.append(TextSegment(text=c, language=None))
            continue
        detected = detect_language(c)
        lang = detected.language if detected else None
        pieces.append(TextSegment(text=c, language=(lang or None)))

    # Resolve short prefixes (<3 words with no previous lang): merge into next detected segment.
    pending_prefix = ""
    resolved: list[TextSegment] = []
    prev_lang: str | None = None
    for p in pieces:
        if p.language is None:
            if prev_lang is not None:
                resolved.append(TextSegment(text=p.text, language=prev_lang))
            else:
                pending_prefix += p.text
            continue

        if pending_prefix:
            resolved.append(TextSegment(text=pending_prefix + p.text, language=p.language))
            pending_prefix = ""
        else:
            resolved.append(p)
        prev_lang = p.language

    if pending_prefix:
        # All segments were short; keep the whole utterance as-is.
        if resolved:
            last = resolved[-1]
            resolved[-1] = TextSegment(text=last.text + pending_prefix, language=last.language)
        else:
            resolved.append(TextSegment(text=pending_prefix, language=None))

    # Merge adjacent segments with identical language.
    merged: list[TextSegment] = []
    for seg in resolved:
        if not merged:
            merged.append(seg)
            continue
        prev = merged[-1]
        if prev.language == seg.language:
            merged[-1] = TextSegment(text=prev.text + seg.text, language=prev.language)
        else:
            merged.append(seg)

    return merged


@dataclass(frozen=True, slots=True)
class WavPcm:
    num_channels: int
    sample_rate: int
    sample_width_bytes: int
    pcm_data: bytes
    duration_ms: float


def stitch_tts_results(results: Iterable[TtsResult]) -> TtsResult:
    """Concatenate multiple Azure PCM WAV results into one WAV and merge viseme offsets."""
    results_list = [r for r in results if r and r.audio_data]
    if not results_list:
        return TtsResult(audio_data=b"", visemes=[], duration_ms=0.0, characters_synthesized=0)

    parsed: list[WavPcm] = []
    for r in results_list:
        with wave.open(io.BytesIO(r.audio_data), "rb") as wf:
            nch = wf.getnchannels()
            rate = wf.getframerate()
            sw = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
            dur = wf.getnframes() / max(1, rate) * 1000.0
            parsed.append(WavPcm(num_channels=nch, sample_rate=rate, sample_width_bytes=sw, pcm_data=frames, duration_ms=dur))

    base = parsed[0]
    for p in parsed[1:]:
        if (p.sample_rate, p.num_channels, p.sample_width_bytes) != (base.sample_rate, base.num_channels, base.sample_width_bytes):
            raise ValueError("WAV formats do not match; cannot stitch")

    pcm = b"".join(p.pcm_data for p in parsed)
    out_buf = io.BytesIO()
    with wave.open(out_buf, "wb") as wf_out:
        wf_out.setnchannels(base.num_channels)
        wf_out.setframerate(base.sample_rate)
        wf_out.setsampwidth(base.sample_width_bytes)
        wf_out.writeframes(pcm)
    wav = out_buf.getvalue()

    merged_visemes: list[VisemeEvent] = []
    offset_ms = 0.0
    for r, p in zip(results_list, parsed, strict=True):
        for v in r.visemes:
            merged_visemes.append(VisemeEvent(id=v.id, offset_ms=float(v.offset_ms) + offset_ms))
        offset_ms += float(p.duration_ms or 0.0)

    duration_ms = sum(p.duration_ms for p in parsed)
    chars = sum(int(r.characters_synthesized or 0) for r in results_list)

    return TtsResult(audio_data=wav, visemes=merged_visemes, duration_ms=duration_ms, characters_synthesized=chars)


_VOICE_LOCALE_RE = re.compile(r"^([a-z]{2,3}-[A-Z]{2})-")


def _voice_to_locale(voice_name: str, fallback: str = "en-US") -> str:
    m = _VOICE_LOCALE_RE.match((voice_name or "").strip())
    return m.group(1) if m else fallback


def _segments_cover_text(raw: str, segments: list[TextSegment]) -> bool:
    return "".join(s.text for s in segments) == raw


def _build_voice_switch_ssml(*, text: str, voices_by_segment: list[tuple[str, str]]) -> tuple[str, int]:
    """Return (ssml, characters_synthesized) for Azure speak_ssml.

    voices_by_segment: [(voice_name, segment_text)] in order. segment_text must cover full text.
    """
    # Use a stable top-level xml:lang (Azure still respects per-voice selection).
    top_locale = _voice_to_locale(voices_by_segment[0][0]) if voices_by_segment else "en-US"

    body_parts: list[str] = []
    chars = 0
    for voice, seg_text in voices_by_segment:
        # Keep punctuation/spacing, but avoid newlines that can confuse SSML parsing.
        normalized = (seg_text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\n", " ")
        chars += len(normalized)
        body_parts.append(f'<voice name="{_xml_escape(voice)}">{_xml_escape(normalized)}</voice>')

    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{top_locale}">'
        + "".join(body_parts)
        + "</speak>"
    )
    return (ssml, chars)


def synthesize_mixed_language_ssml(
    text: str,
    *,
    session_id: str,
    fallback_voice: str,
    detect_language: Callable[[str], DetectedLanguage | None] | None,
    resolve_voice: Callable[[str, str | None, str], str],
    get_tts: Callable[[str], object],
    max_detect_calls: int = 6,
) -> tuple[TtsResult, str | None]:
    """Synthesize one continuous TTS stream with per-language voices via a single SSML call.

    This is intentionally conservative: if anything looks off, it falls back to single-voice synthesis
    of the full text (never partial output).
    """
    raw = (text or "").strip()
    if not raw:
        return (TtsResult(audio_data=b"", visemes=[], duration_ms=0.0), None)

    segments = segment_text_by_language(raw, detect_language=detect_language, max_detect_calls=max_detect_calls)
    if not segments:
        return (TtsResult(audio_data=b"", visemes=[], duration_ms=0.0), None)
    if not _segments_cover_text(raw, segments):
        # Safety net: never speak partial output.
        voice = resolve_voice(session_id, None, fallback_voice)
        tts = get_tts(voice)
        chunk: TtsResult = tts.synthesize(raw)  # type: ignore[attr-defined]
        return (chunk, voice)

    voices: list[str] = []
    voices_by_segment: list[tuple[str, str]] = []
    for seg in segments:
        voice = resolve_voice(session_id, seg.language, fallback_voice)
        voices.append(voice)
        voices_by_segment.append((voice, seg.text))

    ssml, chars = _build_voice_switch_ssml(text=raw, voices_by_segment=voices_by_segment)

    # Use any cached TTS instance (voice in SSML overrides per segment).
    tts = get_tts(fallback_voice)
    out: TtsResult = tts.synthesize_ssml(ssml, characters_synthesized=chars)  # type: ignore[attr-defined]

    uniq = list(dict.fromkeys(voices))
    voice_used = uniq[0] if len(uniq) == 1 else "mixed"
    return (out, voice_used)


def synthesize_mixed_language(
    text: str,
    *,
    session_id: str,
    fallback_voice: str,
    detect_language: Callable[[str], DetectedLanguage | None] | None,
    resolve_voice: Callable[[str, str | None, str], str],
    get_tts: Callable[[str], object],
    max_detect_calls: int = 6,
) -> tuple[TtsResult, str | None]:
    """Synthesize one continuous TTS stream with per-language voices.

    Returns: (tts_result, voice_used)
    - voice_used is either a single voice name or 'mixed' when multiple voices were used.
    """
    segments = segment_text_by_language(text, detect_language=detect_language, max_detect_calls=max_detect_calls)
    if not segments:
        return (TtsResult(audio_data=b"", visemes=[], duration_ms=0.0), None)

    voices: list[str] = []
    chunks: list[TtsResult] = []
    for seg in segments:
        voice = resolve_voice(session_id, seg.language, fallback_voice)
        voices.append(voice)
        tts = get_tts(voice)
        # AzureTtsService.synthesize signature
        chunk: TtsResult = tts.synthesize(seg.text)  # type: ignore[attr-defined]
        chunks.append(chunk)

    stitched = stitch_tts_results(chunks)
    uniq = list(dict.fromkeys(voices))
    voice_used = uniq[0] if len(uniq) == 1 else "mixed"
    return (stitched, voice_used)

