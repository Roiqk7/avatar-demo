"""Interactive sprite viewer for debugging avatar assets."""

from __future__ import annotations

import os
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.rendering.avatar_assets import load_eyes, load_face, load_visemes
from backend.rendering.avatar_config import (
    ASSETS_DIR,
    BG_COLOR,
    EYE_HEIGHT_RATIO,
    EYE_WIDTH_RATIO,
    EYE_Y_RATIO,
    MOUTH_HEIGHT_RATIO,
    MOUTH_WIDTH_RATIO,
    MOUTH_Y_RATIO,
    VISEME_LABELS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)


def test_sprites() -> None:
    """Interactive sprite viewer: shows each eye and viseme overlaid on the face.

    Controls:
      Left / Right  — previous / next sprite
      E             — switch to eye sprites
      V             — switch to viseme sprites
      Space         — toggle auto-cycle (2 s per frame)
      Esc / Q       — quit
    """

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Sprite Test Viewer")
    clock = pygame.time.Clock()

    face_width: int = 530
    mouth_max_w = int(face_width * MOUTH_WIDTH_RATIO)
    mouth_max_h = int(face_width * MOUTH_HEIGHT_RATIO)
    eye_max_w = int(face_width * EYE_WIDTH_RATIO)
    eye_max_h = int(face_width * EYE_HEIGHT_RATIO)

    face = load_face(face_width)
    viseme_images = load_visemes(mouth_max_w, mouth_max_h)
    eye_images = load_eyes(eye_max_w, eye_max_h)

    if not face:
        print("ERROR: avatar-base.png not found")
        pygame.quit()
        return

    # Also load raw (un-trimmed, un-scaled) eyes for debug info.
    raw_eye_sizes: dict[int, tuple[int, int]] = {}
    eyes_dir = ASSETS_DIR / "eyes"
    if eyes_dir.exists():
        for path in sorted(eyes_dir.glob("eye-*.png")):
            try:
                idx = int(path.name.split("-")[1])
                raw = pygame.image.load(str(path)).convert_alpha()
                raw_eye_sizes[idx] = raw.get_size()
            except Exception:
                pass

    # Build a unified sprite list: (name, index, surface, kind).
    eye_list = [(f"eye-{i:02d}", i, eye_images[i], "eye") for i in sorted(eye_images)]
    vis_list = [
        (f"vis-{i:02d}-{VISEME_LABELS[i]}", i, viseme_images[i], "viseme") for i in sorted(viseme_images)
    ]

    sprites = eye_list  # start with eyes
    sprite_idx = 0
    auto_cycle = False
    last_cycle_ms: float = 0.0

    face_x = (WINDOW_WIDTH - face.get_width()) // 2
    face_y = 60
    mouth_cx = face_x + face.get_width() // 2
    mouth_cy = face_y + int(face.get_height() * MOUTH_Y_RATIO)
    eye_cx = face_x + face.get_width() // 2
    eye_cy = face_y + int(face.get_height() * EYE_Y_RATIO)

    font = pygame.font.SysFont("monospace", 15)
    font_big = pygame.font.SysFont("monospace", 18, bold=True)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_RIGHT:
                    sprite_idx = (sprite_idx + 1) % max(1, len(sprites))
                elif event.key == pygame.K_LEFT:
                    sprite_idx = (sprite_idx - 1) % max(1, len(sprites))
                elif event.key == pygame.K_e:
                    sprites = eye_list
                    sprite_idx = 0
                elif event.key == pygame.K_v:
                    sprites = vis_list
                    sprite_idx = 0
                elif event.key == pygame.K_SPACE:
                    auto_cycle = not auto_cycle
                    last_cycle_ms = time.time() * 1000

        now_ms = time.time() * 1000
        if auto_cycle and sprites and now_ms - last_cycle_ms > 2000:
            sprite_idx = (sprite_idx + 1) % len(sprites)
            last_cycle_ms = now_ms

        screen.fill(BG_COLOR)
        screen.blit(face, (face_x, face_y))

        if sprites:
            name, idx, surf, kind = sprites[sprite_idx]
            cx, cy = (eye_cx, eye_cy) if kind == "eye" else (mouth_cx, mouth_cy)

            x = cx - surf.get_width() // 2
            y = cy - surf.get_height() // 2
            screen.blit(surf, (x, y))

            # Draw crosshair at centre point.
            pygame.draw.line(screen, (255, 0, 0, 120), (cx - 12, cy), (cx + 12, cy), 1)
            pygame.draw.line(screen, (255, 0, 0, 120), (cx, cy - 12), (cx, cy + 12), 1)

            raw_info = ""
            if kind == "eye" and idx in raw_eye_sizes:
                rw, rh = raw_eye_sizes[idx]
                raw_info = f"  raw={rw}x{rh}"

            lines = [
                f"{name}  [{sprite_idx + 1}/{len(sprites)}]  ({'EYES' if kind == 'eye' else 'VISEMES'})",
                f"scaled={surf.get_width()}x{surf.get_height()}{raw_info}",
                f"pos=({x},{y})  centre=({cx},{cy})",
                f"face={face.get_width()}x{face.get_height()}  eye_max={eye_max_w}x{eye_max_h}",
                "",
                "Left/Right=prev/next  E=eyes  V=visemes",
                f"Space=auto-cycle ({'ON' if auto_cycle else 'OFF'})  Esc=quit",
            ]
            for i, line in enumerate(lines):
                f = font_big if i == 0 else font
                color = (255, 255, 100) if i == 0 else (200, 200, 200)
                screen.blit(f.render(line, True, color), (10, WINDOW_HEIGHT - 140 + i * 19))
        else:
            screen.blit(font_big.render("No sprites loaded!", True, (255, 80, 80)), (10, WINDOW_HEIGHT - 40))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
