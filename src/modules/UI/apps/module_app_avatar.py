"""
Module: Avatar App
Description: Pygame app that renders the character avatar with animated blinking
             and talking-state mouth movement — mirrors the holo.html endpoint
             behavior but runs locally on the OpenGL/Pygame display.
             Follows the TARS-AI app framework (init/reset/update/render/cleanup).
"""

import os
import time
import random
import pygame

from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CAUTION_AMBER,
    CHROME_FACE,
    OFFLINE_GRAY,
    PAPER_TEXT,
    PHOSPHOR_CYAN,
    READY_GREEN,
    draw_grid,
    draw_hazard_marks,
    draw_label,
    draw_status_bar,
    draw_title_bar,
    scale_for,
    scaled,
)
from modules.UI.module_ui_state import resolve_presentation

# ---------------------------------------------------------------------------
# Module-level state — set by module_chatui to drive the animation
# ---------------------------------------------------------------------------
_talking_state: bool = False
_emotion_request: str | None = None


def set_talking_state(is_talking: bool) -> None:
    """Signal whether TARS is currently speaking (called from module_chatui)."""
    global _talking_state
    _talking_state = is_talking


def set_emotion_request(emotion: str) -> None:
    """Queue an emotion change to be applied on the next update tick."""
    global _emotion_request
    _emotion_request = emotion


# ---------------------------------------------------------------------------
# Sprite key → filename suffix mapping (matches chatui _get_sprite_urls)
# ---------------------------------------------------------------------------
_SPRITE_KEYS = {
    "nottalking_open":   "nottalking_eyes_open",
    "nottalking_closed": "nottalking_eyes_closed",
    "talking_open":      "talking_eyes_open",
    "talking_closed":    "talking_eyes_closed",
}


