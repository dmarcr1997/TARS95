"""
Analog Clock App demo
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.

See below on how to use this framework to create more apps
"""

import pygame
import math
from datetime import datetime

from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CAUTION_AMBER,
    CHROME_FACE,
    OFFLINE_GRAY,
    PANEL_LINE,
    PANEL_MUTED,
    PAPER_TEXT,
    PHOSPHOR_CYAN,
    READY_GREEN,
    draw_grid,
    draw_label,
    draw_rule,
    draw_status_bar,
    draw_title_bar,
    load_font,
    scale_for,
    scaled,
)
from modules.UI.module_ui_state import resolve_presentation


class ClockApp:
    def __init__(self, screen, width, height):
        self.output_screen = screen
        self.logical_width = width
        self.logical_height = height
        self.width = height
        self.height = width
        self.screen = pygame.Surface((self.width, self.height))

        self._machine_state = "STANDBY"
        self._battery = None
        self._alert = "NONE"
        self._connectivity = "N/A"

    def reset(self):
        pass

    def update(self):
        try:
            from modules.module_state import get_tars_state
            self._machine_state = str(get_tars_state().value).upper()
        except Exception:
            pass

    def set_preview_state(self, snapshot):
        self._machine_state = str(snapshot.machine_state).upper()
        self._battery = snapshot.battery
        self._alert = str(snapshot.alert).upper()
        self._connectivity = str(snapshot.connectivity).upper()

    def render(self):
        self.screen.fill(CANVAS_BLACK)
        scale = scale_for(self.screen)
        title_height = scaled(28, scale)
        status_height = scaled(25, scale)
        content = pygame.Rect(0, title_height, self.width, self.height - title_height - status_height)
        draw_grid(self.screen, content, step=scaled(32, scale))
        now = datetime.now()

        self._draw_analog_clock(now, scale, content)
        self._draw_readout(now, scale, content)

        presentation = resolve_presentation(
            self._machine_state, self._alert, self._connectivity,
        )
        draw_title_bar(
            self.screen, "TARS/95", "CHRONOMETER // LOCAL", presentation.label,
            height=title_height,
            state_color=presentation.color,
            icon="clock",
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
                ("SRC", "LOCAL", PHOSPHOR_CYAN),
                ("ZONE", now.strftime("%Z") or "LOCAL", PAPER_TEXT),
                ("LINK", self._connectivity, link_color),
                ("BAT", battery, battery_color),
            ),
            height=status_height,
        )
        self.output_screen.blit(pygame.transform.rotate(self.screen, 90), (0, 0))

    def _draw_analog_clock(self, now, scale, content):
        cx = scaled(132, scale)
        cy = content.centery
        r = scaled(88, scale)

        pygame.draw.circle(self.screen, PANEL_LINE, (cx, cy), r, scaled(2, scale))
        pygame.draw.circle(self.screen, PANEL_LINE, (cx, cy), r - scaled(5, scale), 1)

        for i in range(60):
            angle = math.radians(i * 6 - 90)
            if i % 5 == 0:
                inner = r - scaled(17, scale)
                outer = r - scaled(6, scale)
                color = CHROME_FACE
                width = scaled(2, scale)
            else:
                inner = r - scaled(11, scale)
                outer = r - scaled(6, scale)
                color = PANEL_LINE
                width = 1

            x1 = cx + int(inner * math.cos(angle))
            y1 = cy + int(inner * math.sin(angle))
            x2 = cx + int(outer * math.cos(angle))
            y2 = cy + int(outer * math.sin(angle))
            pygame.draw.line(self.screen, color, (x1, y1), (x2, y2), width)

        hour = now.hour % 12
        minute = now.minute
        second = now.second
        microsecond = now.microsecond

        smooth_second = second + microsecond / 1_000_000.0
        smooth_minute = minute + smooth_second / 60.0
        smooth_hour = hour + smooth_minute / 60.0

        hour_angle = math.radians(smooth_hour * 30 - 90)
        hour_len = r * 0.5
        hx = cx + int(hour_len * math.cos(hour_angle))
        hy = cy + int(hour_len * math.sin(hour_angle))
        pygame.draw.line(self.screen, PAPER_TEXT, (cx, cy), (hx, hy), scaled(4, scale))

        min_angle = math.radians(smooth_minute * 6 - 90)
        min_len = r * 0.7
        mx = cx + int(min_len * math.cos(min_angle))
        my = cy + int(min_len * math.sin(min_angle))
        pygame.draw.line(self.screen, PHOSPHOR_CYAN, (cx, cy), (mx, my), scaled(3, scale))

        sec_angle = math.radians(smooth_second * 6 - 90)
        sec_len = r * 0.8
        sx = cx + int(sec_len * math.cos(sec_angle))
        sy = cy + int(sec_len * math.sin(sec_angle))
        pygame.draw.line(self.screen, CAUTION_AMBER, (cx, cy), (sx, sy), scaled(2, scale))

        tail_len = r * 0.15
        tx = cx - int(tail_len * math.cos(sec_angle))
        ty = cy - int(tail_len * math.sin(sec_angle))
        pygame.draw.line(self.screen, CAUTION_AMBER, (cx, cy), (tx, ty), 1)

        pygame.draw.circle(self.screen, PHOSPHOR_CYAN, (cx, cy), scaled(5, scale))
        pygame.draw.circle(self.screen, CAUTION_AMBER, (cx, cy), scaled(2, scale))

    def _draw_readout(self, now, scale, content):
        left = scaled(260, scale)
        draw_label(
            self.screen, "LOCAL SYSTEM TIME", (left, content.top + scaled(34, scale)),
            size=scaled(9, scale), color=CAUTION_AMBER,
        )
        draw_rule(
            self.screen,
            (left, content.top + scaled(53, scale)),
            (self.width - scaled(18, scale), content.top + scaled(53, scale)),
            PANEL_LINE,
        )
        time_str = now.strftime("%H:%M:%S")
        time_font = load_font(scaled(38, scale), "mono")
        time_surf = time_font.render(time_str, True, PHOSPHOR_CYAN)
        self.screen.blit(time_surf, (left, content.top + scaled(72, scale)))

        draw_label(
            self.screen, now.strftime("%A").upper(),
            (left, content.top + scaled(132, scale)),
            size=scaled(16, scale), color=PAPER_TEXT, role="pixel",
        )
        draw_label(
            self.screen, now.strftime("%Y.%m.%d"),
            (left, content.top + scaled(166, scale)),
            size=scaled(13, scale), color=PANEL_MUTED,
        )
        draw_label(
            self.screen, f"DAY {now.strftime('%j')} // CYCLE {now.isocalendar().week:02d}",
            (left, content.top + scaled(198, scale)),
            size=scaled(8, scale), color=CAUTION_AMBER,
        )

    def cleanup(self):
        pass


