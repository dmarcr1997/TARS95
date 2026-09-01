"""
Module: Eyes App
Author: Latisha Besariani Hendra
Description: Pygame app that renders RoboEyes.
             Follows the TARS-AI app framework (init/reset/update/render/cleanup).
"""

import time
import random
import asyncio
import threading
import pygame

from modules.module_eyes import RoboEyes, Mood
from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CAUTION_AMBER,
    OFFLINE_GRAY,
    PANEL_LINE,
    PHOSPHOR_CYAN,
    READY_GREEN,
    STATE_COLORS,
    alert_color,
    draw_grid,
    draw_hazard_marks,
    draw_label,
    draw_rule,
    draw_status_bar,
    draw_title_bar,
    scale_for,
    scaled,
)

_mood_request = None

def set_mood_request(mood):
    global _mood_request
    _mood_request = mood

# Voice lines for touch reactions
TOUCH_VOICE_LINES = {
    'poke_left': [
        "Ouch!", "Hey!", "Ow, my eye!", "Watch it!", "That's my eye!",
        "Do you mind?", "Ow!", "Not cool!", "Easy there!",
    ],
    'poke_right': [
        "Ouch!", "Hey!", "Ow, my eye!", "Watch it!", "That's my eye!",
        "Do you mind?", "Ow!", "Not cool!", "Easy there!",
    ],
    'boop_nose': [
        "Boop!", "Hehe, stop it!", "That tickles!", "Boop right back at ya!",
        "My nose!", "Okay that was cute.", "Again? Really?",
    ],
    'forehead_tap': [
        "Hey, I'm thinking up here.", "Quit it.", "Stop poking my head.",
        "Yes, there's a brain in here.", "Knock knock, nobody's home.",
        "Do you mind? I was thinking.",
    ],
    'chin_tap': [
        "Whoa!", "Hey, watch the chin!", "Hmm?", "What's down there?",
        "That startled me!", "Oh!",
    ],
    'poke_face': [
        "Hey!", "Stop that.", "Excuse me.", "Personal space, please.",
        "I felt that.", "Blink.",
    ],
    'dizzy': [
        "Whoa, the room is spinning!", "I'm seeing stars!",
        "Make it stop!", "Everything's going in circles!",
        "I think I need to sit down.", "Too many pokes!",
        "The world won't stay still!",
    ],
}


def _speak_in_background(text):
    """Fire TTS in a background thread without blocking the render loop."""
    def _run():
        try:
            from modules.module_config import load_config
            from modules.module_tts import play_audio_chunks
            config = load_config()
            asyncio.run(play_audio_chunks(text, config['TTS']['ttsoption']))
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


