"""Physical-first TARS/95 renderer for the existing command-console model."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from modules.UI.module_ui_state import resolve_presentation
from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CAUTION_AMBER,
    CHROME_FACE,
    CHROME_HIGHLIGHT,
    FAULT_RED,
    NAVY,
    OFFLINE_GRAY,
    PANEL_LINE,
    PAPER_TEXT,
    PHOSPHOR_CYAN,
    READY_GREEN,
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

if TYPE_CHECKING:
    from modules.UI.module_ui_terminal import TerminalSystem


class Tars95TerminalRenderer:
    """Draw the console in physical landscape and route its touch controls."""

    def __init__(self, owner: "TerminalSystem", logical_width: int, logical_height: int) -> None:
        self.owner = owner
        self.logical_width = logical_width
        self.logical_height = logical_height
        self.physical_width = logical_height
        self.physical_height = logical_width
        self.frame = pygame.Surface((self.physical_width, self.physical_height))
        self.scroll_up_rect: pygame.Rect | None = None
        self.scroll_down_rect: pygame.Rect | None = None
        self.menu_targets: list[tuple[pygame.Rect, str]] = []
        self.app_targets: list[tuple[pygame.Rect, str]] = []
        self.power_targets: list[tuple[pygame.Rect, str]] = []

    def logical_to_physical(self, position: tuple[int, int]) -> tuple[int, int]:
        x, y = position
        return self.physical_width - 1 - y, x

    def draw(self, logical_surface: pygame.Surface) -> None:
        frame = self.frame
        frame.fill(CANVAS_BLACK)
        scale = scale_for(frame)
        title_h = scaled(28, scale)
        status_h = scaled(25, scale)
        content = pygame.Rect(0, title_h, frame.get_width(), frame.get_height() - title_h - status_h)
        draw_grid(frame, content, step=scaled(32, scale))

        machine_state = "THINKING" if self.owner.thinking else self.owner.tars_status
        presentation = resolve_presentation(
            machine_state, self.owner._alert, self.owner._connectivity,
        )
        draw_title_bar(
            frame, "TARS/95", "COMMAND // CONSOLE", presentation.label,
            height=title_h, state_color=presentation.color, icon="chat",
        )
        self._draw_channel_header(frame, content, presentation, scale)
        self._draw_messages(frame, content, scale)
        self._draw_scroll_rail(frame, content, scale)

        link_value, link_color = self._link_readout()
        draw_status_bar(
            frame,
            (
                ("MENU", "OPEN", CHROME_FACE),
                ("STATE", presentation.label, presentation.color),
                ("LINK", link_value, link_color),
                ("MSG", f"{len(self.owner.messages):03d}", PAPER_TEXT),
                ("PWR", "SAFE", CAUTION_AMBER),
            ),
            height=status_h,
        )

        if self.owner.show_main_menu:
            self._draw_main_menu(frame, presentation, scale)
        elif self.owner.show_app_menu:
            self._draw_app_menu(frame, presentation, scale)
        elif self.owner.show_power_menu:
            self._draw_power_menu(frame, scale)

        self._draw_toast(frame, scale)
        logical_surface.blit(pygame.transform.rotate(frame, 90), (0, 0))

    def handle_click(self, logical_position: tuple[int, int]) -> bool:
        position = self.logical_to_physical(logical_position)
        owner = self.owner

        if owner.show_main_menu:
            for rect, action in self.menu_targets:
                if rect.collidepoint(position):
                    self._run_menu_action(action)
                    return True
            owner.show_main_menu = False
            return True

        if owner.show_app_menu:
            for rect, app_name in self.app_targets:
                if rect.collidepoint(position):
                    if owner.on_app_select:
                        owner.on_app_select(app_name)
                    owner.show_app_menu = False
                    return True
            owner.show_app_menu = False
            return True

        if owner.show_power_menu:
            for rect, action in self.power_targets:
                if rect.collidepoint(position):
                    if action == "exit" and owner.on_exit:
                        owner.on_exit()
                    elif action == "shutdown" and owner.on_shutdown:
                        owner.on_shutdown()
                    owner.show_power_menu = False
                    return True
            owner.show_power_menu = False
            return True

        if self.scroll_up_rect and self.scroll_up_rect.collidepoint(position):
            owner.scroll_up(1)
            return True
        if self.scroll_down_rect and self.scroll_down_rect.collidepoint(position):
            owner.scroll_down(1)
            return True

        status_h = scaled(25, scale_for(self.frame))
        if position[1] >= self.physical_height - status_h:
            cell = int(position[0] / (self.physical_width / 5))
            if cell == 0:
                owner.show_main_menu = True
            elif cell == 4:
                owner.show_power_menu = True
            return True
        return True

    def _draw_channel_header(self, frame, content, presentation, scale: float) -> None:
        y = content.top + scaled(8, scale)
        draw_label(frame, "TERM-A1", (scaled(11, scale), y), size=scaled(9, scale), color=CHROME_FACE, role="pixel")
        draw_label(
            frame, "LOCAL COMMAND CHANNEL",
            (scaled(76, scale), y + scaled(1, scale)),
            size=scaled(8, scale), color=OFFLINE_GRAY,
        )
        scroll_label = "SCROLL HOLD" if self.owner.scroll_offset else "SCROLL AUTO"
        scroll_image = load_font(scaled(8, scale)).render(scroll_label, True, PAPER_TEXT)
        frame.blit(scroll_image, scroll_image.get_rect(topright=(frame.get_width() - scaled(12, scale), y)))
        rule_y = y + scaled(16, scale)
        draw_rule(frame, (scaled(10, scale), rule_y), (frame.get_width() - scaled(10, scale), rule_y), PANEL_LINE)
        if self.owner.thinking:
            phase = (pygame.time.get_ticks() // 120) % 8
            segment_w = scaled(8, scale)
            for index in range(8):
                color = presentation.color if index <= phase else PANEL_LINE
                pygame.draw.rect(
                    frame, color,
                    (scaled(11, scale) + index * (segment_w + scaled(2, scale)), rule_y + scaled(3, scale), segment_w, scaled(3, scale)),
                )

    def _draw_messages(self, frame, content, scale: float) -> None:
        x = scaled(10, scale)
        y = content.top + scaled(33, scale)
        right = frame.get_width() - scaled(49, scale)
        bottom = content.bottom - scaled(6, scale)
        width = right - x
        font = load_font(scaled(9, scale))
        meta_font = load_font(scaled(7, scale), "pixel")
        line_h = scaled(12, scale)
        gap = scaled(5, scale)
        offset = max(0, self.owner.scroll_offset)
        messages = list(reversed(self.owner.messages))[offset:]

        if not messages:
            draw_label(frame, "NO MESSAGES // CHANNEL READY", (x + scaled(8, scale), y + scaled(12, scale)), size=scaled(9, scale), color=OFFLINE_GRAY)
            return

        for index, (key, value, msg_type, _timestamp) in enumerate(messages):
            category, signal = self._message_style(key, msg_type)
            lines = self._wrap(str(value), font, width - scaled(20, scale))
            height = scaled(18, scale) + len(lines) * line_h
            if y + height > bottom:
                break
            rect = pygame.Rect(x, y, width, height)
            draw_panel(frame, rect, fill=SCREEN_INK, line=PANEL_LINE)
            pygame.draw.rect(frame, signal, (rect.left, rect.top, scaled(4, scale), rect.height))
            frame.blit(meta_font.render(category, True, signal), (rect.left + scaled(10, scale), rect.top + scaled(5, scale)))
            line_y = rect.top + scaled(17, scale)
            for line in lines:
                frame.blit(font.render(line, True, PAPER_TEXT), (rect.left + scaled(10, scale), line_y))
                line_y += line_h
            y = rect.bottom + gap

    def _draw_scroll_rail(self, frame, content, scale: float) -> None:
        rail_x = frame.get_width() - scaled(41, scale)
        rail_top = content.top + scaled(31, scale)
        rail_bottom = content.bottom - scaled(6, scale)
        button_h = scaled(48, scale)
        self.scroll_up_rect = pygame.Rect(rail_x, rail_top, scaled(31, scale), button_h)
        self.scroll_down_rect = pygame.Rect(rail_x, rail_bottom - button_h, scaled(31, scale), button_h)
        for rect, direction in ((self.scroll_up_rect, "up"), (self.scroll_down_rect, "down")):
            draw_panel(frame, rect, fill=SCREEN_INK, line=PANEL_LINE)
            cx, cy = rect.center
            amount = scaled(6, scale)
            points = (
                [(cx, cy - amount), (cx - amount, cy + amount), (cx + amount, cy + amount)]
                if direction == "up"
                else [(cx, cy + amount), (cx - amount, cy - amount), (cx + amount, cy - amount)]
            )
            pygame.draw.polygon(frame, CHROME_FACE, points)
        draw_label(
            frame, f"{self.owner.scroll_offset:02d}",
            (rail_x + scaled(8, scale), rail_top + button_h + scaled(12, scale)),
            size=scaled(8, scale), color=OFFLINE_GRAY,
        )

    def _draw_main_menu(self, frame, presentation, scale: float) -> None:
        items = (
            ("APPS", "apps"), ("CAMERA", "camera"),
            ("DISPLAY", "display"), ("WAVEFORM", "wave"),
            ("CLEAR LOG", "clear"), ("CLOSE", "close"),
        )
        self.menu_targets = self._draw_modal_grid(
            frame, "CONSOLE CONTROL", items, presentation.color, scale,
        )

    def _draw_app_menu(self, frame, presentation, scale: float) -> None:
        items = tuple((app["label"].upper(), app["name"]) for app in self.owner.app_list)
        self.app_targets = self._draw_modal_grid(
            frame, "APPLICATION DIRECTORY", items, presentation.color, scale,
        )

    def _draw_power_menu(self, frame, scale: float) -> None:
        panel = pygame.Rect(scaled(70, scale), scaled(81, scale), frame.get_width() - scaled(140, scale), scaled(158, scale))
        draw_panel(frame, panel, fill=SCREEN_INK, line=FAULT_RED)
        pygame.draw.rect(frame, CHROME_FACE, (panel.left, panel.top, panel.width, scaled(27, scale)))
        draw_label(frame, "POWER CONTROL", (panel.left + scaled(10, scale), panel.top + scaled(7, scale)), size=scaled(10, scale), color=NAVY, role="pixel")
        draw_label(frame, "CONFIRM A DELIBERATE MACHINE ACTION", (panel.left + scaled(14, scale), panel.top + scaled(43, scale)), size=scaled(8, scale), color=OFFLINE_GRAY)
        button_y = panel.top + scaled(76, scale)
        button_w = (panel.width - scaled(42, scale)) // 2
        self.power_targets = []
        for index, (label, action) in enumerate((("EXIT PROGRAM", "exit"), ("SHUTDOWN", "shutdown"))):
            rect = pygame.Rect(panel.left + scaled(14, scale) + index * (button_w + scaled(14, scale)), button_y, button_w, scaled(51, scale))
            draw_panel(frame, rect, fill=SCREEN_INK, line=FAULT_RED)
            draw_label(frame, label, (rect.left + scaled(10, scale), rect.top + scaled(17, scale)), size=scaled(9, scale), color=FAULT_RED, role="pixel")
            self.power_targets.append((rect, action))

    def _draw_modal_grid(self, frame, title: str, items, signal, scale: float):
        panel = pygame.Rect(scaled(38, scale), scaled(42, scale), frame.get_width() - scaled(76, scale), scaled(236, scale))
        draw_panel(frame, panel, fill=CANVAS_BLACK, line=CHROME_FACE)
        pygame.draw.rect(frame, CHROME_FACE, (panel.left, panel.top, panel.width, scaled(27, scale)))
        draw_label(frame, title, (panel.left + scaled(10, scale), panel.top + scaled(7, scale)), size=scaled(10, scale), color=NAVY, role="pixel")
        targets = []
        gap = scaled(9, scale)
        margin = scaled(12, scale)
        top = panel.top + scaled(39, scale)
        tile_w = (panel.width - margin * 2 - gap) // 2
        tile_h = scaled(50, scale)
        for index, (label, action) in enumerate(items[:6]):
            row, column = divmod(index, 2)
            rect = pygame.Rect(panel.left + margin + column * (tile_w + gap), top + row * (tile_h + gap), tile_w, tile_h)
            draw_panel(frame, rect, fill=SCREEN_INK, line=PANEL_LINE)
            pygame.draw.rect(frame, signal, (rect.left, rect.top, scaled(4, scale), rect.height))
            draw_label(frame, label, (rect.left + scaled(13, scale), rect.top + scaled(17, scale)), size=scaled(9, scale), color=PAPER_TEXT, role="pixel")
            draw_lamp(frame, (rect.right - scaled(10, scale), rect.centery), signal, size=scaled(4, scale))
            targets.append((rect, action))
        return targets

    def _run_menu_action(self, action: str) -> None:
        owner = self.owner
        if action == "apps":
            owner.show_main_menu = False
            owner.show_app_menu = True
        elif action == "camera" and owner.on_camera_toggle:
            owner.on_camera_toggle()
            owner.show_main_menu = False
        elif action == "display" and owner.on_background_change:
            self._toast(owner.on_background_change())
        elif action == "wave" and owner.on_spectrum_change:
            self._toast(owner.on_spectrum_change())
        elif action == "clear":
            owner.clear_messages()
            owner.show_main_menu = False
        elif action == "close":
            owner.show_main_menu = False

    def _toast(self, value) -> None:
        if value:
            self.owner._toast_text = str(value)
            self.owner._toast_time = pygame.time.get_ticks() / 1000.0

    def _draw_toast(self, frame, scale: float) -> None:
        if not self.owner._toast_text:
            return
        elapsed = pygame.time.get_ticks() / 1000.0 - self.owner._toast_time
        if elapsed >= self.owner._toast_duration:
            self.owner._toast_text = None
            return
        text = str(self.owner._toast_text).upper()
        font = load_font(scaled(8, scale))
        image = font.render(text, True, NAVY)
        rect = image.get_rect(midtop=(frame.get_width() // 2, scaled(31, scale))).inflate(scaled(16, scale), scaled(8, scale))
        pygame.draw.rect(frame, CHROME_HIGHLIGHT, rect)
        pygame.draw.rect(frame, NAVY, rect, 1)
        frame.blit(image, image.get_rect(center=rect.center))

    def _link_readout(self) -> tuple[str, tuple[int, int, int]]:
        if not self.owner._wifi_initialized:
            return "N/A", OFFLINE_GRAY
        if self.owner._wifi_mode == "client":
            return "ONLINE", READY_GREEN
        if self.owner._wifi_mode == "hotspot":
            return "HOTSPOT", CAUTION_AMBER
        return "OFFLINE", OFFLINE_GRAY

    def _message_style(self, key: str, msg_type: str) -> tuple[str, tuple[int, int, int]]:
        upper_key = str(key).upper()
        upper_type = str(msg_type).upper()
        if upper_type == "ERROR":
            return "FAULT // SYSTEM", FAULT_RED
        if upper_type == "WARNING":
            return "WARNING // SYSTEM", CAUTION_AMBER
        if upper_key in {"SYSTEM", "SYS", "INFO", "DEBUG", "DEBUG VOICE"}:
            return f"{upper_key} // LOG", OFFLINE_GRAY
        if upper_key == self.owner.character_name.upper():
            return f"{upper_key} // TARS", PHOSPHOR_CYAN
        return f"{upper_key} // OPERATOR", CHROME_FACE

    @staticmethod
    def _wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current: list[str] = []
        for word in words:
            candidate = " ".join((*current, word))
            if current and font.size(candidate)[0] > width:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        return lines or [""]