# =============================================================================
# HOW TO CREATE A NEW TARS APP
# =============================================================================
#
# 1. Create a new file in this folder (src/modules/UI/apps/), e.g.:
#       module_app_weather.py
#
# 2. Write a class with these 5 methods:
#
#       import pygame
#
#       class WeatherApp:
#           def __init__(self, screen, width, height):
#               self.screen = screen       # pygame Surface to draw on
#               self.width = width         # display width in pixels
#               self.height = height       # display height in pixels
#
#           def reset(self):
#               pass  # called when the app is launched/relaunched
#
#           def update(self):
#               pass  # called every frame BEFORE render (update logic here)
#
#           def render(self):
#               self.screen.fill((5, 15, 20))  # clear and draw your UI
#
#           def cleanup(self):
#               pass  # called when the app is closed (free resources)
#
# 3. Register it in module_ui_apps.py:
#
#       from modules.UI.apps.module_app_weather import WeatherApp
#
#       AVAILABLE_APPS = {
#           "clock":   {"class": ClockApp,   "type": "pygame", "label": "Clock"},
#           "weather": {"class": WeatherApp, "type": "pygame", "label": "Weather"},
#       }
#
# NOTES:
#   - "type" should be "pygame" for standard 2D apps, "opengl" only for raw GL
#   - "label" is the display name shown in the app launcher UI
#   - Draw directly to self.screen using pygame (pygame.draw, surface.blit, etc.)
#   - Load fonts with: pygame.font.Font("UI/mono.ttf", 24)
#     Always add a fallback: pygame.font.SysFont("monospace", 24)
#   - The AppManager calls update() then render() every frame automatically
#   - Apps are display-only, they do not receive input events
# =============================================================================