class AvatarApp:
    """Animated character avatar for the local TARS display."""

    def __init__(self, screen: pygame.Surface, width: int, height: int) -> None:
        self.output_screen = screen
        self.logical_width = width
        self.logical_height = height
        self.width = height
        self.height = width
        self.screen = pygame.Surface((self.width, self.height))

        # Derive src/ base dir: this file lives at src/modules/UI/apps/
        self._base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            )
        )

        # Read character name from config
        try:
            from modules.module_config import load_config
            config = load_config()
            char_path = config["CHAR"].get("character_card_path", "")
            if char_path:
                self._char_name = os.path.splitext(os.path.basename(char_path))[0]
            else:
                self._char_name = config["CHAR"].get("character_name", "TARS")
        except Exception:
            self._char_name = "TARS"

        # Load initial sprites
        self._emotion = "neutral"
        self._sprites: dict[str, pygame.Surface | None] = {}
        self._load_sprites(self._emotion)

        # Animation state
        self._is_talking = False
        self._is_blinking = False
        self._next_blink = time.time() + 3.0 + random.random() * 2.0
        self._blink_end = 0.0
        self._talk_frame_timer = 0.0
        self._talk_frame_interval = 0.1   # seconds between mouth frames
        self._mouth_open = True

        self._machine_state = "STANDBY"
        self._battery = None
        self._alert = "NONE"
        self._connectivity = "N/A"

        # Cached scaled frame
        self._current_surf: pygame.Surface | None = None
        self._render_rect: pygame.Rect | None = None
        self._update_frame()

    # ------------------------------------------------------------------
    # Sprite loading
    # ------------------------------------------------------------------

    def _sprite_path(self, emotion: str, key: str) -> str:
        suffix = _SPRITE_KEYS[key]
        filename = f"{self._char_name}_{emotion}_{suffix}.png"
        return os.path.join(
            self._base_dir, "character", self._char_name,
            "images", emotion, "animation", filename
        )

    def _load_sprites(self, emotion: str) -> None:
        """Load all 4 sprite surfaces for *emotion*, falling back to neutral."""
        emo_dir = os.path.join(
            self._base_dir, "character", self._char_name,
            "images", emotion, "animation"
        )
        if not os.path.isdir(emo_dir):
            emotion = "neutral"

        sprites: dict[str, pygame.Surface | None] = {}
        for key in _SPRITE_KEYS:
            path = self._sprite_path(emotion, key)
            if os.path.isfile(path):
                try:
                    sprites[key] = pygame.image.load(path).convert_alpha()
                except Exception:
                    sprites[key] = None
            else:
                sprites[key] = None

        self._sprites = sprites
        self._emotion = emotion

    # ------------------------------------------------------------------
    # Frame selection (same logic as holo.html updateAvatarFrame)
    # ------------------------------------------------------------------

    def _frame_key(self) -> str:
        if self._is_talking:
            if self._is_blinking:
                return "talking_closed"
            return "talking_open" if self._mouth_open else "nottalking_open"
        return "nottalking_closed" if self._is_blinking else "nottalking_open"

    def _update_frame(self) -> None:
        """Resolve the current frame and cache a scaled version."""
        fallback_order = (
            self._frame_key(),
            "nottalking_open",
            "talking_open",
            "nottalking_closed",
            "talking_closed",
        )
        surf = None
        for k in fallback_order:
            surf = self._sprites.get(k)
            if surf is not None:
                break

        if surf is None:
            self._current_surf = None
            self._render_rect = None
            return

        # Character art is authored for the portrait logical canvas. Rotate it
        # into the final landscape composition before the app boundary rotates.
        oriented = pygame.transform.rotate(surf, 270)
        tinted = oriented.copy()
        tinted.fill((*CHROME_FACE, 255), special_flags=pygame.BLEND_RGBA_MULT)

        ui_scale = self.height / 320.0
        title_h = scaled(28, ui_scale)
        status_h = scaled(25, ui_scale)
        available = pygame.Rect(
            scaled(22, ui_scale), title_h + scaled(18, ui_scale),
            self.width - scaled(44, ui_scale),
            self.height - title_h - status_h - scaled(34, ui_scale),
        )
        img_w, img_h = tinted.get_size()
        image_scale = min(available.width / img_w, available.height / img_h)
        new_w, new_h = max(1, int(img_w * image_scale)), max(1, int(img_h * image_scale))
        self._current_surf = pygame.transform.smoothscale(tinted, (new_w, new_h))
        self._render_rect = self._current_surf.get_rect(center=available.center)

    # ------------------------------------------------------------------
    # App framework interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        global _talking_state
        _talking_state = False
        self._is_talking = False
        self._is_blinking = False
        self._next_blink = time.time() + 3.0 + random.random() * 2.0
        self._blink_end = 0.0
        self._mouth_open = True
        self._update_frame()

    def update(self) -> None:
        global _talking_state, _emotion_request
        now = time.time()

        # Emotion change
        if _emotion_request is not None:
            emo = _emotion_request
            _emotion_request = None
            if emo != self._emotion:
                self._load_sprites(emo)

        # Talking state
        new_talking = _talking_state
        if new_talking != self._is_talking:
            self._is_talking = new_talking
            self._mouth_open = True
            self._talk_frame_timer = now

        # Blink logic
        if not self._is_blinking and now >= self._next_blink:
            self._is_blinking = True
            self._blink_end = now + 0.4
        if self._is_blinking and now >= self._blink_end:
            self._is_blinking = False
            self._next_blink = now + 3.0 + random.random() * 2.0

        # Mouth animation during talking
        if self._is_talking and now - self._talk_frame_timer >= self._talk_frame_interval:
            self._mouth_open = random.random() < 0.7
            self._talk_frame_timer = now

        try:
            from modules.module_state import get_tars_state
            self._machine_state = str(get_tars_state().value).upper()
        except Exception:
            pass

        self._update_frame()

    def set_preview_state(self, snapshot) -> None:
        self._machine_state = str(snapshot.machine_state).upper()
        self._battery = snapshot.battery
        self._alert = str(snapshot.alert).upper()
        self._connectivity = str(snapshot.connectivity).upper()

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def render(self) -> None:
        self.screen.fill(CANVAS_BLACK)
        ui_scale = scale_for(self.screen)
        title_h = scaled(28, ui_scale)
        status_h = scaled(25, ui_scale)
        draw_grid(
            self.screen,
            pygame.Rect(0, title_h, self.width, self.height - title_h - status_h),
            step=scaled(32, ui_scale),
        )
        if self._current_surf is not None and self._render_rect is not None:
            self.screen.blit(self._current_surf, self._render_rect)
        else:
            draw_label(
                self.screen, "CHARACTER IMAGE N/A",
                (self.width // 2 - scaled(70, ui_scale), self.height // 2),
                size=scaled(10, ui_scale), color=OFFLINE_GRAY,
            )

        draw_hazard_marks(
            self.screen,
            pygame.Rect(
                scaled(10, ui_scale), title_h + scaled(10, ui_scale),
                scaled(28, ui_scale), scaled(3, ui_scale),
            ),
            segment=scaled(4, ui_scale),
        )
        draw_label(
            self.screen, f"CHARACTER // {self._char_name.upper()}",
            (scaled(44, ui_scale), title_h + scaled(8, ui_scale)),
            size=scaled(8, ui_scale), color=CAUTION_AMBER,
        )

        presentation = resolve_presentation(
            self._machine_state, self._alert, self._connectivity,
        )
        draw_title_bar(
            self.screen, "TARS/95", "IDENTITY // AVATAR", presentation.label,
            height=title_h,
            state_color=presentation.color,
            icon="avatar",
        )

        battery = "N/A" if self._battery is None else f"{int(self._battery):03d}%"
        battery_color = OFFLINE_GRAY if self._battery is None else (
            (240, 68, 54) if self._battery <= 20
            else CAUTION_AMBER if self._battery <= 40
            else READY_GREEN
        )
        link_color = {
            "ONLINE": READY_GREEN,
            "DEGRADED": CAUTION_AMBER,
            "OFFLINE": OFFLINE_GRAY,
        }.get(self._connectivity, OFFLINE_GRAY)
        draw_status_bar(
            self.screen,
            (
                ("HOME", "EYES", CHROME_FACE),
                ("VOICE", "LIVE" if self._is_talking else "IDLE", PHOSPHOR_CYAN if self._is_talking else OFFLINE_GRAY),
                ("EMO", self._emotion.upper(), PAPER_TEXT),
                ("LINK", self._connectivity, link_color),
                ("BAT", battery, battery_color),
            ),
            height=status_h,
        )
        self.output_screen.blit(pygame.transform.rotate(self.screen, 90), (0, 0))

    def cleanup(self) -> None:
        pass
