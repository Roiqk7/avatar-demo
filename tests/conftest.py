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
