"""FastAPI web server for the Avatar Demo.

Exposes the existing pipeline over HTTP and serves a Canvas-based frontend.

Usage:
    pip install fastapi uvicorn python-multipart
    python web_server.py
"""

from __future__ import annotations

import base64
import logging
import os
import sys
from pathlib import Path
from typing import Literal

# Add project root to path so backend imports work
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from backend.config import Settings
from backend.log import setup_logging
from backend.models import PipelineResult, TtsResult
from backend.personalities import list_personality_ids, load_personality, Personality
from backend.services.llm import EchoLlmService, OpenAiChatLlmService
from backend.services.lang_detect import AzureTranslatorLanguageDetectService
from backend.services.stt import WhisperSttService
from backend.services.tts import AzureTtsService
from backend.services.azure_voice_catalog import AzureSpeechVoiceCatalog
from backend.services.voice_select import choose_voice
from backend.rendering.animation_config import (
    EYE_PRESETS,
    MOUTH_TIMING_PRESETS,
    EMOTE_TIMING_PRESETS,
)
from backend.rendering.emote_catalog import EMOTES_BY_NAME
from backend.rendering.avatar_controllers import (
    EYE_SEQUENCE_CATALOG,
    SEQ_BLINK,
    SEQ_SLOW_BLINK,
    SEQ_DOUBLE_BLINK,
    SEQ_SPIN,
    SEQ_FRANTIC,
    SEQ_CROSSEYED,
    SEQ_SHOCK_SQUINT,
    SEQ_CONFUSED,
)

setup_logging("INFO")
logger = logging.getLogger("backend.web")

app = FastAPI(title="Avatar Demo")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Globals (initialized on startup) ---
_settings: Settings | None = None
_stt = None
_tts_cache: dict[str, AzureTtsService] = {}
_lang_detect: AzureTranslatorLanguageDetectService | None = None
_voice_catalog: AzureSpeechVoiceCatalog | None = None

ASSETS_DIR = PROJECT_ROOT / "assets"


# --- Startup ---
@app.on_event("startup")
def startup():
    global _settings, _stt, _lang_detect, _voice_catalog
    try:
        _settings = Settings.load()
        _stt = WhisperSttService(api_key=_settings.openai_api_key)
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


LlmBackend = Literal["echo", "openai"]


def _get_llm(llm_backend: LlmBackend, system_prompt: str):
    if llm_backend == "echo":
        return EchoLlmService(system_prompt=system_prompt)
    if llm_backend == "openai":
        if _settings is None:
            raise HTTPException(500, "Server not configured — missing .env keys")
        return OpenAiChatLlmService(
            api_key=_settings.openai_api_key,
            system_prompt=system_prompt,
            model=_settings.llm_model,
            max_completion_tokens=_settings.llm_max_completion_tokens,
        )
    raise HTTPException(400, f"Unsupported llm_backend: {llm_backend}")


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


class VisemeOut(BaseModel):
    id: int
    offset_ms: float


class PipelineResponse(BaseModel):
    user_text: str
    response_text: str
    audio_base64: str
    visemes: list[VisemeOut]
    duration_ms: float
    detected_language: str | None = None
    detected_language_score: float | None = None
    voice_used: str | None = None
    language_detection_enabled: bool = False
    language_detection_error: str | None = None


# --- API Endpoints ---
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
def pipeline_text(req: TextRequest):
    """Run text through LLM → TTS, return audio + visemes."""
    if _settings is None:
        raise HTTPException(500, "Server not configured — missing .env keys")

    p = load_personality(req.personality_id)
    fallback_voice = _settings.azure_voice_name
    system_prompt = p.llm_system_prompt or _settings.llm_system_prompt

    llm = _get_llm(req.llm_backend, system_prompt=system_prompt)
    llm_result = llm.generate(req.text)

    detected = _lang_detect.detect(llm_result.response) if _lang_detect is not None else None
    selection = choose_voice(
        detected_language=detected.language if detected else None,
        fallback_voice_name=fallback_voice,
        catalog=_voice_catalog,
    )
    voice = selection.voice_name

    tts = _get_tts(voice)
    try:
        tts_result = tts.synthesize(llm_result.response)
    except Exception as e:
        logger.error("TTS failed: %s", e)
        tts_result = TtsResult(audio_data=b"", visemes=[], duration_ms=0.0)

    audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""

    return PipelineResponse(
        user_text=req.text,
        response_text=llm_result.response,
        audio_base64=audio_b64,
        visemes=[VisemeOut(id=v.id, offset_ms=v.offset_ms) for v in tts_result.visemes],
        duration_ms=tts_result.duration_ms,
        detected_language=detected.language if detected else None,
        detected_language_score=detected.score if detected else None,
        voice_used=voice,
        language_detection_enabled=bool(_lang_detect and _lang_detect.enabled),
        language_detection_error=_lang_detect.last_error if _lang_detect is not None else "Language detection is disabled.",
    )


@app.post("/api/pipeline/audio", response_model=PipelineResponse)
async def pipeline_audio(
    audio_file: UploadFile = File(...),
    personality_id: str = Form("peter"),
    llm_backend: LlmBackend = Form("echo"),
):
    """Run audio through STT → LLM → TTS, return audio + visemes."""
    if _settings is None or _stt is None:
        raise HTTPException(500, "Server not configured — missing .env keys")

    audio_bytes = await audio_file.read()
    ext = (audio_file.filename or "audio.wav").rsplit(".", 1)[-1]

    stt_result = _stt.transcribe(audio_bytes, ext)
    logger.info("STT: %s", stt_result.text[:80])

    p = load_personality(personality_id)
    fallback_voice = _settings.azure_voice_name
    system_prompt = p.llm_system_prompt or _settings.llm_system_prompt

    llm = _get_llm(llm_backend, system_prompt=system_prompt)
    llm_result = llm.generate(stt_result.text)

    detected = _lang_detect.detect(llm_result.response) if _lang_detect is not None else None
    selection = choose_voice(
        detected_language=detected.language if detected else None,
        fallback_voice_name=fallback_voice,
        catalog=_voice_catalog,
    )
    voice = selection.voice_name

    tts = _get_tts(voice)
    try:
        tts_result = tts.synthesize(llm_result.response)
    except Exception as e:
        logger.error("TTS failed: %s", e)
        tts_result = TtsResult(audio_data=b"", visemes=[], duration_ms=0.0)

    audio_b64 = base64.b64encode(tts_result.audio_data).decode() if tts_result.audio_data else ""

    return PipelineResponse(
        user_text=stt_result.text,
        response_text=llm_result.response,
        audio_base64=audio_b64,
        visemes=[VisemeOut(id=v.id, offset_ms=v.offset_ms) for v in tts_result.visemes],
        duration_ms=tts_result.duration_ms,
        detected_language=detected.language if detected else None,
        detected_language_score=detected.score if detected else None,
        voice_used=voice,
        language_detection_enabled=bool(_lang_detect and _lang_detect.enabled),
        language_detection_error=_lang_detect.last_error if _lang_detect is not None else "Language detection is disabled.",
    )


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
