"""TARS/95 device shell, touch launcher, and physical taskbar routing."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from modules.UI.module_ui_icons import draw_icon
from modules.UI.module_ui_state import StatePresentation
from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CHROME_FACE,
    CHROME_HIGHLIGHT,
    NAVY,
    OFFLINE_GRAY,
    PANEL_LINE,
    PAPER_TEXT,
    SCREEN_INK,
    draw_grid,
    draw_label,
    draw_lamp,
    draw_panel,
    draw_rule,
    draw_status_bar,
    draw_title_bar,
    load_font,
    scale_for,
    scaled,
)


@dataclass(frozen=True)
class ShellApp:
    name: str
    label: str
    description: str
    icon: str


SHELL_APPS = (
    ShellApp("eyes", "EYES", "PRESENCE / HOME", "eyes"),
    ShellApp("clock", "CLOCK", "LOCAL TIME", "clock"),
    ShellApp("audio", "AUDIO", "SIGNAL DIAGNOSTICS", "audio"),
    ShellApp("avatar", "AVATAR", "IDENTITY FRAME", "avatar"),
    ShellApp("remote", "REMOTE", "LINK SERVICE", "remote"),
    ShellApp("terminal", "CONSOLE", "COMMAND CHANNEL", "chat"),
)


class Tars95Shell:
    """Render and route the exact physical shell shared by Pi and preview."""

    def __init__(self, logical_width: int, logical_height: int) -> None:
        self.logical_width = logical_width
        self.logical_height = logical_height
        self.physical_width = logical_height
        self.physical_height = logical_width
        self._frame = pygame.Surface((self.physical_width, self.physical_height))
        self._targets: list[tuple[pygame.Rect, str]] = []

    def logical_to_physical(self, position: tuple[int, int]) -> tuple[int, int]:
        x, y = position
        return self.physical_width - 1 - y, x

    def physical_to_logical(self, position: tuple[int, int]) -> tuple[int, int]:
        x, y = position
        return y, self.physical_width - 1 - x

    def is_taskbar_trigger(self, physical_position: tuple[int, int]) -> bool:
        x, y = physical_position
        status_h = scaled(25, self.physical_height / 320.0)
        return y >= self.physical_height - status_h and x < self.physical_width / 5

    def launcher_action(self, physical_position: tuple[int, int]) -> tuple[str, str | None] | None:
        for rect, app_name in self._targets:
            if rect.collidepoint(physical_position):
                return "launch", app_name

        x, y = physical_position
        status_h = scaled(28, self.physical_height / 320.0)
        if y >= self.physical_height - status_h:
            cell = int(x / (self.physical_width / 4))
            if cell == 0:
                return "launch", "eyes"
            if cell == 3:
                return "close", None
        return None

    @property
    def touch_targets(self) -> tuple[tuple[pygame.Rect, str], ...]:
        return tuple(self._targets)

    def render_launcher(
        self,
        logical_surface: pygame.Surface,
        active_app: str,
        presentation: StatePresentation,
    ) -> None:
        frame = self._frame
        frame.fill(CANVAS_BLACK)
        scale = scale_for(frame)
        title_h = scaled(28, scale)
        status_h = scaled(28, scale)
        content = pygame.Rect(0, title_h, frame.get_width(), frame.get_height() - title_h - status_h)
        draw_grid(frame, content, step=scaled(32, scale))
        draw_title_bar(
            frame, "TARS/95", "APPLICATION DIRECTORY", presentation.label,
            height=title_h, state_color=presentation.color, icon="settings",
        )

        draw_label(
            frame, "SYSTEM MENU // TOUCH TO LAUNCH",
            (scaled(12, scale), title_h + scaled(9, scale)),
            size=scaled(8, scale), color=CHROME_FACE, role="pixel",
        )
        active_text = f"ACTIVE {active_app.upper()}"
        active_image = load_font(scaled(8, scale)).render(active_text, True, presentation.color)
        frame.blit(
            active_image,
            active_image.get_rect(topright=(frame.get_width() - scaled(12, scale), title_h + scaled(9, scale))),
        )

        self._targets = []
        margin = scaled(12, scale)
        gap_x = scaled(10, scale)
        gap_y = scaled(8, scale)
        grid_top = title_h + scaled(29, scale)
        tile_w = (frame.get_width() - margin * 2 - gap_x) // 2
        tile_h = scaled(59, scale)
        for index, app in enumerate(SHELL_APPS):
            column = index % 2
            row = index // 2
            rect = pygame.Rect(
                margin + column * (tile_w + gap_x),
                grid_top + row * (tile_h + gap_y),
                tile_w,
                tile_h,
            )
            self._draw_app_tile(frame, rect, app, app.name == active_app, presentation, scale, index)
            self._targets.append((rect, app.name))

        draw_status_bar(
            frame,
            (
                ("HOME", "EYES", CHROME_FACE),
                ("ACTIVE", active_app.upper(), presentation.color),
                ("STATE", presentation.label, presentation.color),
                ("EXIT", "CLOSE", CHROME_FACE),
            ),
            height=status_h,
        )
        logical_surface.blit(pygame.transform.rotate(frame, 90), (0, 0))

    def _draw_app_tile(
        self,
        frame: pygame.Surface,
        rect: pygame.Rect,
        app: ShellApp,
        active: bool,
        presentation: StatePresentation,
        scale: float,
        index: int,
    ) -> None:
        line = CHROME_FACE if active else PANEL_LINE
        draw_panel(frame, rect, fill=SCREEN_INK, line=line)
        marker_w = scaled(5, scale)
        pygame.draw.rect(frame, presentation.color if active else PANEL_LINE, (rect.left, rect.top, marker_w, rect.height))
        icon_size = scaled(24, scale)
        icon_rect = pygame.Rect(
            rect.left + scaled(16, scale),
            rect.centery - icon_size // 2,
            icon_size,
            icon_size,
        )
        draw_icon(frame, app.icon, icon_rect, presentation.color if active else CHROME_FACE)
        text_x = icon_rect.right + scaled(14, scale)
        draw_label(
            frame, app.label, (text_x, rect.top + scaled(12, scale)),
            size=scaled(11, scale), color=CHROME_HIGHLIGHT if active else PAPER_TEXT, role="pixel",
        )
        draw_label(
            frame, app.description, (text_x, rect.top + scaled(34, scale)),
            size=scaled(7, scale), color=OFFLINE_GRAY,
        )
        draw_label(
            frame, f"{index + 1:02d}",
            (rect.right - scaled(21, scale), rect.top + scaled(7, scale)),
            size=scaled(7, scale), color=NAVY if active else PANEL_LINE,
        )
        draw_lamp(
            frame,
            (rect.right - scaled(9, scale), rect.bottom - scaled(9, scale)),
            presentation.color if active else PANEL_LINE,
            size=scaled(4, scale),
        )
