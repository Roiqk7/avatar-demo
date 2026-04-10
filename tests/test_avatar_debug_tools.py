import types

import pygame
import pytest

from backend.rendering.avatar_test_animations import test_animations as run_animation_viewer
from backend.rendering.avatar_test_sprites import test_sprites as run_sprite_viewer


def _patch_pygame_basics(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("pygame.init", lambda: None)
    monkeypatch.setattr("pygame.quit", lambda: None)
    monkeypatch.setattr("pygame.display.set_caption", lambda text: None)
    monkeypatch.setattr("pygame.display.flip", lambda: None)
    monkeypatch.setattr("pygame.font.SysFont", lambda *args, **kwargs: types.SimpleNamespace(render=lambda *a, **k: pygame.Surface((1, 1))))
    monkeypatch.setattr("pygame.time.Clock", lambda: types.SimpleNamespace(tick=lambda fps: None))


def test_test_sprites_exits_when_face_missing(monkeypatch: pytest.MonkeyPatch):
    _patch_pygame_basics(monkeypatch)
    monkeypatch.setattr("pygame.display.set_mode", lambda size: pygame.Surface(size))
    monkeypatch.setattr("backend.rendering.avatar_test_sprites.load_face", lambda face_width: None)
    monkeypatch.setattr("backend.rendering.avatar_test_sprites.load_visemes", lambda w, h: {})
    monkeypatch.setattr("backend.rendering.avatar_test_sprites.load_eyes", lambda w, h: {})
    run_sprite_viewer()


def test_test_animations_exits_when_face_missing(monkeypatch: pytest.MonkeyPatch):
    _patch_pygame_basics(monkeypatch)
    monkeypatch.setattr("pygame.display.set_mode", lambda size: pygame.Surface(size))
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_face", lambda face_width: None)
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_visemes", lambda w, h: {})
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_eyes", lambda w, h: {})
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_idle_mouths", lambda w, h: {})
    run_animation_viewer()


def test_test_sprites_runs_single_quit_frame(monkeypatch: pytest.MonkeyPatch):
    _patch_pygame_basics(monkeypatch)
    monkeypatch.setattr("pygame.display.set_mode", lambda size: pygame.Surface(size))
    monkeypatch.setattr("backend.rendering.avatar_test_sprites.load_face", lambda face_width: pygame.Surface((200, 200), pygame.SRCALPHA))
    monkeypatch.setattr("backend.rendering.avatar_test_sprites.load_visemes", lambda w, h: {})
    monkeypatch.setattr("backend.rendering.avatar_test_sprites.load_eyes", lambda w, h: {})
    monkeypatch.setattr("pygame.event.get", lambda: [types.SimpleNamespace(type=pygame.QUIT)])
    run_sprite_viewer()


def test_test_animations_runs_single_quit_frame(monkeypatch: pytest.MonkeyPatch):
    _patch_pygame_basics(monkeypatch)
    monkeypatch.setattr("pygame.display.set_mode", lambda size: pygame.Surface(size))
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_face", lambda face_width: pygame.Surface((200, 200), pygame.SRCALPHA))
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_visemes", lambda w, h: {0: pygame.Surface((10, 10), pygame.SRCALPHA)})
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_eyes", lambda w, h: {})
    monkeypatch.setattr("backend.rendering.avatar_test_animations.load_idle_mouths", lambda w, h: {})
    monkeypatch.setattr("pygame.event.get", lambda: [types.SimpleNamespace(type=pygame.QUIT)])
    run_animation_viewer()
