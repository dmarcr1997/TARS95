"""Shared TARS/95 pygame colors and low-resolution drawing primitives."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Sequence

import pygame

from modules.UI.module_ui_icons import draw_icon
from modules.UI.module_ui_state import STATE_COLORS, STATE_LABELS


# The same compact palette used by the TARS/95 web theme.
CANVAS_BLACK = (5, 7, 8)
SCREEN_INK = (8, 17, 22)
PANEL_LINE = (48, 64, 68)
PANEL_MUTED = (111, 119, 122)
PAPER_TEXT = (232, 227, 209)
CHROME_FACE = (216, 201, 155)
CHROME_HIGHLIGHT = (255, 242, 194)
CHROME_MID = (142, 128, 92)
CHROME_SHADOW = (34, 34, 34)
NAVY = (3, 28, 85)
PHOSPHOR_CYAN = (22, 217, 196)
READY_GREEN = (56, 232, 120)
CAUTION_AMBER = (255, 176, 0)
FAULT_RED = (240, 68, 54)
OFFLINE_GRAY = (111, 119, 122)

_FONT_ROOT = Path(__file__).resolve().parent


def scaled(value: int | float, scale: float) -> int:
    """Scale a design pixel while preserving one-pixel rules."""
    return max(1, int(round(value * scale)))


def scale_for(surface: pygame.Surface) -> float:
    """Return the scale relative to the primary 480x320 physical display."""
    return surface.get_height() / 320.0


@lru_cache(maxsize=32)
def load_font(size: int, role: str = "mono") -> pygame.font.Font:
    """Load an offline repository font with a safe pygame fallback."""
    candidates = (
        ("pixelmix.ttf", "assets/vga.ttf")
        if role == "pixel"
        else ("mono.ttf", "assets/vga.ttf")
    )
    for relative_path in candidates:
        path = _FONT_ROOT / relative_path
        if path.is_file():
            try:
                return pygame.font.Font(str(path), size)
            except pygame.error:
                continue
    return pygame.font.Font(None, size)


def draw_label(
    surface: pygame.Surface,
    text: str,
    position: tuple[int, int],
    *,
    size: int = 10,
    color: tuple[int, int, int] = PAPER_TEXT,
    role: str = "mono",
) -> pygame.Rect:
    label = load_font(size, role).render(text, True, color)
    rect = label.get_rect(topleft=position)
    surface.blit(label, rect)
    return rect


def draw_lamp(
    surface: pygame.Surface,
    center: tuple[int, int],
    color: tuple[int, int, int],
    *,
    size: int = 4,
) -> pygame.Rect:
    """Draw a square indicator lamp without glow or decorative shadow."""
    rect = pygame.Rect(0, 0, size, size)
    rect.center = center
    pygame.draw.rect(surface, CHROME_SHADOW, rect.inflate(2, 2), 1)
    pygame.draw.rect(surface, color, rect)
    return rect


def draw_rule(
    surface: pygame.Surface,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int] = PANEL_LINE,
    *,
    width: int = 1,
) -> None:
    pygame.draw.line(surface, color, start, end, width)


def draw_grid(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    step: int = 32,
    color: tuple[int, int, int] = (10, 28, 30),
) -> None:
    """Draw a quiet instrumentation grid clipped to a rectangular field."""
    previous_clip = surface.get_clip()
    surface.set_clip(rect)
    for x in range(rect.left, rect.right + 1, step):
        draw_rule(surface, (x, rect.top), (x, rect.bottom), color)
    for y in range(rect.top, rect.bottom + 1, step):
        draw_rule(surface, (rect.left, y), (rect.right, y), color)
    surface.set_clip(previous_clip)


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    fill: tuple[int, int, int] = SCREEN_INK,
    line: tuple[int, int, int] = PANEL_LINE,
) -> pygame.Rect:
    """Draw the approved flat instrument panel treatment."""
    pygame.draw.rect(surface, fill, rect)
    pygame.draw.rect(surface, line, rect, 1)
    return rect


def draw_button(
    surface: pygame.Surface,
    rect: pygame.Rect,
    text: str,
    *,
    active: bool = False,
) -> pygame.Rect:
    """Draw a compact physical control using restrained Windows-era chrome."""
    face = CHROME_HIGHLIGHT if active else CHROME_FACE
    pygame.draw.rect(surface, face, rect)
    pygame.draw.rect(surface, CHROME_SHADOW, rect, 1)
    label = load_font(max(8, int(rect.height * 0.42)), "pixel").render(text, True, NAVY)
    surface.blit(label, label.get_rect(center=rect.center))
    return rect


def draw_title_bar(
    surface: pygame.Surface,
    title: str,
    section: str,
    state: str,
    *,
    height: int,
    state_color: tuple[int, int, int] | None = None,
    icon: str | None = None,
) -> pygame.Rect:
    """Draw warm manila structural chrome with a flat machine-state readout."""
    rect = pygame.Rect(0, 0, surface.get_width(), height)
    pygame.draw.rect(surface, CHROME_FACE, rect)
    draw_rule(surface, (0, 0), (rect.right, 0), CHROME_HIGHLIGHT)
    draw_rule(surface, (0, rect.bottom - 1), (rect.right, rect.bottom - 1), CHROME_SHADOW)

    scale = scale_for(surface)
    title_size = scaled(11, scale)
    meta_size = scaled(9, scale)
    pad = scaled(8, scale)
    title_rect = draw_label(
        surface, title, (pad, max(1, (height - title_size) // 2 - 1)),
        size=title_size, color=NAVY, role="pixel",
    )
    divider_x = title_rect.right + scaled(8, scale)
    draw_rule(surface, (divider_x, scaled(5, scale)), (divider_x, height - scaled(5, scale)), CHROME_MID)
    section_x = divider_x + scaled(8, scale)
    if icon:
        icon_size = scaled(16, scale)
        draw_icon(
            surface, icon,
            pygame.Rect(section_x, (height - icon_size) // 2, icon_size, icon_size),
            NAVY,
        )
        section_x += icon_size + scaled(6, scale)
    draw_label(
        surface, section, (section_x, max(1, (height - meta_size) // 2)),
        size=meta_size, color=CHROME_SHADOW,
    )

    normalized_state = state.upper()
    display_state = STATE_LABELS.get(normalized_state, normalized_state)
    lamp_color = state_color or STATE_COLORS.get(normalized_state, OFFLINE_GRAY)
    state_font = load_font(meta_size, "mono")
    state_image = state_font.render(display_state, True, NAVY)
    state_rect = state_image.get_rect(midright=(rect.right - pad, height // 2))
    surface.blit(state_image, state_rect)
    draw_lamp(
        surface,
        (state_rect.left - scaled(9, scale), height // 2),
        lamp_color,
        size=scaled(5, scale),
    )
    return rect


def draw_window(
    surface: pygame.Surface,
    rect: pygame.Rect,
    title: str,
    *,
    title_height: int = 24,
) -> pygame.Rect:
    """Draw a simple reusable window; content remains flat and matte."""
    pygame.draw.rect(surface, CHROME_FACE, rect)
    pygame.draw.rect(surface, CHROME_SHADOW, rect, 1)
    inner = rect.inflate(-2, -2)
    pygame.draw.rect(surface, SCREEN_INK, inner)
    title_rect = pygame.Rect(rect.left + 1, rect.top + 1, rect.width - 2, title_height)
    pygame.draw.rect(surface, CHROME_FACE, title_rect)
    draw_rule(surface, title_rect.bottomleft, title_rect.bottomright, CHROME_SHADOW)
    draw_label(
        surface, title, (title_rect.left + 6, title_rect.top + 5),
        size=max(8, int(title_height * 0.42)), color=NAVY, role="pixel",
    )
    return pygame.Rect(inner.left, title_rect.bottom + 1, inner.width, inner.bottom - title_rect.bottom - 1)


def draw_hazard_marks(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    color: tuple[int, int, int] = CAUTION_AMBER,
    segment: int = 8,
) -> None:
    """Draw a small maintenance marker, not a general decorative border."""
    pygame.draw.rect(surface, CHROME_SHADOW, rect)
    for x in range(rect.left, rect.right, segment * 2):
        pygame.draw.rect(surface, color, (x, rect.top, min(segment, rect.right - x), rect.height))


def draw_status_bar(
    surface: pygame.Surface,
    items: Sequence[tuple[str, str, tuple[int, int, int]]],
    *,
    height: int,
) -> pygame.Rect:
    """Draw a flat telemetry rail with hairline separators instead of boxes."""
    rect = pygame.Rect(0, surface.get_height() - height, surface.get_width(), height)
    pygame.draw.rect(surface, SCREEN_INK, rect)
    draw_rule(surface, rect.topleft, rect.topright, PANEL_LINE)
    if not items:
        return rect

    scale = scale_for(surface)
    cell_width = rect.width / len(items)
    font_size = scaled(8, scale)
    pad = scaled(7, scale)
    for index, (label, value, color) in enumerate(items):
        left = int(round(rect.left + index * cell_width))
        right = int(round(rect.left + (index + 1) * cell_width))
        if index:
            draw_rule(surface, (left, rect.top + 4), (left, rect.bottom - 4), PANEL_LINE)
        draw_lamp(surface, (left + pad, rect.centery), color, size=scaled(4, scale))
        draw_label(
            surface, f"{label} {value}",
            (left + pad + scaled(7, scale), rect.top + max(2, (height - font_size) // 2)),
            size=font_size, color=PAPER_TEXT,
        )
    return rect


def alert_color(alert: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    normalized = alert.upper()
    if normalized == "FAULT":
        return FAULT_RED
    if normalized in {"WARNING", "ADVISORY"}:
        return CAUTION_AMBER
    return fallback
