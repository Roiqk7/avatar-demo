"""Pygame avatar window + rendering loop.

This module owns all pygame setup, the main loop, and the composition of
face/eyes/mouth onto the screen. Animation decisions are delegated to the
controller state machines in `backend.rendering.avatar_controllers`.
"""

from __future__ import annotations

import io
import logging
import os
import queue
import time
from collections.abc import Callable

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.models import PipelineResult, VisemeEvent
from backend.personalities import Personality
from backend.rendering.avatar_assets import load_eyes, load_face, load_idle_mouths, load_visemes
from backend.rendering.avatar_config import BG_COLOR, WINDOW_HEIGHT, WINDOW_WIDTH
from backend.rendering.avatar_controllers import EmoteController, EyeController, MouthController
from backend.rendering.avatar_utils import blit_centered

logger: logging.Logger = logging.getLogger("backend.avatar")


def get_active_viseme(visemes: list[VisemeEvent], elapsed_ms: float) -> int:
    """Return the viseme id active at `elapsed_ms`."""
    active: int = 0
    for v in visemes:
        if v.offset_ms <= elapsed_ms:
            active = v.id
        else:
            break
    return active


class AvatarWindow:
    """Long-lived pygame avatar window.

    Call :meth:`run_forever` from the **main thread** (required on macOS).
    Feed it work via :meth:`play` (thread-safe) and shut it down with
    :meth:`request_close` (thread-safe).
    """

    def __init__(self, personality: Personality, *, oneshot: bool = False) -> None:
        self._oneshot: bool = oneshot
        self._bootstrap_pygame()
        self._apply_personality(personality)

    def _bootstrap_pygame(self) -> None:
        pygame.init()
        self._screen: pygame.Surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self._clock: pygame.time.Clock = pygame.time.Clock()
        pygame.mixer.init(frequency=16000, size=-16, channels=1)
        self._font: pygame.font.Font = pygame.font.SysFont("monospace", 16)
        self._play_queue: queue.Queue[PipelineResult] = queue.Queue()
        self._close_requested: bool = False

    def _apply_personality(self, personality: Personality) -> None:
        if getattr(self, "_sound", None) is not None:
            try:
                self._sound.stop()
            except Exception:
                pass
        self._sound = None

        self._personality: Personality = personality
        self._viseme_labels: tuple[str, ...] = personality.effective_viseme_labels
        pygame.display.set_caption(personality.window_title)

        face_width: int = 530
        layout = personality.face_layout
        mouth_max_w: int = int(face_width * layout.mouth_width_ratio)
        mouth_max_h: int = int(face_width * layout.mouth_height_ratio)
        eye_max_w: int = int(face_width * layout.eye_width_ratio)
        eye_max_h: int = int(face_width * layout.eye_height_ratio)

        ap = personality.assets
        self._face: pygame.Surface | None = load_face(
            ap.face_root,
            face_width,
            face_filename=ap.face_filename,
        )
        self._viseme_images: dict[int, pygame.Surface] = load_visemes(
            ap.sprites_root,
            mouth_max_w,
            mouth_max_h,
            visemes_dir=ap.visemes_dir,
            labels=self._viseme_labels,
        )
        self._eye_images: dict[int, pygame.Surface] = load_eyes(
            ap.sprites_root,
            eye_max_w,
            eye_max_h,
            eyes_dir=ap.eyes_dir,
        )
        idle_names = personality.all_idle_mouth_asset_names()
        self._idle_mouth_images: dict[str, pygame.Surface] = load_idle_mouths(
            ap.sprites_root,
            idle_names,
            mouth_max_w,
            mouth_max_h,
            visemes_dir=ap.visemes_dir,
        )

        if not self._face or not self._viseme_images:
            logger.info("[AVT] No assets found — cannot render avatar")
            self._ready = False
            self._visemes = []
            self._audio_start_ms = 0.0
            self._playing = False
            self._status_text = "Listening..."
            return
        self._ready = True

        if not self._eye_images:
            logger.warning("[AVT] No eye assets found — rendering without eyes")
        else:
            logger.info("[AVT] Loaded %d eye frames", len(self._eye_images))

        face_x: int = (WINDOW_WIDTH - self._face.get_width()) // 2
        face_y: int = 60
        self._face_pos = (face_x, face_y)
        self._mouth_cx: int = face_x + self._face.get_width() // 2
        self._mouth_cy: int = face_y + int(self._face.get_height() * layout.mouth_y_ratio)
        self._eye_cx: int = face_x + self._face.get_width() // 2
        self._eye_cy: int = face_y + int(self._face.get_height() * layout.eye_y_ratio)

        if self._idle_mouth_images:
            logger.info("[AVT] Loaded %d idle mouth sprites", len(self._idle_mouth_images))

        self._eye_ctrl: EyeController = EyeController(personality.eye_config)
        self._mouth_ctrl: MouthController = MouthController(
            personality.idle_mouth_pools,
            personality.mouth_timing,
            idle_animation_enabled=personality.mouth_idle_enabled,
        )
        self._emote_ctrl: EmoteController = EmoteController(
            list(personality.emotes),
            personality.emote_timing,
        )

        self._visemes = []
        self._audio_start_ms = 0.0
        self._playing = False
        self._status_text = "Listening..."

    def apply_personality(self, personality: Personality) -> None:
        """Reload avatar assets and motion for a different personality (main thread only)."""
        self._apply_personality(personality)

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def is_playing(self) -> bool:
        return self._playing

    # ---- thread-safe API --------------------------------------------------

    def play(self, result: PipelineResult) -> None:
        """Enqueue a pipeline result to be played (thread-safe)."""
        self._play_queue.put(result)

    def request_close(self) -> None:
        """Signal the render loop to shut down (thread-safe)."""
        self._close_requested = True

    # ---- main-thread only -------------------------------------------------

    def _start_playback(self, result: PipelineResult) -> None:
        """Begin playing a new result (main thread only)."""
        self._visemes = result.tts.visemes
        self._status_text = result.response_text[:40]
        has_audio: bool = len(result.tts.audio_data) > 0

        if has_audio:
            self._sound = pygame.mixer.Sound(io.BytesIO(result.tts.audio_data))
            self._sound.play()
        else:
            self._sound = None

        self._audio_start_ms = time.time() * 1000
        self._playing = True
        self._mouth_ctrl.notify_speaking()
        self._emote_ctrl.notify_speaking()

        logger.debug(
            "[AVT] Playing — %d visemes, audio=%s",
            len(self._visemes),
            "yes" if has_audio else "no",
        )

    def _resolve_mouth(self, name: str | None) -> pygame.Surface | None:
        """Map a mouth name to a surface. None -> sil viseme."""
        if name is None:
            return self._viseme_images.get(0)
        return self._idle_mouth_images.get(name)

    def _draw_idle_mouth(self, prev_name: str | None, cur_name: str | None, t: float) -> None:
        """Draw idle mouth with cross-fade between prev and current."""
        prev_surf = self._resolve_mouth(prev_name)
        cur_surf = self._resolve_mouth(cur_name)

        def _blit(surf: pygame.Surface, alpha: int = 255) -> None:
            blit_centered(self._screen, surf, self._mouth_cx, self._mouth_cy, alpha=alpha)

        if t >= 1.0 or prev_name == cur_name:
            if cur_surf:
                _blit(cur_surf)
        elif t >= 0.5:
            if cur_surf:
                _blit(cur_surf)
            if prev_surf and prev_surf is not cur_surf:
                _blit(prev_surf, int((1.0 - t) * 2 * 255))
        else:
            if prev_surf:
                _blit(prev_surf)
            if cur_surf and cur_surf is not prev_surf:
                _blit(cur_surf, int(t * 2 * 255))

    def run_forever(
        self,
        *,
        on_keydown: Callable[[pygame.event.Event], bool] | None = None,
        on_after_draw: Callable[[pygame.Surface], None] | None = None,
    ) -> None:
        """Main render loop — blocks until close is requested or window is closed.

        Must be called from the main thread on macOS.

        If ``on_keydown`` is set, it is called for each ``KEYDOWN`` event; return
        ``True`` if the event was handled (default Escape handling is skipped).

        If ``on_after_draw`` is set, it runs after the default HUD is drawn and
        before :func:`pygame.display.flip` (e.g. for test-mode overlays).
        """
        if not self._ready:
            pygame.quit()
            return

        global_start_ms: float = time.time() * 1000
        running: bool = True

        while running:
            # ---- events ---------------------------------------------------
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if on_keydown is not None and on_keydown(event):
                        continue
                    if event.key == pygame.K_ESCAPE:
                        running = False

            if self._close_requested:
                running = False
                continue

            # ---- consume queued playback requests -------------------------
            try:
                result = self._play_queue.get_nowait()
                self._start_playback(result)
            except queue.Empty:
                pass

            # ---- timing ---------------------------------------------------
            now_ms: float = time.time() * 1000
            eye_elapsed_ms: float = now_ms - global_start_ms

            if self._playing:
                audio_elapsed_ms: float = now_ms - self._audio_start_ms
                active_viseme: int = get_active_viseme(self._visemes, audio_elapsed_ms)

                audio_busy = self._sound is not None and pygame.mixer.get_busy()
                if not audio_busy and audio_elapsed_ms > 500:
                    self._playing = False
                    active_viseme = 0
                    self._mouth_ctrl.notify_idle(eye_elapsed_ms)
                    self._emote_ctrl.notify_idle(eye_elapsed_ms)
                    if self._oneshot:
                        running = False
            else:
                active_viseme = 0
                self._mouth_ctrl.notify_idle(eye_elapsed_ms)
                self._emote_ctrl.notify_idle(eye_elapsed_ms)

            # Coordinated emotes drive both eye + mouth when active.
            emote_active = self._emote_ctrl.update(
                eye_elapsed_ms,
                eye_ctrl=self._eye_ctrl,
                mouth_ctrl=self._mouth_ctrl,
                available_mouths=self._idle_mouth_images,
            )

            blend = self._eye_ctrl.get_blend(eye_elapsed_ms)

            # ---- draw -----------------------------------------------------
            self._screen.fill(BG_COLOR)
            self._screen.blit(self._face, self._face_pos)

            # Eyes
            if self._eye_images:
                if blend.t >= 1.0 or blend.from_idx == blend.to_idx:
                    surf = self._eye_images.get(blend.to_idx)
                    if surf:
                        blit_centered(self._screen, surf, self._eye_cx, self._eye_cy)
                elif blend.t >= 0.5:
                    to_surf = self._eye_images.get(blend.to_idx)
                    from_surf = self._eye_images.get(blend.from_idx)
                    if to_surf:
                        blit_centered(self._screen, to_surf, self._eye_cx, self._eye_cy)
                    if from_surf:
                        blit_centered(
                            self._screen,
                            from_surf,
                            self._eye_cx,
                            self._eye_cy,
                            alpha=int((1.0 - blend.t) * 2 * 255),
                        )
                else:
                    to_surf = self._eye_images.get(blend.to_idx)
                    from_surf = self._eye_images.get(blend.from_idx)
                    if from_surf:
                        blit_centered(self._screen, from_surf, self._eye_cx, self._eye_cy)
                    if to_surf:
                        blit_centered(
                            self._screen,
                            to_surf,
                            self._eye_cx,
                            self._eye_cy,
                            alpha=int(blend.t * 2 * 255),
                        )

            # Mouth
            if self._playing:
                mouth = self._viseme_images.get(active_viseme)
                if mouth:
                    blit_centered(self._screen, mouth, self._mouth_cx, self._mouth_cy)
                n_labels = len(self._viseme_labels)
                mouth_label = (
                    self._viseme_labels[active_viseme] if active_viseme < n_labels else "?"
                )
            else:
                idle_prev, idle_cur, idle_t = self._mouth_ctrl.get_idle_mouth(
                    eye_elapsed_ms,
                    self._idle_mouth_images,
                )
                if not emote_active:
                    self._draw_idle_mouth(idle_prev, idle_cur, idle_t)
                else:
                    # Emotes have already forced the mouth controller state.
                    self._draw_idle_mouth(idle_prev, idle_cur, idle_t)
                mouth_label = idle_cur or "sil"

            state: str = "Speaking" if self._playing else "Listening..."
            status: str = (
                f"{state} | Mouth:{mouth_label}"
                f" | Eye:{blend.to_idx:2d}({self._eye_ctrl.state_label})"
                f" | {self._status_text}"
            )
            self._screen.blit(
                self._font.render(status, True, (200, 200, 200)),
                (10, WINDOW_HEIGHT - 30),
            )
            if on_after_draw is not None:
                on_after_draw(self._screen)

            pygame.display.flip()
            self._clock.tick(60)

        pygame.mixer.quit()
        pygame.quit()
        logger.debug("Avatar window closed")


def render_avatar(result: PipelineResult, personality: Personality) -> None:
    """Open a pygame window, play audio, animate, then close."""
    window = AvatarWindow(personality, oneshot=True)
    if not window.ready:
        return
    window.play(result)
    window.run_forever()
