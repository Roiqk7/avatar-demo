# Avatar Demo

Speech-driven avatar pipeline: **STT → LLM → TTS + Visemes → Avatar Rendering**

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

## Usage

Every run can target a **personality** (avatar look, motion, Azure voice, and LLM system prompt) with `--personality ID`. IDs match YAML files in `backend/personalities/` (e.g. `peter`, `ted`, `emma`, `trevor`). Default is `peter`.

```bash
# Text input
python3 -m backend.main --text "Hello, how are you?"

# Same pipeline with a specific persona
python3 -m backend.main --text "Hello" --personality emma --render

# Audio file input (runs through STT first)
python3 -m backend.main --audio speech.mp3 --personality trevor

# Text file input (one utterance per line)
python3 -m backend.main --file demo_script.txt

# Interactive mode (no args)
python3 -m backend.main

# Verbose logging
python3 -m backend.main --text "Hello" --log-level DEBUG

# Save audio + viseme JSON to disk
python3 -m backend.main --text "Hello" --output ./output

# Run full unit test suite
python3 -m backend.main --test
```

### Debug tools (pygame, no full pipeline unless noted)

Use `--personality` to load that persona’s face, layout, and shared sprite paths.

```bash
# Sprite viewer: step through eyes and TTS viseme overlays on the face
python3 -m backend.main --test-sprites --personality emma

# Animation browser: idle mouth tiers, blinks, emotes for this persona
python3 -m backend.main --test-animations --personality ted

# Personality switcher: Left/Right cycles YAML personas, Space runs Azure TTS demo line
# Requires .env with Azure Speech (same as normal TTS)
python3 -m backend.main --test-personalities --personality peter
```

### Adding a new personality

Copy `backend/personalities/_template.yaml` to `backend/personalities/<id>.yaml` (no leading underscore), set `assets.face`, voice, and prompt. Optional shortcuts: `animation.vibe` (`calm` | `balanced` | `playful` | `wild`) and `idle_mouth_profile` (`none` | `minimal` | `standard` | `full`). Full options are documented in the module docstring at the top of `backend/personalities/loader.py`.

## Architecture

```
Input (text/audio/file) → STT (OpenAI Whisper) → LLM (echo/GPT-4o) → TTS + Visemes (Azure) → Renderer (audio/pygame)
```

Services are defined as `Protocol` interfaces in `backend/services/__init__.py`. Swap any implementation by changing one line in `main.py`.

## Web frontend

There is also a browser-based UI backed by FastAPI.

### Auto voice by detected language (cs/sk/en)

The web server can **detect language from text** via **Azure Translator** and automatically pick a preferred Azure TTS voice (currently Czech, Slovak, English). This **overrides** the personality-configured voice.

Add these to `.env`:

- `AZURE_TRANSLATOR_KEY`
- `AZURE_TRANSLATOR_REGION` (recommended)

```bash
# Backend (FastAPI)
python web_server.py

# Frontend (React/Vite dev server)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.
