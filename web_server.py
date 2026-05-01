"""FastAPI web server for the Avatar Demo.

Exposes the existing pipeline over HTTP and serves a Canvas-based frontend.

Usage:
    pip install fastapi uvicorn python-multipart
    python web_server.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import re
from urllib.parse import urlparse

# Add project root to path so backend imports work
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
except Exception:  # optional dependency for local testing
    Limiter = None  # type: ignore[assignment]

    class RateLimitExceeded(Exception):
        pass

    def get_remote_address(_request: Request) -> str:  # type: ignore[override]
        return "0.0.0.0"

    def _rate_limit_exceeded_handler(_request: Request, _exc: Exception):
        raise HTTPException(429, "Rate limit exceeded")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from backend.config import Settings
from backend.log import setup_logging
from backend.models import ChatTurn, PipelineResult, TtsResult
from backend.personalities import list_personality_ids, load_personality, Personality
from backend.personalities.llm_baseline import compose_llm_system_prompt
from backend.services.llm import EchoLlmService, OpenAiChatLlmService
from backend.services.lang_detect import AzureTranslatorLanguageDetectService, DetectedLanguage
from backend.services.stt import WhisperSttService
from backend.services.tts import AzureTtsService
from backend.services.mixed_language_tts import synthesize_mixed_language_ssml
from backend.services.azure_voice_catalog import AzureSpeechVoiceCatalog
from backend.services.voice_select import choose_voice
from backend.safety.slur_filter import (
    SlurLanguage,
    compile_slur_regex_by_language,
    detect_slur_by_language,
    default_slur_terms_by_language,
)
# Note: rendering/debug catalogs intentionally not imported here to keep server startup
# lightweight and avoid importing optional native dependencies during API-only runs.

setup_logging("INFO")
logger = logging.getLogger("backend.web")

app = FastAPI(title="Avatar Demo")

_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "https://ai-avatar.signosoft.com,http://127.0.0.1:8000,http://localhost:8000,http://localhost:5173",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

if Limiter is None:
    class _NoopLimiter:
        def limit(self, *_a, **_kw):
            def _decorator(fn):
                return fn

            return _decorator

    limiter = _NoopLimiter()
else:
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Globals (initialized on startup) ---
_settings: Settings | None = None
_stt = None
_tts_cache: dict[str, AzureTtsService] = {}
_lang_detect: AzureTranslatorLanguageDetectService | None = None
_voice_catalog: AzureSpeechVoiceCatalog | None = None
# Maps session_id -> {language_code -> voice_name}; pinned for the lifetime of the process.
_session_voice_maps: dict[str, dict[str, str]] = {}
_session_voice_map_timestamps: dict[str, float] = {}
# Maps session_id -> detected language ("cs"/"en"/"pt"); used to select per-session STT prompt.
_session_detected_lang: dict[str, str] = {}
_SESSION_TTL_S = 3600  # 1 hour


@dataclass(slots=True)
class SessionLangState:
    turn_count: int = 0
    pinned_lang: str | None = None  # one of _SUPPORTED_STT_LANGS
    candidate_lang: str | None = None  # last seen candidate (holy trio only)
    candidate_streak: int = 0
    evidence: dict[str, float] | None = None  # accumulates holy-trio scores
    locked_until_turn: int = 0  # for Czech-first stickiness window


# Tracks language pinning evidence/streaks for the first few turns.
_session_lang_state: dict[str, SessionLangState] = {}

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB
_terms_by_lang = default_slur_terms_by_language()
# Backwards-compatible override/extension: comma-separated literal terms.
# These are added to the English bucket (language-agnostic demo override).
_extra_terms = [t.strip() for t in (os.environ.get("AVATAR_DEMO_SLUR_TERMS") or "").split(",") if t.strip()]
if _extra_terms:
    _terms_by_lang = {**_terms_by_lang, "en": [*_terms_by_lang.get("en", []), *_extra_terms]}
_slur_regex_by_lang = compile_slur_regex_by_language(_terms_by_lang)

ASSETS_DIR = PROJECT_ROOT / "assets"

KIND_SYSTEM_PROMPT_BY_LANG: dict[SlurLanguage, str] = {
    "en": (
        "You are a friendly avatar assistant. The user used insulting or hateful language.\n"
        "Respond briefly, calmly, and firmly. Ask them to be kind and to rephrase without insults.\n"
        "Do not repeat or quote slurs. Keep it to 1–2 sentences."
    ),
    "cs": (
        "Jsi přátelský avatar asistent. Uživatel použil urážlivý nebo nenávistný jazyk.\n"
        "Odpověz stručně, klidně a pevně. Požádej o slušnost a ať to přeformuluje bez urážek.\n"
        "Neopakuj ani necituj nadávky. 1–2 věty."
    ),
}

KIND_FALLBACK_TEXT_BY_LANG: dict[SlurLanguage, str] = {
    "en": "Please be kind. If you're upset, tell me what's going on without insults.",
    "cs": "Prosím, buď slušný. Pokud jsi naštvaný, řekni mi, co se děje, bez urážek.",
}

LISTENING_MODE_PROMPT_ADDENDUM = (
    "Context: The user input comes from a microphone in an interactive listening mode (speech-to-text).\n"
    "- Transcription may contain mistakes, missing punctuation, or cutoffs.\n"
    "- The user may interrupt (barge in). The newest user utterance is authoritative.\n"
    "- Keep replies brief and interruption-friendly (1–3 spoken sentences unless asked otherwise)."
)

# Extra context for Max mode: model is expected to orchestrate within the demo pipeline.
MAX_MODE_SYSTEM_ADDENDUM = (
    "You are part of the Signosoft Avatar Demo pipeline. You are the brain of the pipeline as you are "
    "the one who generates the response to the user's input. So please be professional Signosoft Assistant."
    "Because the STT is not perfect, you may need to correct the transcription. Please do not mention this to the user."
    "Correct possible transcription errors based on the full conversation context in case the input is messy."
    "Please format replies in Markdown when helpful (e.g., **bold**, lists, `inline code`, links, etc.)."
    "Please keep the language of the response the same as the language of the user's input."
    "Here is link to Signosoft website for more information: https://signosoft.com. Link it frequently in your responses."
    
)

# Per-language STT prompts used once session language is known.
# Instruction-only — NO vocabulary hints here. The language= param already forces the language;
# vocab hints in the prompt cause leakage when audio is ambiguous or silent.
_STT_PROMPT_BY_LANG: dict[str, str] = {
    "cs": "Transcribe in Czech. Never output Polish or Slovak.",
    "en": "Transcribe in English.",
    "pt": "Transcribe in Portuguese.",
}

# ISO 639-1 codes accepted by the STT language parameter.
_SUPPORTED_STT_LANGS: frozenset[str] = frozenset({"cs", "en", "pt"})

# Slavic languages that are acoustically/lexically close to Czech.
# Low-confidence detections of these are almost always Czech being misidentified.
_SLAVIC_LANGS: frozenset[str] = frozenset({"sk", "pl", "bs", "hr", "sr", "sl", "mk", "bg", "uk", "be", "ru"})

# Confidence thresholds for smart language switching.
_CONF_HIGH = 0.90   # 90%+ → trust non-holy-trio detection; don't override
_CONF_SLAVIC = 0.85 # <85% Slavic → treat as Czech misidentification


def _resolve_session_language(detected_lang: str, detected_score: float) -> str | None:
    """Map a raw detection result to the language we should pin to this session.

    Returns a language code to store, or None to leave the session unpinned.

    Rules (evaluated in order):
    1. Holy trio (cs/en/pt) always stored as-is — no threshold needed.
    2. Score >= 90% on non-trio → user is genuinely speaking another language; don't override.
       Return None so the session stays unpinned and STT auto-detects naturally.
    3. Slavic non-trio + score < 85% → almost certainly Czech being misidentified.
       Hard-switch to Czech.
    4. Anything else below the high-confidence bar → English as safe fallback.
    """
    if detected_lang in _SUPPORTED_STT_LANGS:
        return detected_lang
    if detected_score >= _CONF_HIGH:
        return None  # Confident other language — respect it, don't override
    if detected_lang in _SLAVIC_LANGS and detected_score < _CONF_SLAVIC:
        return "cs"
    return "en"


def _tts_detect_holy_trio_bias(
    text: str,
    *,
    detect_language: Callable[[str], DetectedLanguage | None] | None,
) -> DetectedLanguage | None:
    """Detect language but bias voice selection toward cs/en/pt.

    Unlike session STT pinning, we still allow non-trio languages when confidence is high.
    """
    if detect_language is None:
        return None
    detected = detect_language(text)
    if detected is None:
        return None
    lang_raw = (detected.language or "").strip().lower()
    score = float(detected.score or 0.0)

    if lang_raw in _SUPPORTED_STT_LANGS:
        return detected
    if score >= _CONF_HIGH:
        return detected  # allow confident non-trio for TTS
    if lang_raw in _SLAVIC_LANGS and score < _CONF_SLAVIC:
        return DetectedLanguage(language="cs", score=detected.score)
    return DetectedLanguage(language="en", score=detected.score)


def _update_session_language(session_id: str, detected_lang: str, detected_score: float) -> None:
    """Backward-compatible wrapper: advance one turn, apply one signal, finalize."""
    _advance_session_language_turn(session_id)
    _apply_session_language_signal(session_id, detected_lang, detected_score)
    _finalize_session_language_turn(session_id)


def _get_or_create_session_lang_state(session_id: str) -> SessionLangState | None:
    if not session_id:
        return None
    state = _session_lang_state.get(session_id)
    if state is None:
        state = SessionLangState()
        _session_lang_state[session_id] = state
    return state


def _commit_session_language(session_id: str, state: SessionLangState, lang: str) -> None:
    state.pinned_lang = lang
    _session_detected_lang[session_id] = lang
    _session_voice_map_timestamps[session_id] = time.time()


def _advance_session_language_turn(session_id: str) -> None:
    state = _get_or_create_session_lang_state(session_id)
    if state is None:
        return
    state.turn_count += 1


def _apply_session_language_signal(session_id: str, detected_lang: str, detected_score: float) -> None:
    """Apply one detection signal within the current turn (does not advance turn_count)."""
    state = _get_or_create_session_lang_state(session_id)
    if state is None:
        return

    # Best-effort normalization
    lang_raw = (detected_lang or "").strip().lower()
    score = float(detected_score or 0.0)

    # Map raw detection into a holy-trio candidate (or None => don't pin).
    candidate = _resolve_session_language(lang_raw, score)

    # Track evidence for holy-trio candidates only.
    if candidate in _SUPPORTED_STT_LANGS:
        if state.evidence is None:
            state.evidence = {"cs": 0.0, "en": 0.0, "pt": 0.0}
        state.evidence[candidate] = float(state.evidence.get(candidate, 0.0)) + score

    # Update streak tracking only for holy-trio candidates.
    if candidate in _SUPPORTED_STT_LANGS:
        if state.candidate_lang == candidate:
            state.candidate_streak += 1
        else:
            state.candidate_lang = candidate
            state.candidate_streak = 1
    else:
        # Non-trio / don't-pin signal breaks streak.
        state.candidate_lang = None
        state.candidate_streak = 0

    # Turn-1 Czech-first: immediate pin + sticky window.
    if state.turn_count == 1 and candidate == "cs":
        state.locked_until_turn = 4
        _commit_session_language(session_id, state, "cs")
        return

    # If unpinned, allow fast pinning but require confirmation for non-Czech.
    if state.pinned_lang is None:
        if candidate == "cs":
            # Czech can pin immediately even beyond turn 1.
            _commit_session_language(session_id, state, "cs")
        elif candidate in ("en", "pt"):
            if state.candidate_streak >= 2:
                _commit_session_language(session_id, state, candidate)

    # Early switching: in first 4 turns we allow corrections.
    # Czech is sticky through locked_until_turn.
    if state.pinned_lang == "cs" and state.turn_count <= max(1, state.locked_until_turn):
        # Require 2-in-a-row AND the challenger must beat Czech evidence by a margin.
        if state.candidate_lang in ("en", "pt") and state.candidate_streak >= 2:
            ev = state.evidence or {"cs": 0.0, "en": 0.0, "pt": 0.0}
            challenger = state.candidate_lang
            margin = 0.2
            if ev.get(challenger, 0.0) > ev.get("cs", 0.0) + margin:
                _commit_session_language(session_id, state, challenger)
    elif state.pinned_lang in ("en", "pt") and state.turn_count <= 4:
        if state.candidate_lang in _SUPPORTED_STT_LANGS and state.candidate_lang != state.pinned_lang:
            if state.candidate_streak >= 2:
                _commit_session_language(session_id, state, state.candidate_lang)


def _finalize_session_language_turn(session_id: str) -> None:
    """Finalize the current turn (e.g. enforce 'pinned by turn 4')."""
    state = _get_or_create_session_lang_state(session_id)
    if state is None:
        return

    if state.turn_count >= 4 and state.pinned_lang is None:
        ev = state.evidence or {"cs": 0.0, "en": 0.0, "pt": 0.0}
        # Choose highest evidence; tie-breaker defaults to Czech-first.
        best = max(
            ("cs", "en", "pt"),
            key=lambda k: (ev.get(k, 0.0), 1 if k == "cs" else 0),
        )
        _commit_session_language(session_id, state, best)


def _get_stt_context(session_id: str) -> tuple[str | None, str | None]:
    """Return (prompt_override, language_override) for this session.

    Once the session language is known, both the prompt AND the language parameter
    are set — double-enforcement to prevent cross-language confusion (e.g. Czech → Polish).
    First call always uses default multilingual prompt with no forced language.
    """
    lang = _session_detected_lang.get(session_id)
    if not lang or lang not in _SUPPORTED_STT_LANGS:
        return None, None
    return _STT_PROMPT_BY_LANG.get(lang), lang


def _maybe_add_interaction_context(system_prompt: str, interaction_mode: str | None) -> str:
    mode = (interaction_mode or "").strip().lower()
    if mode != "listening":
        return system_prompt
    base = (system_prompt or "").strip()
    return f"{base}\n\n{LISTENING_MODE_PROMPT_ADDENDUM}"


# --- Startup ---
@app.on_event("startup")
def startup():
    global _settings, _stt, _lang_detect, _voice_catalog
    try:
        _settings = Settings.load()
        _stt = WhisperSttService(
            api_key=_settings.openai_api_key,
            model=_settings.stt_model,
            language=_settings.stt_language,
            prompt=_settings.stt_prompt,
        )
        _lang_detect = AzureTranslatorLanguageDetectService(
            key=_settings.azure_translator_key,
            region=_settings.azure_translator_region,
            endpoint=_settings.azure_translator_endpoint,
        )
        _voice_catalog = AzureSpeechVoiceCatalog(
            speech_key=_settings.azure_speech_key,
            speech_region=_settings.azure_speech_region,
        )
        _voice_catalog.load()
        logger.info("Settings loaded, STT ready")
    except KeyError as e:
        logger.warning("Missing env var %s — TTS/STT will fail. Copy .env.example → .env", e)
        _settings = None
        _stt = None
        _lang_detect = None
        _voice_catalog = None


def _cleanup_stale_sessions() -> None:
    now = time.time()
    stale = [sid for sid, ts in _session_voice_map_timestamps.items() if now - ts > _SESSION_TTL_S]
    for sid in stale:
        _session_voice_maps.pop(sid, None)
        _session_voice_map_timestamps.pop(sid, None)
        _session_detected_lang.pop(sid, None)
        _session_lang_state.pop(sid, None)


def _resolve_voice(session_id: str, detected_language: str | None, fallback_voice: str) -> str:
    """Return a consistent voice for this session+language, picking one on first encounter."""
    _cleanup_stale_sessions()
    _session_voice_map_timestamps[session_id] = time.time()
    lang = (detected_language or "").strip().lower()
    voice_map = _session_voice_maps.setdefault(session_id, {})
    if lang and lang in voice_map:
        return voice_map[lang]
    selection = choose_voice(
        detected_language=detected_language,
        fallback_voice_name=fallback_voice,
        catalog=_voice_catalog,
    )
    if lang:
        voice_map[lang] = selection.voice_name
    return selection.voice_name


def _guess_stt_format(upload: UploadFile) -> str:
    """Best-effort format inference for Whisper.

    We prefer content_type since the filename can be missing or incorrect when produced by browsers.
    """
    ct = (upload.content_type or "").lower().strip()
    if "webm" in ct:
        return "webm"
    if "ogg" in ct or "oga" in ct:
        return "ogg"
    if "wav" in ct:
        return "wav"
    if "mpeg" in ct or "mp3" in ct or "mpga" in ct:
        return "mp3"
    if "mp4" in ct:
        return "mp4"
    if "m4a" in ct:
        return "m4a"

    name = (upload.filename or "").lower()
    m = re.search(r"\.([a-z0-9]{1,6})$", name)
    if m:
        return m.group(1)
    return "webm"


def _get_tts(voice_name: str) -> AzureTtsService:
    if _settings is None:
        raise HTTPException(500, "Server not configured — missing .env keys")
    if voice_name not in _tts_cache:
        _tts_cache[voice_name] = AzureTtsService(
            speech_key=_settings.azure_speech_key,
            speech_region=_settings.azure_speech_region,
            voice_name=voice_name,
        )
    return _tts_cache[voice_name]


LlmBackend = Literal["echo", "openai", "max"]


def _get_llm(llm_backend: LlmBackend, system_prompt: str):
    if llm_backend == "echo":
        return EchoLlmService(system_prompt=system_prompt)
    if llm_backend in ("openai", "max"):
        if _settings is None:
            raise HTTPException(500, "Server not configured — missing .env keys")
        model = "gpt-5.4-mini" if llm_backend == "max" else _settings.llm_model
        return OpenAiChatLlmService(
            api_key=_settings.openai_api_key,
            system_prompt=system_prompt,
            model=model,
            max_completion_tokens=_settings.llm_max_completion_tokens,
        )
    raise HTTPException(400, f"Unsupported llm_backend: {llm_backend}")


def _sanitize_history(history: list[dict] | None) -> list[ChatTurn]:
    """Best-effort validation: keep only {role,user|assistant} turns with non-empty content."""
    if not history:
        return []
    out: list[ChatTurn] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        c = content.strip()
        if not c:
            continue
        out.append({"role": role, "content": c})
    return out


def _slice_history(llm_backend: str, history: list[ChatTurn]) -> list[ChatTurn]:
    mode = (llm_backend or "").strip().lower()
    if mode == "echo":
        return []
    if mode == "openai":
        return history[-3:]
    if mode == "max":
        return history
    return history[-3:]


def _parse_history_form(raw: str | None) -> list[ChatTurn]:
    if not raw:
        return []
    try:
        obj = json.loads(raw)
    except Exception:
        return []
    if not isinstance(obj, list):
        return []
    # pydantic isn't involved for Form fields; sanitize directly.
    return _sanitize_history(obj)


def _build_system_prompt_for_mode(prompt_body: str, *, interaction_mode: str | None, llm_backend: str) -> str:
    base = compose_llm_system_prompt(prompt_body)
    if (llm_backend or "").strip().lower() == "max":
        base = f"{base}\n\n{MAX_MODE_SYSTEM_ADDENDUM}".strip()
    return _maybe_add_interaction_context(base, interaction_mode)


def _cut_after_n_words(text: str, *, n_words: int) -> int | None:
    """Return a safe cut index after the Nth word (at a whitespace boundary), or None."""
    if n_words <= 0:
        return None
    s = text or ""
    it = list(_TTS_WORD_RE.finditer(s))
    if len(it) < n_words:
        return None
    end = it[n_words - 1].end()
    # Prefer to cut at whitespace after the Nth word.
    i = end
    while i < len(s) and not s[i].isspace():
        i += 1
    while i < len(s) and s[i].isspace():
        i += 1
    # We want chunk to end before the remainder starts.
    cut = i
    # Ensure forward progress.
    if cut <= 0 or cut > len(s):
        return None
    return cut


def _pop_tts_chunk_doubling(buf: str, *, target_words: int, force: bool) -> tuple[str | None, str]:
    """Split streaming buffer into (chunk, remainder) using doubling word targets.

    - First chunk aims for >=8 words, then 16, 32, ...
    - Keeps fast start while making later chunks larger/smoother.
    """
    raw = buf or ""
    if not raw.strip():
        return None, ""
    if force:
        return raw.strip(), ""

    s = raw
    # Newlines are strong boundaries: flush the line(s) if we have enough words.
    if "\n" in s:
        parts = s.split("\n", 1)
        chunk = parts[0].strip()
        remainder = parts[1].lstrip() if len(parts) > 1 else ""
        if _word_count_for_tts(chunk) >= max(1, target_words):
            return chunk, remainder
        return None, raw

    cut = _cut_after_n_words(s, n_words=target_words)
    if cut is None:
        return None, raw

    chunk = s[:cut].strip()
    remainder = s[cut:].lstrip()
    if _word_count_for_tts(chunk) < max(1, target_words):
        return None, raw
    return chunk, remainder


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+|www\.[^)]+)\)", flags=re.IGNORECASE)
_URL_RE = re.compile(r"\bhttps?://[^\s<>()]+|\bwww\.[^\s<>()]+", flags=re.IGNORECASE)
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
_TTS_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž0-9]+", flags=re.UNICODE)
_DATE_DMY_RE = re.compile(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\b")
_DATE_DM_RE = re.compile(r"\b(\d{1,2})\.\s*(\d{1,2})\.\b")
_DATE_RANGE_DASH_RE = re.compile(r"\s*[–—-]\s*")
_DATE_RANGE_CONTEXT_RE = re.compile(
    r"(\d{1,2}\s+[A-Za-zÀ-ÖØ-öø-ÿĀ-ž]+(?:\s+\d{4})?)\s*(?:[–—-]|--)\s*(\d{1,2}\s+[A-Za-zÀ-ÖØ-öø-ÿĀ-ž]+(?:\s+\d{4})?)",
    flags=re.UNICODE,
)
_NX_RE = re.compile(r"\b(\d+)\s*[xX]\s*(\d+)\b")
_MUL_SIGN_RE = re.compile(r"\b(\d+)\s*×\s*(\d+)\b")
_MATH_BLOCK_RE = re.compile(r"(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\))", flags=re.UNICODE)


def _times_word_for_lang(lang: str | None) -> str:
    l = (lang or "").strip().lower()
    if l == "cs":
        return "krat"
    if l == "en":
        return "times"
    return "times"

_CZ_MONTHS = {
    1: "leden",
    2: "unor",
    3: "brezen",
    4: "duben",
    5: "kveten",
    6: "cerven",
    7: "cervenec",
    8: "srpen",
    9: "zari",
    10: "rijen",
    11: "listopad",
    12: "prosinec",
}


def _word_count_for_tts(text: str) -> int:
    return len(_TTS_WORD_RE.findall(text or ""))


def _pop_tts_chunk(buf: str, *, min_words: int, force: bool) -> tuple[str | None, str]:
    """Split a streaming buffer into (chunk, remainder) without cutting inside a word.

    - Prefers to split on whitespace boundaries.
    - Enforces min_words unless force=True.
    """
    raw = buf or ""
    if not raw.strip():
        return None, ""

    # If forcing (end of stream), flush all.
    if force:
        return raw.strip(), ""

    # Find last whitespace boundary to avoid cutting within a word.
    s = raw
    cut = -1
    for i in range(len(s) - 1, -1, -1):
        if s[i].isspace():
            cut = i
            break
    if cut <= 0:
        return None, raw

    chunk = s[:cut].strip()
    remainder = s[cut:].lstrip()

    if _word_count_for_tts(chunk) < min_words:
        return None, raw
    return chunk, remainder


def _domain_for_tts(urlish: str) -> str:
    raw = (urlish or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("www."):
        raw = "http://" + raw
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return ""
    host = host.lstrip(".")
    if not _HOST_RE.match(host):
        return ""
    labels = [p for p in host.split(".") if p]
    if not labels:
        return ""
    # Speak domain as tokens with dots, but avoid long subdomain chains.
    core = labels[-2:] if len(labels) >= 2 else labels
    safe_parts: list[str] = []
    for p in core:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "", p)
        if cleaned:
            safe_parts.append(cleaned)
    if not safe_parts:
        return ""
    return " . ".join(safe_parts)


def _sanitize_for_tts(text: str, *, lang_hint: str | None = None) -> str:
    """Produce a TTS-friendly variant: no markdown symbols, emojis, or raw URLs.

    Allowed output chars: letters, digits, space, '.' and ','.
    """
    s = (text or "").strip()
    if not s:
        return ""

    # Strip math blocks entirely so they don't affect language detection or speech.
    s = _MATH_BLOCK_RE.sub(" ", s)
    # Also strip bracket-math style: [ ... ] when it looks like LaTeX.
    s = re.sub(r"\[\s*([\s\S]*?)\s*\]", lambda m: " " if re.search(r"\\[A-Za-z]+|[_^]|\\times|\\left|\\right", m.group(1) or "") else m.group(0), s)

    # Convert Czech-style numeric dates into spoken-ish form for TTS:
    # 17. 7. 1942 -> 17 cervenec 1942
    def _dmy(m: re.Match) -> str:
        d = int(m.group(1))
        mo = int(m.group(2))
        y = int(m.group(3))
        mname = _CZ_MONTHS.get(mo)
        if not mname:
            return f"{d}. {mo}. {y}"
        return f"{d} {mname} {y}"

    s = _DATE_DMY_RE.sub(_dmy, s)

    # Date ranges: replace dash-like separators with " az " only in date-like contexts.
    s = _DATE_RANGE_CONTEXT_RE.sub(r"\1 az \2", s)

    # Also convert day+month without year if present.
    def _dm(m: re.Match) -> str:
        d = int(m.group(1))
        mo = int(m.group(2))
        mname = _CZ_MONTHS.get(mo)
        if not mname:
            return f"{d}. {mo}."
        return f"{d} {mname}"

    s = _DATE_DM_RE.sub(_dm, s)

    # Treat remaining em/en dashes and double-dashes as pauses (after date range handling).
    s = s.replace("—", ". ")
    s = s.replace("–", ". ")
    s = s.replace("--", ". ")

    # 1x50 -> 1 times 50 / 1 krat 50 (avoid reading 'x' as a letter)
    times_word = _times_word_for_lang(lang_hint)
    s = _MUL_SIGN_RE.sub(lambda m: f"{m.group(1)} {times_word} {m.group(2)}", s)
    s = _NX_RE.sub(lambda m: f"{m.group(1)} {times_word} {m.group(2)}", s)

    # Markdown links: keep visible text + domain.
    def _md_link_sub(m: re.Match) -> str:
        label = (m.group(1) or "").strip()
        url = (m.group(2) or "").strip()
        dom = _domain_for_tts(url)
        # Speak link label only if present (domain is for UI, not speech).
        if label:
            return label
        if dom:
            return dom
        return label

    s = _MD_LINK_RE.sub(_md_link_sub, s)

    # Standalone URLs -> domain only.
    def _url_sub(m: re.Match) -> str:
        dom = _domain_for_tts(m.group(0) or "")
        if dom.replace(" ", "") == "signosoft.com":
            return "Signosoft"
        return dom if dom else ""

    s = _URL_RE.sub(_url_sub, s)

    # Strip common markdown formatting markers.
    s = s.replace("**", " ")
    s = s.replace("__", " ")
    s = s.replace("*", " ")
    s = s.replace("_", " ")
    s = s.replace("`", " ")
    s = s.replace("~", " ")
    s = s.replace("#", " ")
    s = s.replace(">", " ")

    # Normalize separators/punctuation to keep sentence cadence.
    s = s.replace("\n", ". ")
    s = re.sub(r"[!?;:]+", ".", s)
    s = re.sub(r"[\(\)\[\]\{\}<>\"“”‘’]+", " ", s)
    s = re.sub(r"[-–—/\\|]+", " ", s)

    # Remove emojis and any other non-allowed characters.
    out_chars: list[str] = []
    for ch in s:
        if ch.isalnum():
            out_chars.append(ch)
            continue
        if ch in (".", ","):
            out_chars.append(ch)
            continue
        if ch.isspace():
            out_chars.append(" ")
            continue
        # drop everything else (including emojis)
    cleaned = "".join(out_chars)

    # Collapse whitespace and repeated punctuation.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = re.sub(r",\s*,+", ",", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",(?=[A-Za-z0-9])", ", ", cleaned)
    cleaned = re.sub(r"\.(?=[A-Za-z0-9])", ". ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


# --- Static files ---
# Avatar sprite images (faces/eyes/visemes).
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    dist_index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if dist_index.exists():
        return dist_index.read_text()
    return (PROJECT_ROOT / "static" / "index.html").read_text()


# --- API Models ---
class TextRequest(BaseModel):
    text: str
    personality_id: str = "peter"
    llm_backend: LlmBackend = "echo"
    session_id: str = ""
    safety_hint_language: SlurLanguage | None = None
    history: list[dict] = []


class VisemeOut(BaseModel):
    id: int
    offset_ms: float


class PipelineResponse(BaseModel):
    user_text: str
    response_text: str
    audio_base64: str
    visemes: list[VisemeOut]
    duration_ms: float
    mood: Literal["neutral", "sad"] = "neutral"
    safety_triggered: bool = False
    safety_language: SlurLanguage | None = None
    detected_language: str | None = None
    detected_language_score: float | None = None
    debug_lang_mode: str | None = None
    debug_session_lang: str | None = None
    voice_used: str | None = None
    debug_voice_mode: str | None = None
    language_detection_enabled: bool = False
    language_detection_error: str | None = None
    debug_stt_model: str | None = None
    debug_stt_language: str | None = None
    debug_llm_backend: str | None = None
    debug_llm_model: str | None = None
    debug_tts_backend: str | None = None
    debug_lang_detect_backend: str | None = None
    timing_stt_ms: float | None = None
    timing_llm_ms: float | None = None
    timing_tts_ms: float | None = None


@app.get("/api/personalities")
def get_personalities():
    """Return all available personalities with their full config for the JS renderer."""
    ids = list_personality_ids()
    out = []
    for pid in ids:
        p = load_personality(pid)
        out.append(_serialize_personality(p))
    return out


def _serialize_personality(p: Personality) -> dict:
    """Serialize a Personality into JSON the frontend can consume."""
    spr_rel = str(p.assets.sprites_root.relative_to(ASSETS_DIR))
    spr_prefix = "" if spr_rel in (".", "") else f"{spr_rel}/"
    return {
        "id": p.id,
        "display_name": p.display_name,
        "window_title": p.window_title,
        "face_layout": {
            "mouth_width_ratio": p.face_layout.mouth_width_ratio,
            "mouth_height_ratio": p.face_layout.mouth_height_ratio,
            "mouth_y_ratio": p.face_layout.mouth_y_ratio,
            "eye_y_ratio": p.face_layout.eye_y_ratio,
            "eye_width_ratio": p.face_layout.eye_width_ratio,
            "eye_height_ratio": p.face_layout.eye_height_ratio,
        },
        "assets": {
            "face_path": f"/assets/{p.assets.face_root.relative_to(ASSETS_DIR)}/{p.assets.face_filename}",
            "visemes_dir": f"/assets/{spr_prefix}{p.assets.visemes_dir}",
            "eyes_dir": f"/assets/{spr_prefix}{p.assets.eyes_dir}",
        },
        "viseme_labels": list(p.effective_viseme_labels),
        "idle_mouth_pools": {
            "subtle": list(p.idle_mouth_pools.subtle),
            "happy": list(p.idle_mouth_pools.happy),
            "goofy": list(p.idle_mouth_pools.goofy),
            "dramatic": list(p.idle_mouth_pools.dramatic),
        },
        "idle_mouth_names": list(p.all_idle_mouth_asset_names()),
        "mouth_idle_enabled": p.mouth_idle_enabled,
        "eye_config": {
            "enable_micro_glance": p.eye_config.enable_micro_glance,
            "enable_long_glance": p.eye_config.enable_long_glance,
            "enable_expr_glance": p.eye_config.enable_expr_glance,
            "enable_goofy_sequences": p.eye_config.enable_goofy_sequences,
            "blink_initial_ms": list(p.eye_config.blink_initial_ms),
            "blink_after_ms": list(p.eye_config.blink_after_ms),
            "micro_initial_ms": list(p.eye_config.micro_initial_ms),
            "micro_after_ms": list(p.eye_config.micro_after_ms),
            "micro_glance_indices": list(p.eye_config.micro_glance_indices),
            "micro_return_ms": list(p.eye_config.micro_return_ms),
            "glance_initial_ms": list(p.eye_config.glance_initial_ms),
            "glance_after_ms": list(p.eye_config.glance_after_ms),
            "glance_indices": list(p.eye_config.glance_indices),
            "glance_return_ms": list(p.eye_config.glance_return_ms),
            "expr_initial_ms": list(p.eye_config.expr_initial_ms),
            "expr_after_ms": list(p.eye_config.expr_after_ms),
            "expr_indices": list(p.eye_config.expr_indices),
            "expr_return_ms": list(p.eye_config.expr_return_ms),
            "goofy_initial_ms": list(p.eye_config.goofy_initial_ms),
            "goofy_after_ms": list(p.eye_config.goofy_after_ms),
            "micro_transition_ms": p.eye_config.micro_transition_ms,
            "glance_transition_ms": p.eye_config.glance_transition_ms,
            "expr_transition_ms": p.eye_config.expr_transition_ms,
            "forbidden_eye_indices": list(p.eye_config.forbidden_eye_indices),
        },
        "mouth_timing": {
            "idle_delay_ms": p.mouth_timing.idle_delay_ms,
            "subtle_next_initial": list(p.mouth_timing.subtle_next_initial),
            "subtle_next_after": list(p.mouth_timing.subtle_next_after),
            "happy_next_initial": list(p.mouth_timing.happy_next_initial),
            "happy_next_after": list(p.mouth_timing.happy_next_after),
            "goofy_next_initial": list(p.mouth_timing.goofy_next_initial),
            "goofy_next_after": list(p.mouth_timing.goofy_next_after),
            "dramatic_next_initial": list(p.mouth_timing.dramatic_next_initial),
            "dramatic_next_after": list(p.mouth_timing.dramatic_next_after),
            "subtle_transition_ms": p.mouth_timing.subtle_transition_ms,
            "subtle_hold_ms": list(p.mouth_timing.subtle_hold_ms),
            "happy_transition_ms": p.mouth_timing.happy_transition_ms,
            "happy_hold_ms": list(p.mouth_timing.happy_hold_ms),
            "goofy_transition_ms": p.mouth_timing.goofy_transition_ms,
            "goofy_hold_ms": list(p.mouth_timing.goofy_hold_ms),
            "dramatic_transition_ms": p.mouth_timing.dramatic_transition_ms,
            "dramatic_hold_ms": list(p.mouth_timing.dramatic_hold_ms),
            "return_transition_ms": p.mouth_timing.return_transition_ms,
        },
        "emotes": [
            {
                "name": e.name,
                "eye_seq": [[idx, trans, hold] for idx, trans, hold in e.eye_seq],
                "mouth": e.mouth,
                "mouth_hold_ms": e.mouth_hold_ms,
            }
            for e in p.emotes
        ],
        "emote_timing": {
            "enabled": p.emote_timing.enabled,
            "idle_delay_ms": p.emote_timing.idle_delay_ms,
            "first_emote_after_ms": list(p.emote_timing.first_emote_after_ms),
            "emote_after_ms": list(p.emote_timing.emote_after_ms),
        },
    }


@app.post("/api/pipeline/text", response_model=PipelineResponse)
@limiter.limit("20/minute")
def pipeline_text(request: Request, req: TextRequest):
    """Run text through LLM → TTS, return audio + visemes."""
    if _settings is None:
        raise HTTPException(500, "Server not configured — missing .env keys")

    p = load_personality(req.personality_id)
    fallback_voice = _settings.azure_voice_name
    prompt_body = (p.llm_system_prompt or _settings.llm_system_prompt).strip()
    system_prompt = _build_system_prompt_for_mode(prompt_body, interaction_mode=None, llm_backend=req.llm_backend)

    history = _slice_history(req.llm_backend, _sanitize_history(req.history))

    slur_hit = detect_slur_by_language(req.text, regex_by_lang=_slur_regex_by_lang)
    timing_llm_ms: float | None = None
    timing_tts_ms: float | None = None
    if slur_hit is not None:
        safety_lang: SlurLanguage = slur_hit.language
        # Prefer frontend hint only when it matches a supported language.
        if req.safety_hint_language in ("en", "cs"):
            safety_lang = req.safety_hint_language

        if req.llm_backend in ("openai", "max"):
            llm = _get_llm(req.llm_backend, system_prompt=KIND_SYSTEM_PROMPT_BY_LANG[safety_lang])
            t0 = time.perf_counter()
            llm_result = llm.generate(req.text, history=history)
            timing_llm_ms = (time.perf_counter() - t0) * 1000
            response_text = llm_result.response
        else:
            response_text = KIND_FALLBACK_TEXT_BY_LANG[safety_lang]
        safety_triggered = True
        mood: Literal["neutral", "sad"] = "sad"
    else:
        llm = _get_llm(req.llm_backend, system_prompt=system_prompt)
        t0 = time.perf_counter()
        llm_result = llm.generate(req.text, history=history)
        timing_llm_ms = (time.perf_counter() - t0) * 1000
        response_text = llm_result.response
        safety_triggered = False
        mood = "neutral"

    detected = _lang_detect.detect(response_text) if _lang_detect is not None else None
    t0 = time.perf_counter()
    try:
        tts_result, voice_used = synthesize_mixed_language_ssml(
            response_text,
            session_id=req.session_id,
            fallback_voice=fallback_voice,
            detect_language=(
                (lambda t: _tts_detect_holy_trio_bias(t, detect_language=_lang_detect.detect))
                if _lang_detect is not None
                else None
            ),
            resolve_voice=_resolve_voice,
            get_tts=_get_tts,
        )
    except Exception as e:
        logger.error("TTS failed: %s", e)
        raise HTTPException(502, "TTS synthesis failed") from e
    timing_tts_ms = (time.perf_counter() - t0) * 1000

    audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""
    debug_lang_mode = "detected" if (detected and _lang_detect and _lang_detect.enabled) else "assumed"
    debug_voice_mode = (
        None
        if voice_used is None
        else ("pinned" if voice_used == fallback_voice else "auto")
    )

    return PipelineResponse(
        user_text=req.text,
        response_text=response_text,
        audio_base64=audio_b64,
        visemes=[VisemeOut(id=v.id, offset_ms=v.offset_ms) for v in tts_result.visemes],
        duration_ms=tts_result.duration_ms,
        mood=mood,
        safety_triggered=safety_triggered,
        safety_language=slur_hit.language if slur_hit is not None else None,
        detected_language=detected.language if detected else None,
        detected_language_score=detected.score if detected else None,
        debug_lang_mode=debug_lang_mode,
        debug_session_lang=_session_detected_lang.get(req.session_id) if req.session_id else None,
        voice_used=voice_used,
        debug_voice_mode=debug_voice_mode,
        language_detection_enabled=bool(_lang_detect and _lang_detect.enabled),
        language_detection_error=_lang_detect.last_error if _lang_detect is not None else "Language detection is disabled.",
        debug_stt_model=_settings.stt_model,
        debug_stt_language=_settings.stt_language or "auto",
        debug_llm_backend=req.llm_backend,
        debug_llm_model=("gpt-5.4-mini" if req.llm_backend == "max" else _settings.llm_model)
        if req.llm_backend in ("openai", "max")
        else None,
        debug_tts_backend="azure-speech",
        debug_lang_detect_backend="azure-translator" if (_lang_detect and _lang_detect.enabled) else "disabled",
        timing_llm_ms=timing_llm_ms,
        timing_tts_ms=timing_tts_ms,
    )


@app.post("/api/pipeline/audio", response_model=PipelineResponse)
@limiter.limit("20/minute")
async def pipeline_audio(
    request: Request,
    audio_file: UploadFile = File(...),
    personality_id: str = Form("peter"),
    llm_backend: LlmBackend = Form("echo"),
    session_id: str = Form(""),
    interaction_mode: str = Form(""),
    history: str = Form(""),
):
    """Run audio through STT → LLM → TTS, return audio + visemes."""
    if _settings is None or _stt is None:
        raise HTTPException(500, "Server not configured — missing .env keys")

    audio_bytes = await audio_file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio file too large (max 10 MB)")
    stt_format = _guess_stt_format(audio_file)
    stt_prompt_override, stt_lang_override = _get_stt_context(session_id)

    t0 = time.perf_counter()
    stt_result = await asyncio.to_thread(
        _stt.transcribe, audio_bytes, stt_format, stt_prompt_override, stt_lang_override
    )
    timing_stt_ms = (time.perf_counter() - t0) * 1000
    logger.info("STT: %s (%.0fms)", stt_result.text[:80], timing_stt_ms)

    # Language pinning: start a new "turn" for this audio request.
    _advance_session_language_turn(session_id)
    # Optional strengthening: detect language from the user transcript early in the session
    # (most helpful for Czech vs Slovak/Polish confusion).
    if _lang_detect is not None:
        state = _session_lang_state.get(session_id)
        turn = state.turn_count if state is not None else 0
        pinned = state.pinned_lang if state is not None else None
        if (turn and turn <= 4) or pinned is None:
            user_detected = _lang_detect.detect(stt_result.text)
            if user_detected:
                _apply_session_language_signal(
                    session_id, user_detected.language, user_detected.score or 0.0
                )

    p = load_personality(personality_id)
    fallback_voice = _settings.azure_voice_name
    prompt_body = (p.llm_system_prompt or _settings.llm_system_prompt).strip()
    system_prompt = _build_system_prompt_for_mode(prompt_body, interaction_mode=interaction_mode, llm_backend=llm_backend)
    sliced_history = _slice_history(llm_backend, _parse_history_form(history))

    slur_hit = detect_slur_by_language(stt_result.text, regex_by_lang=_slur_regex_by_lang)
    t0 = time.perf_counter()
    if slur_hit is not None:
        safety_lang = slur_hit.language
        if llm_backend in ("openai", "max"):
            llm = _get_llm(
                llm_backend,
                system_prompt=_maybe_add_interaction_context(KIND_SYSTEM_PROMPT_BY_LANG[safety_lang], interaction_mode),
            )
            llm_result = await asyncio.to_thread(llm.generate, stt_result.text, history=sliced_history)
            response_text = llm_result.response
        else:
            response_text = KIND_FALLBACK_TEXT_BY_LANG[safety_lang]
        safety_triggered = True
        mood: Literal["neutral", "sad"] = "sad"
    else:
        llm = _get_llm(llm_backend, system_prompt=system_prompt)
        llm_result = await asyncio.to_thread(llm.generate, stt_result.text, history=sliced_history)
        response_text = llm_result.response
        safety_triggered = False
        mood = "neutral"
    timing_llm_ms = (time.perf_counter() - t0) * 1000

    detected = _lang_detect.detect(response_text) if _lang_detect is not None else None
    if detected:
        _apply_session_language_signal(session_id, detected.language, detected.score or 0.0)
    _finalize_session_language_turn(session_id)

    t0 = time.perf_counter()
    try:
        tts_result, voice_used = await asyncio.to_thread(
            synthesize_mixed_language_ssml,
            response_text,
            session_id=session_id,
            fallback_voice=fallback_voice,
            detect_language=(
                (lambda t: _tts_detect_holy_trio_bias(t, detect_language=_lang_detect.detect))
                if _lang_detect is not None
                else None
            ),
            resolve_voice=_resolve_voice,
            get_tts=_get_tts,
        )
    except Exception as e:
        logger.error("TTS failed: %s", e)
        raise HTTPException(502, "TTS synthesis failed") from e
    timing_tts_ms = (time.perf_counter() - t0) * 1000

    audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""
    debug_lang_mode = "detected" if (detected and _lang_detect and _lang_detect.enabled) else "assumed"
    debug_voice_mode = (
        None
        if voice_used is None
        else ("pinned" if voice_used == fallback_voice else "auto")
    )

    return PipelineResponse(
        user_text=stt_result.text,
        response_text=response_text,
        audio_base64=audio_b64,
        visemes=[VisemeOut(id=v.id, offset_ms=v.offset_ms) for v in tts_result.visemes],
        duration_ms=tts_result.duration_ms,
        mood=mood,
        safety_triggered=safety_triggered,
        safety_language=slur_hit.language if slur_hit is not None else None,
        detected_language=detected.language if detected else None,
        detected_language_score=detected.score if detected else None,
        debug_lang_mode=debug_lang_mode,
        debug_session_lang=_session_detected_lang.get(session_id) if session_id else None,
        voice_used=voice_used,
        debug_voice_mode=debug_voice_mode,
        language_detection_enabled=bool(_lang_detect and _lang_detect.enabled),
        language_detection_error=_lang_detect.last_error if _lang_detect is not None else "Language detection is disabled.",
        debug_stt_model=_settings.stt_model,
        debug_stt_language=_settings.stt_language or "auto",
        debug_llm_backend=llm_backend,
        debug_llm_model=("gpt-5.4-mini" if llm_backend == "max" else _settings.llm_model)
        if llm_backend in ("openai", "max")
        else None,
        debug_tts_backend="azure-speech",
        debug_lang_detect_backend="azure-translator" if (_lang_detect and _lang_detect.enabled) else "disabled",
        timing_stt_ms=timing_stt_ms,
        timing_llm_ms=timing_llm_ms,
        timing_tts_ms=timing_tts_ms,
    )


@app.post("/api/pipeline/audio_stream")
@limiter.limit("20/minute")
async def pipeline_audio_stream(
    request: Request,
    audio_file: UploadFile = File(...),
    personality_id: str = Form("peter"),
    llm_backend: LlmBackend = Form("echo"),
    session_id: str = Form(""),
    interaction_mode: str = Form(""),
    history: str = Form(""),
):
    """Streaming pipeline: STT (authoritative) -> stream LLM text deltas (SSE) -> TTS.

    SSE events:
      - event: stt   data: {"user_text":"..."}
      - event: delta data: {"delta":"..."}
      - event: audio data: {"audio_base64":"...","visemes":[...],"duration_ms":...}
      - event: done  data: {"response_text":"...","audio_base64":"...","visemes":[...],"duration_ms":...,"mood":"neutral|sad"}
      - event: error data: {"message":"Something went wrong. Please try again."}
    """

    if _settings is None or _stt is None:
        raise HTTPException(500, "Server not configured — missing .env keys")

    async def event_stream():
        try:
            audio_bytes = await audio_file.read(MAX_AUDIO_BYTES + 1)
            if len(audio_bytes) > MAX_AUDIO_BYTES:
                yield "event: error\ndata: " + json.dumps({"message": "Audio file too large (max 10 MB)"}) + "\n\n"
                return
            stt_format = _guess_stt_format(audio_file)
            stt_prompt_override, stt_lang_override = _get_stt_context(session_id)

            t0 = time.perf_counter()
            stt_result = await asyncio.to_thread(
                _stt.transcribe, audio_bytes, stt_format, stt_prompt_override, stt_lang_override
            )
            timing_stt_ms = (time.perf_counter() - t0) * 1000

            yield "event: stt\ndata: " + json.dumps({"user_text": stt_result.text}) + "\n\n"

            p = load_personality(personality_id)
            fallback_voice = _settings.azure_voice_name
            prompt_body = (p.llm_system_prompt or _settings.llm_system_prompt).strip()
            system_prompt = _build_system_prompt_for_mode(prompt_body, interaction_mode=interaction_mode, llm_backend=llm_backend)
            sliced_history = _slice_history(llm_backend, _parse_history_form(history))

            slur_hit = detect_slur_by_language(stt_result.text, regex_by_lang=_slur_regex_by_lang)
            t0 = time.perf_counter()
            if slur_hit is not None:
                safety_lang = slur_hit.language
                if llm_backend in ("openai", "max"):
                    llm = _get_llm(
                        llm_backend,
                        system_prompt=_maybe_add_interaction_context(KIND_SYSTEM_PROMPT_BY_LANG[safety_lang], interaction_mode),
                    )
                    # Safety replies can be short; no need to stream.
                    llm_result = await asyncio.to_thread(llm.generate, stt_result.text, history=sliced_history)
                    response_text = llm_result.response
                else:
                    response_text = KIND_FALLBACK_TEXT_BY_LANG[safety_lang]
                safety_triggered = True
                mood: Literal["neutral", "sad"] = "sad"
                stream_iter = None
            else:
                llm = _get_llm(llm_backend, system_prompt=system_prompt)
                safety_triggered = False
                mood = "neutral"
                stream_iter = getattr(llm, "generate_stream", None) if llm_backend in ("openai", "max") else None

                if callable(stream_iter):
                    parts: list[str] = []
                    streamed_tts = False
                    streamed_voice_used: str | None = None

                    if llm_backend == "max":
                        # True incremental streaming for Max: emit deltas immediately.
                        q: asyncio.Queue[str | None] = asyncio.Queue()
                        audio_q: asyncio.Queue[dict] = asyncio.Queue()
                        loop = asyncio.get_running_loop()
                        buf = ""
                        pending_tts = 0

                        def _produce() -> None:
                            try:
                                for d in stream_iter(stt_result.text, history=sliced_history):
                                    if not d:
                                        continue
                                    loop.call_soon_threadsafe(q.put_nowait, d)
                            finally:
                                loop.call_soon_threadsafe(q.put_nowait, None)

                        tts_seq = 0
                        target_words = 8

                        async def _tts_chunk(clean_text: str, *, seq: int) -> None:
                            nonlocal pending_tts, streamed_tts, streamed_voice_used
                            try:
                                tts_result, voice_used = await asyncio.to_thread(
                                    synthesize_mixed_language_ssml,
                                    clean_text,
                                    session_id=session_id,
                                    fallback_voice=fallback_voice,
                                    detect_language=_lang_detect.detect if _lang_detect is not None else None,
                                    resolve_voice=_resolve_voice,
                                    get_tts=_get_tts,
                                )
                                streamed_tts = True
                                streamed_voice_used = voice_used
                                audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""
                                await audio_q.put(
                                    {
                                        "seq": seq,
                                        "audio_base64": audio_b64,
                                        "visemes": [{"id": v.id, "offset_ms": v.offset_ms} for v in tts_result.visemes],
                                        "duration_ms": tts_result.duration_ms,
                                    }
                                )
                            except Exception as e:
                                # Never allow one failed chunk to stall streaming ordering.
                                # We rely on the final full-utterance TTS in the done payload as the safety net.
                                logger.debug("streaming TTS chunk failed (seq=%s): %s", seq, e)
                            finally:
                                pending_tts -= 1

                        producer = asyncio.create_task(asyncio.to_thread(_produce))
                        delta_done = False
                        while True:
                            if delta_done and pending_tts <= 0 and audio_q.empty():
                                break

                            tasks: list[asyncio.Task] = []
                            delta_task: asyncio.Task | None = None
                            audio_task: asyncio.Task | None = None
                            try:
                                if not delta_done:
                                    delta_task = asyncio.create_task(q.get())
                                    tasks.append(delta_task)
                                if pending_tts > 0 or not audio_q.empty():
                                    audio_task = asyncio.create_task(audio_q.get())
                                    tasks.append(audio_task)

                                if not tasks:
                                    break

                                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                                if delta_task is not None and delta_task in done:
                                    item = delta_task.result()
                                    if item is None:
                                        delta_done = True
                                        if buf.strip():
                                            chunk, buf2 = _pop_tts_chunk_doubling(buf, target_words=target_words, force=True)
                                            buf = buf2
                                            if chunk:
                                                lang_hint = _session_detected_lang.get(session_id) if session_id else None
                                                clean = _sanitize_for_tts(chunk, lang_hint=lang_hint)
                                                if clean:
                                                    seq = tts_seq
                                                    tts_seq += 1
                                                    pending_tts += 1
                                                    asyncio.create_task(_tts_chunk(clean, seq=seq))
                                                    target_words = min(256, target_words * 2)
                                    else:
                                        parts.append(item)
                                        buf += item
                                        yield "event: delta\ndata: " + json.dumps({"delta": item}) + "\n\n"
                                        # Doubling strategy: flush after reaching target word count.
                                        chunk, buf2 = _pop_tts_chunk_doubling(buf, target_words=target_words, force=False)
                                        if chunk:
                                            buf = buf2
                                            lang_hint = _session_detected_lang.get(session_id) if session_id else None
                                            clean = _sanitize_for_tts(chunk, lang_hint=lang_hint)
                                            if clean:
                                                seq = tts_seq
                                                tts_seq += 1
                                                pending_tts += 1
                                                asyncio.create_task(_tts_chunk(clean, seq=seq))
                                                target_words = min(256, target_words * 2)

                                if audio_task is not None and audio_task in done:
                                    payload = audio_task.result()
                                    yield "event: audio\ndata: " + json.dumps(payload) + "\n\n"

                                for t in pending:
                                    t.cancel()
                            finally:
                                for t in tasks:
                                    if not t.done():
                                        t.cancel()
                        await producer
                        response_text = "".join(parts).strip()
                    else:
                        # OpenAI mode: streaming optional. Keep legacy behavior.
                        def _collect_stream() -> None:
                            for d in stream_iter(stt_result.text, history=sliced_history):
                                parts.append(d)

                        await asyncio.to_thread(_collect_stream)
                        for d in parts:
                            yield "event: delta\ndata: " + json.dumps({"delta": d}) + "\n\n"
                        response_text = "".join(parts).strip()
                else:
                    llm_result = await asyncio.to_thread(llm.generate, stt_result.text, history=sliced_history)
                    response_text = llm_result.response
            timing_llm_ms = (time.perf_counter() - t0) * 1000

            # Language pinning: one "turn" per audio_stream request.
            _advance_session_language_turn(session_id)
            if _lang_detect is not None:
                state = _session_lang_state.get(session_id)
                turn = state.turn_count if state is not None else 0
                pinned = state.pinned_lang if state is not None else None
                if (turn and turn <= 4) or pinned is None:
                    user_detected = _lang_detect.detect(stt_result.text)
                    if user_detected:
                        _apply_session_language_signal(
                            session_id, user_detected.language, user_detected.score or 0.0
                        )

            detected = _lang_detect.detect(response_text) if _lang_detect is not None else None
            if detected:
                _apply_session_language_signal(session_id, detected.language, detected.score or 0.0)
            _finalize_session_language_turn(session_id)

            tts_result = None
            voice_used = None
            timing_tts_ms = None
            audio_b64 = ""
            # Safety net: always attach a full-utterance TTS to the done payload.
            # Streaming chunks are best-effort; the done payload must be reliable.
            if True:
                t0 = time.perf_counter()
                try:
                    tts_result, voice_used = await asyncio.to_thread(
                        synthesize_mixed_language_ssml,
                        response_text,
                        session_id=session_id,
                        fallback_voice=fallback_voice,
                        detect_language=(
                            (lambda t: _tts_detect_holy_trio_bias(t, detect_language=_lang_detect.detect))
                            if _lang_detect is not None
                            else None
                        ),
                        resolve_voice=_resolve_voice,
                        get_tts=_get_tts,
                    )
                except Exception as e:
                    logger.error("TTS failed: %s", e)
                    yield "event: error\ndata: " + json.dumps({"message": "TTS synthesis failed. Please try again."}) + "\n\n"
                    return
                timing_tts_ms = (time.perf_counter() - t0) * 1000
                audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""
                audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""
            else:
                # For Max streaming, voice may have been chosen during chunk TTS.
                voice_used = streamed_voice_used

            debug_lang_mode = "detected" if (detected and _lang_detect and _lang_detect.enabled) else "assumed"
            debug_voice_mode = (
                None
                if voice_used is None
                else ("pinned" if voice_used == fallback_voice else "auto")
            )

            payload = {
                "user_text": stt_result.text,
                "response_text": response_text,
                "audio_base64": audio_b64,
                "visemes": [{"id": v.id, "offset_ms": v.offset_ms} for v in (tts_result.visemes if tts_result else [])],
                "duration_ms": (tts_result.duration_ms if tts_result else 0.0),
                "mood": mood,
                "safety_triggered": safety_triggered,
                "safety_language": slur_hit.language if slur_hit is not None else None,
                "detected_language": detected.language if detected else None,
                "detected_language_score": detected.score if detected else None,
                "debug_lang_mode": debug_lang_mode,
                "debug_session_lang": _session_detected_lang.get(session_id) if session_id else None,
                "voice_used": voice_used,
                "debug_voice_mode": debug_voice_mode,
                "language_detection_enabled": bool(_lang_detect and _lang_detect.enabled),
                "language_detection_error": _lang_detect.last_error if _lang_detect is not None else "Language detection is disabled.",
                "debug_stt_model": _settings.stt_model,
                "debug_stt_language": _settings.stt_language or "auto",
                "debug_llm_backend": llm_backend,
                "debug_llm_model": ("gpt-5.4-mini" if llm_backend == "max" else _settings.llm_model)
                if llm_backend in ("openai", "max")
                else None,
                "debug_tts_backend": "azure-speech",
                "debug_lang_detect_backend": "azure-translator" if (_lang_detect and _lang_detect.enabled) else "disabled",
                "timing_stt_ms": timing_stt_ms,
                "timing_llm_ms": timing_llm_ms,
                "timing_tts_ms": timing_tts_ms,
            }
            yield "event: done\ndata: " + json.dumps(payload) + "\n\n"
        except Exception as e:
            logger.debug("audio_stream failed: %s", e)
            yield "event: error\ndata: " + json.dumps({"message": "Something went wrong. Please try again."}) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/pipeline/text_stream")
@limiter.limit("20/minute")
async def pipeline_text_stream(request: Request, req: TextRequest):
    """Streaming text pipeline (SSE): stream LLM deltas -> TTS.

    SSE events:
      - event: delta data: {"delta":"..."}
      - event: audio data: {"audio_base64":"...","visemes":[...],"duration_ms":...}
      - event: done  data: <PipelineResponse payload as JSON>
      - event: error data: {"message":"Something went wrong. Please try again."}
    """
    if _settings is None:
        raise HTTPException(500, "Server not configured — missing .env keys")

    async def event_stream():
        try:
            p = load_personality(req.personality_id)
            fallback_voice = _settings.azure_voice_name
            prompt_body = (p.llm_system_prompt or _settings.llm_system_prompt).strip()
            system_prompt = _build_system_prompt_for_mode(prompt_body, interaction_mode=None, llm_backend=req.llm_backend)
            sliced_history = _slice_history(req.llm_backend, _sanitize_history(req.history))

            slur_hit = detect_slur_by_language(req.text, regex_by_lang=_slur_regex_by_lang)
            response_text = ""
            safety_triggered = False
            mood: Literal["neutral", "sad"] = "neutral"
            timing_llm_ms: float | None = None
            timing_tts_ms: float | None = None

            t0 = time.perf_counter()
            if slur_hit is not None:
                safety_lang: SlurLanguage = slur_hit.language
                if req.safety_hint_language in ("en", "cs"):
                    safety_lang = req.safety_hint_language
                if req.llm_backend in ("openai", "max"):
                    llm = _get_llm(req.llm_backend, system_prompt=KIND_SYSTEM_PROMPT_BY_LANG[safety_lang])
                    llm_result = await asyncio.to_thread(llm.generate, req.text, history=sliced_history)
                    response_text = llm_result.response
                else:
                    response_text = KIND_FALLBACK_TEXT_BY_LANG[safety_lang]
                safety_triggered = True
                mood = "sad"
            else:
                llm = _get_llm(req.llm_backend, system_prompt=system_prompt)
                stream_iter = getattr(llm, "generate_stream", None) if req.llm_backend in ("openai", "max") else None

                if req.llm_backend == "max" and callable(stream_iter):
                    q: asyncio.Queue[str | None] = asyncio.Queue()
                    audio_q: asyncio.Queue[dict] = asyncio.Queue()
                    loop = asyncio.get_running_loop()
                    parts: list[str] = []
                    buf = ""
                    pending_tts = 0
                    tts_seq = 0
                    target_words = 8

                    def _produce() -> None:
                        try:
                            for d in stream_iter(req.text, history=sliced_history):
                                if not d:
                                    continue
                                loop.call_soon_threadsafe(q.put_nowait, d)
                        finally:
                            loop.call_soon_threadsafe(q.put_nowait, None)

                    async def _tts_chunk(clean_text: str, *, seq: int) -> None:
                        nonlocal pending_tts
                        try:
                            tts_result, _voice_used = await asyncio.to_thread(
                                synthesize_mixed_language_ssml,
                                clean_text,
                                session_id=req.session_id,
                                fallback_voice=fallback_voice,
                                detect_language=_lang_detect.detect if _lang_detect is not None else None,
                                resolve_voice=_resolve_voice,
                                get_tts=_get_tts,
                            )
                            audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""
                            await audio_q.put(
                                {
                                    "seq": seq,
                                    "audio_base64": audio_b64,
                                    "visemes": [{"id": v.id, "offset_ms": v.offset_ms} for v in tts_result.visemes],
                                    "duration_ms": tts_result.duration_ms,
                                }
                            )
                        except Exception as e:
                            logger.debug("streaming TTS chunk failed (seq=%s): %s", seq, e)
                        finally:
                            pending_tts -= 1

                    producer = asyncio.create_task(asyncio.to_thread(_produce))
                    delta_done = False
                    while True:
                        if delta_done and pending_tts <= 0 and audio_q.empty():
                            break

                        tasks: list[asyncio.Task] = []
                        delta_task: asyncio.Task | None = None
                        audio_task: asyncio.Task | None = None
                        try:
                            if not delta_done:
                                delta_task = asyncio.create_task(q.get())
                                tasks.append(delta_task)
                            if pending_tts > 0 or not audio_q.empty():
                                audio_task = asyncio.create_task(audio_q.get())
                                tasks.append(audio_task)

                            if not tasks:
                                break

                            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                            if delta_task is not None and delta_task in done:
                                item = delta_task.result()
                                if item is None:
                                    delta_done = True
                                    if buf.strip():
                                        chunk, buf2 = _pop_tts_chunk_doubling(buf, target_words=target_words, force=True)
                                        buf = buf2
                                        if chunk:
                                            lang_hint = _session_detected_lang.get(req.session_id) if req.session_id else None
                                            clean = _sanitize_for_tts(chunk, lang_hint=lang_hint)
                                            if clean:
                                                seq = tts_seq
                                                tts_seq += 1
                                                pending_tts += 1
                                                asyncio.create_task(_tts_chunk(clean, seq=seq))
                                                target_words = min(256, target_words * 2)
                                else:
                                    parts.append(item)
                                    buf += item
                                    yield "event: delta\ndata: " + json.dumps({"delta": item}) + "\n\n"
                                    chunk, buf2 = _pop_tts_chunk_doubling(buf, target_words=target_words, force=False)
                                    if chunk:
                                        buf = buf2
                                        lang_hint = _session_detected_lang.get(req.session_id) if req.session_id else None
                                        clean = _sanitize_for_tts(chunk, lang_hint=lang_hint)
                                        if clean:
                                            seq = tts_seq
                                            tts_seq += 1
                                            pending_tts += 1
                                            asyncio.create_task(_tts_chunk(clean, seq=seq))
                                            target_words = min(256, target_words * 2)

                            if audio_task is not None and audio_task in done:
                                payload = audio_task.result()
                                yield "event: audio\ndata: " + json.dumps(payload) + "\n\n"

                            for t in pending:
                                t.cancel()
                        finally:
                            for t in tasks:
                                if not t.done():
                                    t.cancel()
                    await producer
                    response_text = "".join(parts).strip()
                else:
                    # Non-max: generate full response (streaming optional).
                    llm_result = await asyncio.to_thread(llm.generate, req.text, history=sliced_history)
                    response_text = llm_result.response

            timing_llm_ms = (time.perf_counter() - t0) * 1000

            detected = _lang_detect.detect(response_text) if _lang_detect is not None else None

            tts_result = None
            voice_used = None
            audio_b64 = ""
            try:
                t0 = time.perf_counter()
                tts_result, voice_used = await asyncio.to_thread(
                    synthesize_mixed_language_ssml,
                    response_text,
                    session_id=req.session_id,
                    fallback_voice=fallback_voice,
                    detect_language=_lang_detect.detect if _lang_detect is not None else None,
                    resolve_voice=_resolve_voice,
                    get_tts=_get_tts,
                )
            except Exception as e:
                logger.error("TTS failed: %s", e)
                yield "event: error\ndata: " + json.dumps({"message": "TTS synthesis failed. Please try again."}) + "\n\n"
                return
            timing_tts_ms = (time.perf_counter() - t0) * 1000

            audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""
            debug_lang_mode = "detected" if (detected and _lang_detect and _lang_detect.enabled) else "assumed"
            debug_voice_mode = (
                None
                if voice_used is None
                else ("pinned" if voice_used == fallback_voice else "auto")
            )
            payload = {
                "user_text": req.text,
                "response_text": response_text,
                "audio_base64": audio_b64,
                "visemes": [{"id": v.id, "offset_ms": v.offset_ms} for v in (tts_result.visemes if tts_result else [])],
                "duration_ms": (tts_result.duration_ms if tts_result else 0.0),
                "mood": mood,
                "safety_triggered": safety_triggered,
                "safety_language": slur_hit.language if slur_hit is not None else None,
                "detected_language": detected.language if detected else None,
                "detected_language_score": detected.score if detected else None,
                "debug_lang_mode": debug_lang_mode,
                "debug_session_lang": _session_detected_lang.get(req.session_id) if req.session_id else None,
                "voice_used": voice_used,
                "debug_voice_mode": debug_voice_mode,
                "language_detection_enabled": bool(_lang_detect and _lang_detect.enabled),
                "language_detection_error": _lang_detect.last_error if _lang_detect is not None else "Language detection is disabled.",
                "debug_stt_model": _settings.stt_model,
                "debug_stt_language": _settings.stt_language or "auto",
                "debug_llm_backend": req.llm_backend,
                "debug_llm_model": ("gpt-5.4-mini" if req.llm_backend == "max" else _settings.llm_model)
                if req.llm_backend in ("openai", "max")
                else None,
                "debug_tts_backend": "azure-speech",
                "debug_lang_detect_backend": "azure-translator" if (_lang_detect and _lang_detect.enabled) else "disabled",
                "timing_llm_ms": timing_llm_ms,
                "timing_tts_ms": timing_tts_ms,
            }
            yield "event: done\ndata: " + json.dumps(payload) + "\n\n"
        except Exception as e:
            logger.debug("text_stream failed: %s", e)
            yield "event: error\ndata: " + json.dumps({"message": "Something went wrong. Please try again."}) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Built frontend serving (React/Vite) ---
_FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    # Vite build is configured to emit app assets into "ui-assets/" to avoid clashing
    # with the avatar sprite route at "/assets".
    ui_assets_dir = _FRONTEND_DIST / "ui-assets"
    if ui_assets_dir.exists():
        app.mount("/ui-assets", StaticFiles(directory=str(ui_assets_dir)), name="ui-assets")
    # Serve remaining built files (index fallback, favicon, etc). Must be last so
    # /api and /assets routes take precedence.
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=True)
