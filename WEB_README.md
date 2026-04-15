# Avatar Demo — Web Version

Browser-based avatar renderer using HTML5 Canvas + FastAPI backend.

## Setup

```bash
# Existing setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys

# Web dependencies
pip install -r requirements_web.txt
```

## Running

```bash
python web_server.py
```

Open **http://localhost:8000** in your browser.

## Architecture

```
Browser (Canvas + Web Audio)  ←→  FastAPI  ←→  Existing Pipeline (STT/LLM/TTS)
```

### Backend (`web_server.py`)

- `GET /` — serves the single-page frontend
- `GET /api/personalities` — returns all personality configs as JSON (timing, layout, emote definitions, asset paths)
- `POST /api/pipeline/text` — runs text → LLM → TTS, returns base64 audio + viseme timeline
- `POST /api/pipeline/audio` — runs audio → STT → LLM → TTS (for mic input)
- `/assets/*` — serves sprite PNGs directly to the browser

### Frontend (`static/index.html`)

A single self-contained HTML file with:

- **Canvas renderer** — composites face, eyes, and mouth sprites at 60fps
- **EyeController** — JS port of the Python state machine: blinks, micro-glances, long glances, expression glances, goofy sequences
- **MouthController** — JS port: idle mouth animations with four tiers (subtle, happy, goofy, dramatic) and cross-fade transitions
- **EmoteController** — JS port: coordinated eye+mouth emotes on random timers
- **Web Audio API** — plays TTS audio with precise timing for viseme sync
- **Microphone recording** — MediaRecorder API with click-to-toggle, live volume glow on the mic button, recording duration timer, auto-format detection (webm/ogg)
- **Personality switcher** — loads different avatar configs and assets on the fly

### What changed vs. the CLI version

| Concern | CLI (pygame) | Web |
|---------|-------------|-----|
| Rendering | pygame + SDL | HTML5 Canvas 2D |
| Audio playback | pygame.mixer | Web Audio API |
| Animation loop | `while running:` | `requestAnimationFrame` |
| Pipeline invocation | Direct function calls | HTTP POST to FastAPI |
| Asset loading | `pygame.image.load` | `new Image()` from `/assets/` |
| Controllers | Python classes | JS classes (1:1 port) |

The existing Python backend code (`backend/`) is **completely unchanged**. The web server imports and wraps it.

## File placement

Place both files at the **project root** (next to `backend/`, `tests/`, `requirements.txt`):

```
project-root/
├── backend/          # existing — untouched
├── tests/            # existing — untouched
├── static/
│   └── index.html    # ← new
├── web_server.py     # ← new
├── requirements_web.txt  # ← new
├── requirements.txt  # existing
└── .env              # existing
```
