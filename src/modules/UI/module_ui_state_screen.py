"""Responsive TARS/95 idle, warning, and fault takeover screens."""

from __future__ import annotations

from datetime import datetime

import pygame

from modules.UI.module_ui_state import STATE_PRESENTATIONS, StatePresentation
from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CAUTION_AMBER,
    CHROME_FACE,
    CHROME_HIGHLIGHT,
    CHROME_SHADOW,
    FAULT_RED,
    OFFLINE_GRAY,
    PANEL_LINE,
    PANEL_MUTED,
    PAPER_TEXT,
    PHOSPHOR_CYAN,
    READY_GREEN,
    SCREEN_INK,
    draw_grid,
    draw_hazard_marks,
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


class Tars95StateScreen:
    """Draw system-level states above the active app without touching hardware."""

    MODES = ("idle", "warning", "fault")

    def __init__(self, logical_width: int, logical_height: int) -> None:
        self.logical_width = logical_width
        self.logical_height = logical_height
        self.physical_width = logical_height
        self.physical_height = logical_width
        self.frame = pygame.Surface((self.physical_width, self.physical_height))
        self.visible_mode: str | None = None
        self.systems_target: pygame.Rect | None = None

    def render(
        self,
        logical_surface: pygame.Surface,
        mode: str,
        presentation: StatePresentation | None = None,
        *,
        battery: float | int | None = None,
        connectivity: str = "N/A",
        now: datetime | None = None,
    ) -> None:
        normalized = str(mode).lower()
        if normalized not in self.MODES:
            raise ValueError(f"Unknown state-screen mode: {mode}")

        if presentation is None:
            key = "STANDBY" if normalized == "idle" else normalized.upper()
            presentation = STATE_PRESENTATIONS[key]

        self.visible_mode = normalized
        self.systems_target = None
        self.frame.fill(CANVAS_BLACK)
        scale = scale_for(self.frame)
        title_h = scaled(28, scale)
        status_h = scaled(25, scale)
        content = pygame.Rect(
            0, title_h, self.physical_width,
            self.physical_height - title_h - status_h,
        )
        draw_grid(self.frame, content, step=scaled(32, scale))

        if normalized == "idle":
            self._draw_idle(content, presentation, scale, now or datetime.now())
            section = "IDLE // WATCH"
            icon = "eyes"
        else:
            self._draw_alert(content, presentation, scale, normalized)
            section = "SYSTEM // ALERT"
            icon = "warning"

        draw_title_bar(
            self.frame, "TARS/95", section, presentation.label,
            height=title_h, state_color=presentation.color, icon=icon,
        )
        self._draw_status(status_h, presentation, battery, connectivity, normalized)
        logical_surface.blit(pygame.transform.rotate(self.frame, 90), (0, 0))

    def clear(self) -> None:
        self.visible_mode = None
        self.systems_target = None

    def action_at(self, physical_position: tuple[int, int]) -> str | None:
        if self.visible_mode == "idle":
            return "wake"
        if self.systems_target and self.systems_target.collidepoint(physical_position):
            return "systems"
        return None

    def _draw_idle(
        self,
        content: pygame.Rect,
        presentation: StatePresentation,
        scale: float,
        now: datetime,
    ) -> None:
        pad = scaled(12, scale)
        inset = pygame.Rect(
            content.left + pad, content.top + scaled(10, scale),
            content.width - pad * 2, content.height - scaled(20, scale),
        )
        draw_panel(self.frame, inset, fill=CANVAS_BLACK, line=PANEL_LINE)

        draw_label(
            self.frame, "LOW POWER WATCH // OPTICAL ARRAY ARMED",
            (inset.left + scaled(10, scale), inset.top + scaled(9, scale)),
            size=scaled(7, scale), color=CHROME_FACE,
        )
        draw_label(
            self.frame, "APP 01 / EYES",
            (inset.right - scaled(86, scale), inset.top + scaled(9, scale)),
            size=scaled(7, scale), color=PANEL_MUTED,
        )

        center_y = inset.centery - scaled(20, scale)
        aperture_w = min(scaled(92, scale), max(scaled(54, scale), inset.width // 4))
        aperture_h = scaled(8, scale)
        gap = scaled(28, scale)
        for center_x in (inset.centerx - gap - aperture_w // 2, inset.centerx + gap + aperture_w // 2):
            rect = pygame.Rect(0, 0, aperture_w, aperture_h)
            rect.center = (center_x, center_y)
            pygame.draw.rect(self.frame, PANEL_LINE, rect.inflate(scaled(4, scale), scaled(4, scale)), 1)
            pygame.draw.rect(self.frame, PHOSPHOR_CYAN, rect)
            pygame.draw.rect(
                self.frame, CHROME_HIGHLIGHT,
                (rect.left + scaled(5, scale), rect.top, scaled(2, scale), rect.height),
            )

        time_text = now.strftime("%H:%M")
        time_font = load_font(scaled(30, scale), "pixel")
        time_image = time_font.render(time_text, True, PAPER_TEXT)
        self.frame.blit(
            time_image,
            time_image.get_rect(center=(inset.centerx, center_y + scaled(65, scale))),
        )
        date_text = now.strftime("%A // %Y.%m.%d").upper()
        date_image = load_font(scaled(9, scale), "mono").render(date_text, True, PANEL_MUTED)
        self.frame.blit(
            date_image,
            date_image.get_rect(center=(inset.centerx, center_y + scaled(94, scale))),
        )

        sweep_span = max(1, inset.width - scaled(24, scale))
        sweep_x = inset.left + scaled(12, scale) + int((now.second % 30) / 29 * sweep_span)
        sweep_top = inset.top + scaled(38, scale)
        sweep_bottom = inset.bottom - scaled(50, scale)
        draw_rule(self.frame, (sweep_x, sweep_top), (sweep_x, sweep_bottom), PANEL_LINE)
        draw_lamp(
            self.frame, (sweep_x, sweep_bottom), presentation.color,
            size=scaled(4, scale),
        )

        prompt = "TOUCH ANYWHERE TO WAKE"
        prompt_image = load_font(scaled(9, scale), "pixel").render(prompt, True, CHROME_FACE)
        self.frame.blit(
            prompt_image,
            prompt_image.get_rect(center=(inset.centerx, inset.bottom - scaled(22, scale))),
        )

    def _draw_alert(
        self,
        content: pygame.Rect,
        presentation: StatePresentation,
        scale: float,
        mode: str,
    ) -> None:
        color = FAULT_RED if mode == "fault" else CAUTION_AMBER
        pad = scaled(12, scale)
        draw_hazard_marks(
            self.frame,
            pygame.Rect(pad, content.top + scaled(10, scale), content.width - pad * 2, scaled(5, scale)),
            color=color, segment=scaled(8, scale),
        )

        max_w = content.width - scaled(28, scale)
        max_h = content.height - scaled(42, scale)
        panel_w = min(max_w, scaled(430, scale))
        panel_h = min(max_h, scaled(230, scale))
        panel = pygame.Rect(0, 0, panel_w, panel_h)
        panel.center = content.center
        draw_panel(self.frame, panel, fill=SCREEN_INK, line=color)
        pygame.draw.rect(self.frame, color, panel, scaled(2, scale))

        symbol_center = (panel.left + scaled(39, scale), panel.top + scaled(42, scale))
        if mode == "fault":
            arm = scaled(12, scale)
            pygame.draw.line(
                self.frame, color,
                (symbol_center[0] - arm, symbol_center[1] - arm),
                (symbol_center[0] + arm, symbol_center[1] + arm), scaled(4, scale),
            )
            pygame.draw.line(
                self.frame, color,
                (symbol_center[0] + arm, symbol_center[1] - arm),
                (symbol_center[0] - arm, symbol_center[1] + arm), scaled(4, scale),
            )
        else:
            arm = scaled(15, scale)
            pygame.draw.polygon(
                self.frame,
                color,
                ((symbol_center[0], symbol_center[1] - arm),
                 (symbol_center[0] - arm, symbol_center[1] + arm),
                 (symbol_center[0] + arm, symbol_center[1] + arm)),
                width=scaled(3, scale),
            )
            pygame.draw.line(
                self.frame, color,
                (symbol_center[0], symbol_center[1] - scaled(6, scale)),
                (symbol_center[0], symbol_center[1] + scaled(5, scale)), scaled(2, scale),
            )
            draw_lamp(self.frame, (symbol_center[0], symbol_center[1] + scaled(11, scale)), color)

        heading = "FAULT LOCKOUT" if mode == "fault" else "SYSTEM WARNING"
        draw_label(
            self.frame, heading,
            (panel.left + scaled(70, scale), panel.top + scaled(20, scale)),
            size=scaled(17, scale), color=color, role="pixel",
        )
        draw_label(
            self.frame, presentation.cue,
            (panel.left + scaled(70, scale), panel.top + scaled(48, scale)),
            size=scaled(8, scale), color=PAPER_TEXT,
        )

        divider_y = panel.top + scaled(77, scale)
        draw_rule(
            self.frame,
            (panel.left + scaled(12, scale), divider_y),
            (panel.right - scaled(12, scale), divider_y),
            PANEL_LINE,
        )
        details = (
            ("MOTION OUTPUT", "INHIBITED" if mode == "fault" else "HOLD"),
            ("OPERATOR ACTION", "OPEN SYSTEMS"),
        )
        row_y = divider_y + scaled(14, scale)
        for label, value in details:
            draw_label(
                self.frame, label,
                (panel.left + scaled(18, scale), row_y),
                size=scaled(7, scale), color=PANEL_MUTED,
            )
            value_image = load_font(scaled(8, scale), "mono").render(value, True, PAPER_TEXT)
            self.frame.blit(
                value_image,
                value_image.get_rect(topright=(panel.right - scaled(18, scale), row_y)),
            )
            row_y += scaled(20, scale)

        button_h = scaled(42, scale)
        button = pygame.Rect(
            panel.left + scaled(18, scale), panel.bottom - button_h - scaled(14, scale),
            panel.width - scaled(36, scale), button_h,
        )
        pygame.draw.rect(self.frame, CHROME_FACE, button)
        pygame.draw.rect(self.frame, CHROME_SHADOW, button, scaled(1, scale))
        pygame.draw.rect(self.frame, color, (button.left, button.top, scaled(6, scale), button.height))
        button_text = load_font(scaled(10, scale), "pixel").render("OPEN SYSTEMS MONITOR", True, CHROME_SHADOW)
        self.frame.blit(button_text, button_text.get_rect(center=button.center))
        self.systems_target = button

        draw_hazard_marks(
            self.frame,
            pygame.Rect(pad, content.bottom - scaled(15, scale), content.width - pad * 2, scaled(5, scale)),
            color=color, segment=scaled(8, scale),
        )

    def _draw_status(
        self,
        status_h: int,
        presentation: StatePresentation,
        battery: float | int | None,
        connectivity: str,
        mode: str,
    ) -> None:
        battery_value = "N/A" if battery is None else f"{int(battery):03d}%"
        battery_color = OFFLINE_GRAY if battery is None else (
            FAULT_RED if battery <= 20 else CAUTION_AMBER if battery <= 40 else READY_GREEN
        )
        link = str(connectivity).upper()
        link_color = {
            "ONLINE": READY_GREEN,
            "DEGRADED": CAUTION_AMBER,
            "OFFLINE": OFFLINE_GRAY,
        }.get(link, OFFLINE_GRAY)
        action = "WAKE" if mode == "idle" else "SYSTEMS"
        draw_status_bar(
            self.frame,
            (
                ("HOME", "EYES", CHROME_FACE),
                ("STATE", presentation.label, presentation.color),
                ("ACTION", action, CHROME_HIGHLIGHT),
                ("LINK", link, link_color),
                ("BAT", battery_value, battery_color),
            ),
            height=status_h,
        )
