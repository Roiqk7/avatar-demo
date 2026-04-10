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

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

from backend.models import PipelineResult, VisemeEvent
from backend.rendering.avatar_assets import load_eyes, load_face, load_idle_mouths, load_visemes
from backend.rendering.avatar_config import (
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

    def __init__(self, *, oneshot: bool = False) -> None:
        self._oneshot: bool = oneshot

        pygame.init()
        self._screen: pygame.Surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Avatar Demo")
        self._clock: pygame.time.Clock = pygame.time.Clock()

        face_width: int = 530
        mouth_max_w: int = int(face_width * MOUTH_WIDTH_RATIO)
        mouth_max_h: int = int(face_width * MOUTH_HEIGHT_RATIO)
        eye_max_w: int = int(face_width * EYE_WIDTH_RATIO)
        eye_max_h: int = int(face_width * EYE_HEIGHT_RATIO)

        self._face: pygame.Surface | None = load_face(face_width)
        self._viseme_images: dict[int, pygame.Surface] = load_visemes(mouth_max_w, mouth_max_h)
        self._eye_images: dict[int, pygame.Surface] = load_eyes(eye_max_w, eye_max_h)
        self._idle_mouth_images: dict[str, pygame.Surface] = load_idle_mouths(mouth_max_w, mouth_max_h)

        if not self._face or not self._viseme_images:
            logger.info("[AVT] No assets found — cannot render avatar")
            self._ready = False
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
        self._mouth_cy: int = face_y + int(self._face.get_height() * MOUTH_Y_RATIO)
        self._eye_cx: int = face_x + self._face.get_width() // 2
        self._eye_cy: int = face_y + int(self._face.get_height() * EYE_Y_RATIO)

        if self._idle_mouth_images:
            logger.info("[AVT] Loaded %d idle mouth sprites", len(self._idle_mouth_images))

        pygame.mixer.init(frequency=16000, size=-16, channels=1)
        self._font: pygame.font.Font = pygame.font.SysFont("monospace", 16)
        self._eye_ctrl: EyeController = EyeController()
        self._mouth_ctrl: MouthController = MouthController()
        self._emote_ctrl: EmoteController = EmoteController()

        # Playback state.
        self._visemes: list[VisemeEvent] = []
        self._audio_start_ms: float = 0.0
        self._playing: bool = False
        self._status_text: str = "Listening..."
        self._sound: pygame.mixer.Sound | None = None

        # Thread-safe communication.
        self._play_queue: queue.Queue[PipelineResult] = queue.Queue()
        self._close_requested: bool = False

    @property
    def ready(self) -> bool:
        return self._ready

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

    def run_forever(self) -> None:
        """Main render loop — blocks until close is requested or window is closed.

        Must be called from the main thread on macOS.
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
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
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
                mouth_label = VISEME_LABELS[active_viseme] if active_viseme < len(VISEME_LABELS) else "?"
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

            pygame.display.flip()
            self._clock.tick(60)

        pygame.mixer.quit()
        pygame.quit()
        logger.debug("Avatar window closed")


def render_avatar(result: PipelineResult) -> None:
    """Open a pygame window, play audio, animate, then close."""
    window = AvatarWindow(oneshot=True)
    if not window.ready:
        return
    window.play(result)
    window.run_forever()

