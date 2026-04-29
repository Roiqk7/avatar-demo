# Avatar Demo — Web Version

Browser-based avatar renderer using HTML5 Canvas + FastAPI backend.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

## Running

### Option A: Dev mode (recommended)

Run the Python backend:

```bash
python web_server.py
```

In a second terminal, run the React dev server:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

### Option B: Build + serve from FastAPI

```bash
cd frontend
npm install
npm run build
cd ..
python web_server.py
```

Open **http://localhost:8000** in your browser.

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

## Auto voice selection by detected language (cs/sk/en)

If you configure Azure Translator in `.env`, the backend will **detect language from the text being spoken** (the LLM response) and choose a preferred Azure TTS voice for:

- Czech (`cs`)
- Slovak (`sk`)
- English (`en`)

This selection currently **overrides** the personality voice.

Required `.env` vars:

- `AZURE_TRANSLATOR_KEY`
- `AZURE_TRANSLATOR_REGION` (recommended)

### Frontend (`frontend/`)

React + Vite app that contains:

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

```
project-root/
├── backend/          # existing — untouched
├── tests/            # existing — untouched
├── frontend/         # React/Vite app
├── static/           # legacy single-file frontend (still present)
├── web_server.py
├── requirements.txt
└── .env
```