class EyesApp:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        # The production app manager exposes a portrait logical surface and
        # rotates it onto the physical landscape display. Author this app in
        # physical orientation so the eyes remain side-by-side after rotation.
        self.physical_width = height
        self.physical_height = width
        self._physical_frame = pygame.Surface((self.physical_width, self.physical_height))
        self.eyes = RoboEyes(self.physical_width, self.physical_height)
        self.eyes.config.bg_color = CANVAS_BLACK
        self.eyes.set_mood(Mood.NEUTRAL)

        self._machine_state = "STANDBY"
        self._battery = None
        self._alert = "NONE"
        self._connectivity = "N/A"

        self._prev_time = time.time()
        self._last_mouse_move_time = time.time()
        self._cursor_hidden = False

    def reset(self):
        self.eyes.set_mood(Mood.NEUTRAL)
        self._prev_time = time.time()

    def update(self):
        now = time.time()
        dt = now - self._prev_time
        self._prev_time = now

        global _mood_request
        if _mood_request is not None:
            self.eyes.set_mood(_mood_request)
            _mood_request = None

        if not self._cursor_hidden and (now - self._last_mouse_move_time) >= 2.0:
            pygame.mouse.set_visible(False)
            self._cursor_hidden = True

        try:
            from modules.module_state import get_tars_state
            self._machine_state = str(get_tars_state().value).upper()
        except Exception:
            pass

        self.eyes.update(dt)

    def set_preview_state(self, snapshot):
        """Accept desktop-only fixture values without importing preview code."""
        self._machine_state = str(snapshot.machine_state).upper()
        self._battery = snapshot.battery
        self._alert = str(snapshot.alert).upper()
        self._connectivity = str(snapshot.connectivity).upper()

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._last_mouse_move_time = time.time()
            if self._cursor_hidden:
                pygame.mouse.set_visible(True)
                self._cursor_hidden = False
        if event.type == pygame.MOUSEBUTTONDOWN:
            x, y = event.pos
            # Map portrait logical input back to the authored physical frame.
            physical_x = self.physical_width - 1 - y
            physical_y = x
            chrome_height = scaled(28, self.physical_height / 320.0)
            status_height = scaled(25, self.physical_height / 320.0)
            if physical_y < chrome_height or physical_y >= self.physical_height - status_height:
                return False
            reaction = self.eyes.handle_touch(physical_x, physical_y)
            if reaction and reaction in TOUCH_VOICE_LINES:
                line = random.choice(TOUCH_VOICE_LINES[reaction])
                _speak_in_background(line)
            return reaction is not None
        return False

    def render(self):
        frame = self._physical_frame
        frame.fill(CANVAS_BLACK)
        scale = scale_for(frame)
        title_height = scaled(28, scale)
        status_height = scaled(25, scale)
        content_rect = pygame.Rect(
            0, title_height, frame.get_width(), frame.get_height() - title_height - status_height,
        )
        draw_grid(frame, content_rect, step=scaled(32, scale))

        # Eyes are the content, not decoration: keep the central field open.
        self.eyes.draw(frame)

        machine_color = STATE_COLORS.get(self._machine_state, OFFLINE_GRAY)
        draw_title_bar(
            frame,
            "TARS/95",
            "EYES // HOME",
            self._machine_state,
            height=title_height,
            state_color=alert_color(self._alert, machine_color),
        )

        index_y = title_height + scaled(10, scale)
        draw_hazard_marks(
            frame,
            pygame.Rect(scaled(10, scale), index_y, scaled(28, scale), scaled(3, scale)),
            segment=scaled(4, scale),
        )
        draw_label(
            frame, "OPTICAL EXPRESSION ARRAY",
            (scaled(44, scale), index_y - scaled(2, scale)),
            size=scaled(8, scale), color=CAUTION_AMBER,
        )
        draw_rule(
            frame,
            (scaled(10, scale), frame.get_height() - status_height - scaled(10, scale)),
            (scaled(46, scale), frame.get_height() - status_height - scaled(10, scale)),
            PANEL_LINE,
        )

        battery = "N/A" if self._battery is None else f"{int(self._battery):03d}%"
        battery_color = OFFLINE_GRAY
        if self._battery is not None:
            battery_color = (
                (240, 68, 54) if self._battery <= 20
                else CAUTION_AMBER if self._battery <= 40
                else READY_GREEN
            )
        link_color = {
            "ONLINE": READY_GREEN,
            "DEGRADED": CAUTION_AMBER,
            "OFFLINE": OFFLINE_GRAY,
        }.get(self._connectivity, OFFLINE_GRAY)
        mic_value = "LIVE" if self._machine_state == "LISTENING" else "N/A"
        draw_status_bar(
            frame,
            (
                ("MIC", mic_value, PHOSPHOR_CYAN if mic_value == "LIVE" else OFFLINE_GRAY),
                ("VIS", "N/A", OFFLINE_GRAY),
                ("LINK", self._connectivity, link_color),
                ("BAT", battery, battery_color),
            ),
            height=status_height,
        )

        self.screen.blit(pygame.transform.rotate(frame, 90), (0, 0))

    def cleanup(self):
        if self._cursor_hidden:
            pygame.mouse.set_visible(True)
            self._cursor_hidden = False
