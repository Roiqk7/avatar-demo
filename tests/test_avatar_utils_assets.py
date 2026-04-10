from pathlib import Path

import pygame
import pytest

from backend.rendering import avatar_utils
from backend.rendering.avatar_assets import load_eyes, load_face, load_idle_mouths, load_visemes
from backend.rendering.avatar_config import IDLE_MOUTH_NAMES, VISEME_LABELS


class _FakeImage:
    def __init__(self, value):
        self.value = value

    def convert_alpha(self):
        return self.value


def test_smoothstep_bounds():
    assert avatar_utils.smoothstep(-1.0) == 0.0
    assert avatar_utils.smoothstep(2.0) == 1.0


@pytest.mark.parametrize("t", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_smoothstep_monotonic_range(t: float):
    out = avatar_utils.smoothstep(t)
    assert 0.0 <= out <= 1.0


def test_scale_to_fit_uses_target_size(monkeypatch: pytest.MonkeyPatch):
    surface = pygame.Surface((200, 100))
    seen = {}

    def _fake_scale(src, size):
        seen["size"] = size
        return pygame.Surface(size)

    monkeypatch.setattr("pygame.transform.smoothscale", _fake_scale)
    out = avatar_utils.scale_to_fit(surface, 50, 50)
    assert seen["size"] == (50, 25)
    assert out.get_size() == (50, 25)


def test_scale_to_width_uses_target_width(monkeypatch: pytest.MonkeyPatch):
    surface = pygame.Surface((200, 100))
    seen = {}

    def _fake_scale(src, size):
        seen["size"] = size
        return pygame.Surface(size)

    monkeypatch.setattr("pygame.transform.smoothscale", _fake_scale)
    out = avatar_utils.scale_to_width(surface, 40)
    assert seen["size"] == (40, 20)
    assert out.get_size() == (40, 20)


def test_trim_to_content_returns_original_on_error(monkeypatch: pytest.MonkeyPatch):
    surf = pygame.Surface((10, 10), pygame.SRCALPHA)

    def _raise(_):
        raise RuntimeError("fail")

    monkeypatch.setattr("pygame.surfarray.pixels_alpha", _raise)
    out = avatar_utils.trim_to_content(surf)
    assert out is surf


def test_trim_to_content_trims_transparent_border():
    surf = pygame.Surface((12, 12), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    pygame.draw.rect(surf, (255, 255, 255, 255), pygame.Rect(4, 5, 2, 2))
    out = avatar_utils.trim_to_content(surf, pad=0)
    assert out.get_size() == (2, 2)


def test_trim_to_content_all_transparent_returns_original():
    surf = pygame.Surface((10, 10), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    out = avatar_utils.trim_to_content(surf)
    assert out is surf


def test_blit_centered_skips_alpha_zero():
    screen = pygame.Surface((20, 20), pygame.SRCALPHA)
    surf = pygame.Surface((4, 4), pygame.SRCALPHA)
    avatar_utils.blit_centered(screen, surf, 10, 10, alpha=0)
    assert screen.get_at((10, 10)).a == 0


def test_blit_centered_draws_with_full_alpha():
    screen = pygame.Surface((20, 20), pygame.SRCALPHA)
    surf = pygame.Surface((4, 4), pygame.SRCALPHA)
    surf.fill((255, 0, 0, 255))
    avatar_utils.blit_centered(screen, surf, 10, 10, alpha=255)
    assert screen.get_at((10, 10)).r == 255


def test_blit_centered_applies_partial_alpha_and_resets():
    screen = pygame.Surface((20, 20), pygame.SRCALPHA)
    surf = pygame.Surface((4, 4), pygame.SRCALPHA)
    surf.fill((100, 100, 100, 255))
    avatar_utils.blit_centered(screen, surf, 10, 10, alpha=100)
    assert surf.get_alpha() == 255


def test_load_face_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("backend.rendering.avatar_assets.ASSETS_DIR", tmp_path)
    assert load_face(100) is None


def test_load_face_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    (tmp_path / "avatar-base.png").write_bytes(b"x")
    monkeypatch.setattr("backend.rendering.avatar_assets.ASSETS_DIR", tmp_path)
    monkeypatch.setattr("pygame.image.load", lambda path: _FakeImage("raw-face"))
    monkeypatch.setattr("backend.rendering.avatar_assets.scale_to_fit", lambda surf, w, h: ("scaled", surf, w, h))
    out = load_face(123)
    assert out == ("scaled", "raw-face", 123, 123)


def test_load_visemes_only_existing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    vis_dir = tmp_path / "visemes"
    vis_dir.mkdir()
    (vis_dir / f"viseme-00-{VISEME_LABELS[0]}.png").write_bytes(b"x")
    (vis_dir / f"viseme-05-{VISEME_LABELS[5]}.png").write_bytes(b"x")
    monkeypatch.setattr("backend.rendering.avatar_assets.ASSETS_DIR", tmp_path)
    monkeypatch.setattr("pygame.image.load", lambda path: _FakeImage(f"img:{Path(path).name}"))
    monkeypatch.setattr("backend.rendering.avatar_assets.scale_to_fit", lambda surf, w, h: f"scaled:{surf}")
    images = load_visemes(10, 11)
    assert set(images.keys()) == {0, 5}


def test_load_idle_mouths_only_existing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    vis_dir = tmp_path / "visemes"
    vis_dir.mkdir()
    first = IDLE_MOUTH_NAMES[0]
    second = IDLE_MOUTH_NAMES[1]
    (vis_dir / f"viseme-{first}.png").write_bytes(b"x")
    (vis_dir / f"viseme-{second}.png").write_bytes(b"x")
    monkeypatch.setattr("backend.rendering.avatar_assets.ASSETS_DIR", tmp_path)
    monkeypatch.setattr("pygame.image.load", lambda path: _FakeImage(f"img:{Path(path).name}"))
    monkeypatch.setattr("backend.rendering.avatar_assets.scale_to_fit", lambda surf, w, h: f"scaled:{surf}")
    images = load_idle_mouths(10, 11)
    assert set(images.keys()) == {first, second}


def test_load_eyes_returns_empty_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("backend.rendering.avatar_assets.ASSETS_DIR", tmp_path)
    assert load_eyes(10, 10) == {}


def test_load_eyes_loads_valid_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    eyes = tmp_path / "eyes"
    eyes.mkdir()
    (eyes / "eye-00-open.png").write_bytes(b"x")
    (eyes / "eye-03-blink.png").write_bytes(b"x")
    monkeypatch.setattr("backend.rendering.avatar_assets.ASSETS_DIR", tmp_path)
    monkeypatch.setattr("pygame.image.load", lambda path: _FakeImage(f"img:{Path(path).name}"))
    monkeypatch.setattr("backend.rendering.avatar_assets.scale_to_fit", lambda surf, w, h: f"scaled:{surf}")
    out = load_eyes(15, 16)
    assert out[0] == "scaled:img:eye-00-open.png"
    assert out[3] == "scaled:img:eye-03-blink.png"


def test_load_eyes_skips_bad_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    eyes = tmp_path / "eyes"
    eyes.mkdir()
    (eyes / "eye-abc-invalid.png").write_bytes(b"x")
    (eyes / "eye-01-ok.png").write_bytes(b"x")
    monkeypatch.setattr("backend.rendering.avatar_assets.ASSETS_DIR", tmp_path)
    monkeypatch.setattr("pygame.image.load", lambda path: _FakeImage(f"img:{Path(path).name}"))
    monkeypatch.setattr("backend.rendering.avatar_assets.scale_to_fit", lambda surf, w, h: f"scaled:{surf}")
    out = load_eyes(20, 20)
    assert set(out.keys()) == {1}

