"""Interactive animation browser for debugging eye/mouth/emote motion."""

from __future__ import annotations

import os
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.personalities import load_personality
from backend.rendering.avatar_assets import load_eyes, load_face, load_idle_mouths, load_visemes
from backend.rendering.avatar_config import BG_COLOR, WINDOW_HEIGHT, WINDOW_WIDTH
from backend.rendering.avatar_controllers import EYE_SEQUENCE_CATALOG
from backend.rendering.avatar_utils import blit_centered, smoothstep


def test_animations(personality_id: str = "peter") -> None:
    """Interactive animation browser: play eye sequences, idle mouths, and emotes.

    Controls:
      1 / 2 / 3    — switch category (eyes / mouths / emotes)
      Left / Right — select animation
      Space        — play / replay selected animation
      A            — toggle auto-cycle
      Esc / Q      — quit

    Uses lightweight manual state (no autonomous timers) so that only
    user-triggered animations play.
    """

    personality = load_personality(personality_id)
    ap = personality.assets
    labels = personality.effective_viseme_labels
    layout = personality.face_layout

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption(f"Animation Test — {personality.display_name}")
    clock = pygame.time.Clock()

    face_width: int = 530
    mouth_max_w = int(face_width * layout.mouth_width_ratio)
    mouth_max_h = int(face_width * layout.mouth_height_ratio)
    eye_max_w = int(face_width * layout.eye_width_ratio)
    eye_max_h = int(face_width * layout.eye_height_ratio)

    face = load_face(ap.face_root, face_width, face_filename=ap.face_filename)
    viseme_images = load_visemes(
        ap.sprites_root,
        mouth_max_w,
        mouth_max_h,
        visemes_dir=ap.visemes_dir,
        labels=labels,
    )
    eye_images = load_eyes(ap.sprites_root, eye_max_w, eye_max_h, eyes_dir=ap.eyes_dir)
    idle_names = personality.all_idle_mouth_asset_names()
    idle_mouth_images = load_idle_mouths(
        ap.sprites_root,
        idle_names,
        mouth_max_w,
        mouth_max_h,
        visemes_dir=ap.visemes_dir,
    )

    if not face:
        print("ERROR: avatar-base.png not found")
        pygame.quit()
        return

    face_x = (WINDOW_WIDTH - face.get_width()) // 2
    face_y = 60
    mouth_cx = face_x + face.get_width() // 2
    mouth_cy = face_y + int(face.get_height() * layout.mouth_y_ratio)
    eye_cx = face_x + face.get_width() // 2
    eye_cy = face_y + int(face.get_height() * layout.eye_y_ratio)

    font = pygame.font.SysFont("monospace", 15)
    font_big = pygame.font.SysFont("monospace", 18, bold=True)

    # Build category lists.
    cat_names = ["Eye Sequences", "Idle Mouths", "Emotes"]
    idle_mouth_catalog: list[str] = sorted(idle_mouth_images.keys())
    emote_catalog = [e for e in personality.emotes if e.mouth in idle_mouth_images]

    cat_items: list[list[str]] = [
        [name for name, _ in EYE_SEQUENCE_CATALOG],
        idle_mouth_catalog,
        [e.name for e in emote_catalog],
    ]

    cat_idx = 0
    item_idx = 0
    auto_cycle = False
    auto_timer_ms: float = 0.0
    AUTO_DELAY_MS: float = 4000.0

    # ---- Manual eye sequence state (no autonomous timers) -----------------
    eye_seq: list[tuple[int, float, float]] = []
    eye_seq_step: int = 0
    eye_seq_step_start: float = 0.0
    eye_seq_active: bool = False
    eye_prev: int = 0
    eye_cur: int = 0
    eye_trans_start: float = 0.0
    eye_trans_dur: float = 0.0
    eye_in_trans: bool = False

    def _eye_t(now: float) -> float:
        nonlocal eye_in_trans
        if not eye_in_trans:
            return 1.0
        raw = (now - eye_trans_start) / max(1.0, eye_trans_dur)
        t = smoothstep(min(1.0, raw))
        if t >= 1.0:
            eye_in_trans = False
        return t

    def _eye_go(idx: int, dur_ms: float, now: float) -> None:
        nonlocal eye_prev, eye_cur, eye_trans_start, eye_trans_dur, eye_in_trans
        if idx == eye_cur and not eye_in_trans:
            return
        eye_prev = eye_cur if _eye_t(now) >= 0.5 else eye_prev
        eye_cur = idx
        eye_trans_start = now
        eye_trans_dur = dur_ms
        eye_in_trans = True

    def _eye_start_seq(seq: list[tuple[int, float, float]], now: float) -> None:
        nonlocal eye_seq, eye_seq_step, eye_seq_step_start, eye_seq_active
        eye_seq = seq
        eye_seq_step = 0
        eye_seq_step_start = now
        eye_seq_active = True
        idx, trans_ms, _ = seq[0]
        _eye_go(idx, trans_ms, now)

    def _eye_advance(now: float) -> None:
        nonlocal eye_seq_step, eye_seq_step_start, eye_seq_active
        if not eye_seq_active:
            return
        _, trans_ms, hold_ms = eye_seq[eye_seq_step]
        if now - eye_seq_step_start >= trans_ms + hold_ms:
            eye_seq_step += 1
            if eye_seq_step >= len(eye_seq):
                eye_seq_active = False
                _eye_go(0, 200.0, now)
                return
            nidx, ntrans, _ = eye_seq[eye_seq_step]
            _eye_go(nidx, ntrans, now)
            eye_seq_step_start = now

    # ---- Manual mouth state (no autonomous timers) ------------------------
    mouth_cur: str | None = None
    mouth_prev: str | None = None
    mouth_trans_start: float = 0.0
    mouth_trans_dur: float = 0.0
    mouth_in_trans: bool = False
    mouth_holding: bool = False
    mouth_return_ms: float = 0.0

    def _mouth_t(now: float) -> float:
        nonlocal mouth_in_trans
        if not mouth_in_trans:
            return 1.0
        raw = (now - mouth_trans_start) / max(1.0, mouth_trans_dur)
        t = smoothstep(min(1.0, raw))
        if t >= 1.0:
            mouth_in_trans = False
        return t

    def _mouth_go(name: str | None, dur_ms: float, now: float) -> None:
        nonlocal mouth_prev, mouth_cur, mouth_trans_start, mouth_trans_dur, mouth_in_trans
        visible = mouth_cur if _mouth_t(now) >= 0.5 else mouth_prev
        if name == visible:
            return
        mouth_prev = visible
        mouth_cur = name
        mouth_trans_start = now
        mouth_trans_dur = dur_ms
        mouth_in_trans = True

    # ---- Playback tracking ------------------------------------------------
    playing = False
    play_start_ms: float = 0.0
    play_name: str = ""

    def _trigger(cat: int, idx: int, now: float) -> None:
        nonlocal playing, play_start_ms, play_name, mouth_holding, mouth_return_ms
        playing = True
        play_start_ms = now

        if cat == 0:  # eye sequence
            name, seq = EYE_SEQUENCE_CATALOG[idx]
            play_name = name
            _eye_start_seq(seq, now)
        elif cat == 1:  # idle mouth
            name = cat_items[1][idx]
            play_name = name
            _mouth_go(name, 300.0, now)
            mouth_holding = True
            mouth_return_ms = now + 2500.0
        elif cat == 2:  # emote
            emote = emote_catalog[idx]
            play_name = emote.name
            _eye_start_seq(emote.eye_seq, now)
            _mouth_go(emote.mouth, 300.0, now)
            mouth_holding = True
            mouth_return_ms = now + emote.mouth_hold_ms

    global_start_ms = time.time() * 1000
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_1:
                    cat_idx, item_idx = 0, 0
                elif event.key == pygame.K_2:
                    cat_idx, item_idx = 1, 0
                elif event.key == pygame.K_3:
                    cat_idx, item_idx = 2, 0
                elif event.key == pygame.K_RIGHT and cat_items[cat_idx]:
                    item_idx = (item_idx + 1) % len(cat_items[cat_idx])
                elif event.key == pygame.K_LEFT and cat_items[cat_idx]:
                    item_idx = (item_idx - 1) % len(cat_items[cat_idx])
                elif event.key == pygame.K_SPACE and cat_items[cat_idx]:
                    elapsed = time.time() * 1000 - global_start_ms
                    _trigger(cat_idx, item_idx, elapsed)
                elif event.key == pygame.K_a:
                    auto_cycle = not auto_cycle
                    auto_timer_ms = time.time() * 1000

        now_ms = time.time() * 1000
        elapsed_ms = now_ms - global_start_ms

        if auto_cycle and cat_items[cat_idx] and now_ms - auto_timer_ms > AUTO_DELAY_MS:
            _trigger(cat_idx, item_idx, elapsed_ms)
            item_idx = (item_idx + 1) % len(cat_items[cat_idx])
            auto_timer_ms = now_ms

        if playing and elapsed_ms - play_start_ms > 4000:
            playing = False

        _eye_advance(elapsed_ms)

        if mouth_holding and elapsed_ms >= mouth_return_ms:
            mouth_holding = False
            _mouth_go(None, 350.0, elapsed_ms)

        et = _eye_t(elapsed_ms)
        mt = _mouth_t(elapsed_ms)

        # ---- draw ---------------------------------------------------------
        screen.fill(BG_COLOR)
        screen.blit(face, (face_x, face_y))

        # Eyes.
        if eye_images:
            if et >= 1.0 or eye_prev == eye_cur:
                surf = eye_images.get(eye_cur)
                if surf:
                    blit_centered(screen, surf, eye_cx, eye_cy)
            elif et >= 0.5:
                to_surf = eye_images.get(eye_cur)
                from_surf = eye_images.get(eye_prev)
                if to_surf:
                    blit_centered(screen, to_surf, eye_cx, eye_cy)
                if from_surf:
                    blit_centered(screen, from_surf, eye_cx, eye_cy, alpha=int((1.0 - et) * 2 * 255))
            else:
                to_surf = eye_images.get(eye_cur)
                from_surf = eye_images.get(eye_prev)
                if from_surf:
                    blit_centered(screen, from_surf, eye_cx, eye_cy)
                if to_surf:
                    blit_centered(screen, to_surf, eye_cx, eye_cy, alpha=int(et * 2 * 255))

        # Mouth.
        def _get_mouth_surf(name: str | None) -> pygame.Surface | None:
            if name is None:
                return viseme_images.get(0)
            return idle_mouth_images.get(name)

        cur_surf = _get_mouth_surf(mouth_cur)
        prev_surf = _get_mouth_surf(mouth_prev)

        if mt >= 1.0 or mouth_prev == mouth_cur:
            if cur_surf:
                blit_centered(screen, cur_surf, mouth_cx, mouth_cy)
        elif mt >= 0.5:
            if cur_surf:
                blit_centered(screen, cur_surf, mouth_cx, mouth_cy)
            if prev_surf and prev_surf is not cur_surf:
                blit_centered(screen, prev_surf, mouth_cx, mouth_cy, alpha=int((1.0 - mt) * 2 * 255))
        else:
            if prev_surf:
                blit_centered(screen, prev_surf, mouth_cx, mouth_cy)
            if cur_surf and cur_surf is not prev_surf:
                blit_centered(screen, cur_surf, mouth_cx, mouth_cy, alpha=int(mt * 2 * 255))

        cat_label = cat_names[cat_idx]
        items = cat_items[cat_idx]
        item_label = items[item_idx] if items else "(empty)"
        count = len(items)

        lines = [
            f"{cat_label}:  {item_label}  [{item_idx + 1}/{count}]",
            f"Playing: {play_name}" if playing else "Idle",
            f"Eye:{eye_cur:2d}  Mouth:{mouth_cur or 'sil'}",
            "",
            "1/2/3=category  Left/Right=select  Space=play",
            f"A=auto-cycle ({'ON' if auto_cycle else 'OFF'})  Esc=quit",
        ]
        for i, line in enumerate(lines):
            f = font_big if i == 0 else font
            color = (255, 255, 100) if i == 0 else (200, 200, 200)
            screen.blit(f.render(line, True, color), (10, WINDOW_HEIGHT - 130 + i * 19))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

