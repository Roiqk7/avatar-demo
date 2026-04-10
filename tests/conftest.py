import os

import pytest


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


@pytest.fixture(scope="session", autouse=True)
def _init_pygame():
    import pygame

    pygame.init()
    yield
    pygame.quit()
