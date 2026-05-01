"""Test bootstrapping.

The real Azure Speech SDK can load native dependencies that are not available (or unstable)
in CI/sandboxed environments. For unit tests we stub it out at import time.
"""

from __future__ import annotations

import sys
import types


def _install_azure_speech_stub() -> None:
    if "azure.cognitiveservices.speech" in sys.modules:
        return

    azure = types.ModuleType("azure")
    cognitiveservices = types.ModuleType("azure.cognitiveservices")
    speech = types.ModuleType("azure.cognitiveservices.speech")

    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, _name: str):
            # Provide a permissive object for tests that never call the SDK.
            return _Dummy()

        def connect(self, *_a, **_kw):
            return None

        def get(self, *_a, **_kw):
            return _Dummy()

    # Minimal surface area used by our codebase.
    speech.SpeechConfig = _Dummy
    speech.SpeechSynthesizer = _Dummy
    speech.SpeechSynthesisOutputFormat = types.SimpleNamespace(Riff16Khz16BitMonoPcm=0)
    speech.ResultReason = types.SimpleNamespace(SynthesizingAudioCompleted=0)
    speech.CancellationDetails = _Dummy
    speech.SessionEventArgs = _Dummy
    speech.SpeechSynthesisResult = _Dummy

    sys.modules["azure"] = azure
    sys.modules["azure.cognitiveservices"] = cognitiveservices
    sys.modules["azure.cognitiveservices.speech"] = speech


_install_azure_speech_stub()

import sys
from pathlib import Path

# Ensure `import backend` works when running `pytest` from repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os

import pytest


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


@pytest.fixture(scope="session", autouse=True)
def _init_pygame():
    import pygame

    pygame.init()
    yield
    pygame.quit()
