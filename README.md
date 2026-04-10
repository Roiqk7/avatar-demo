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

```bash
# Text input
python3 -m backend.main --text "Hello, how are you?"

# Text input with avatar window
python3 -m backend.main --text "Hello, how are you?" --render

# Audio file input (runs through STT first)
python3 -m backend.main --audio speech.mp3

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

## Architecture

```
Input (text/audio/file) → STT (OpenAI Whisper) → LLM (echo/GPT-4o) → TTS + Visemes (Azure) → Renderer (audio/pygame)
```

Services are defined as `Protocol` interfaces in `backend/services/__init__.py`. Swap any implementation by changing one line in `main.py`.
