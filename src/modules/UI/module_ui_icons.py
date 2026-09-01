"""Original 16-unit TARS/95 pixel icons for pygame interfaces."""

from __future__ import annotations

from typing import Final

import pygame


GRID_SIZE: Final = 16

# Rectangles are x, y, width, height on a 16x16 integer grid. The designs are
# intentionally mechanical and asymmetric; they are not traced platform icons.
ICON_RECTS: Final[dict[str, tuple[tuple[int, int, int, int], ...]]] = {
    "eyes": (
        (1, 4, 5, 7), (10, 4, 5, 7),
        (2, 3, 3, 1), (11, 3, 3, 1), (2, 12, 3, 1), (11, 12, 3, 1),
    ),
    "clock": (
        (5, 1, 6, 1), (3, 2, 2, 1), (11, 2, 2, 1),
        (2, 3, 1, 2), (13, 3, 1, 2), (1, 5, 1, 6), (14, 5, 1, 6),
        (2, 11, 1, 2), (13, 11, 1, 2), (3, 13, 2, 1), (11, 13, 2, 1),
        (5, 14, 6, 1), (7, 4, 2, 5), (8, 8, 4, 2),
    ),
    "avatar": (
        (3, 2, 10, 1), (2, 3, 1, 9), (13, 3, 1, 9), (3, 12, 10, 1),
        (4, 5, 3, 3), (9, 5, 3, 3), (6, 10, 4, 1), (7, 13, 2, 2),
    ),
    "remote": (
        (2, 7, 12, 1), (2, 8, 1, 6), (13, 8, 1, 6), (3, 13, 10, 1),
        (5, 10, 6, 1), (7, 11, 2, 1), (7, 4, 2, 3),
        (4, 4, 1, 1), (11, 4, 1, 1), (2, 2, 1, 1), (13, 2, 1, 1),
    ),
    "audio": (
        (1, 7, 2, 3), (4, 4, 2, 9), (7, 1, 2, 15),
        (10, 3, 2, 11), (13, 6, 2, 5),
    ),
    "chat": (
        (2, 2, 12, 2), (2, 4, 2, 7), (12, 4, 2, 7), (4, 10, 8, 2),
        (4, 12, 2, 2), (3, 14, 2, 1), (5, 6, 2, 2), (9, 6, 2, 2),
    ),
    "motion": (
        (7, 1, 2, 14), (1, 7, 14, 2), (6, 6, 4, 4),
        (5, 3, 2, 2), (9, 3, 2, 2), (5, 11, 2, 2), (9, 11, 2, 2),
        (3, 5, 2, 2), (3, 9, 2, 2), (11, 5, 2, 2), (11, 9, 2, 2),
    ),
    "systems": (
        (1, 13, 14, 2), (2, 9, 2, 4), (5, 5, 2, 8),
        (8, 7, 2, 6), (11, 2, 2, 11), (14, 10, 1, 3),
    ),
    "settings": (
        (1, 3, 14, 2), (1, 8, 14, 2), (1, 13, 14, 2),
        (4, 1, 3, 6), (10, 6, 3, 6), (6, 11, 3, 5),
    ),
    "warning": (
        (7, 1, 2, 2), (6, 3, 4, 2), (5, 5, 6, 2),
        (4, 7, 8, 2), (3, 9, 10, 2), (2, 11, 12, 2), (1, 13, 14, 2),
        (7, 5, 2, 5), (7, 12, 2, 1),
    ),
}

ICON_NAMES: Final = tuple(ICON_RECTS)


def draw_icon(
    surface: pygame.Surface,
    name: str,
    rect: pygame.Rect | tuple[int, int, int, int],
    color: tuple[int, int, int],
    *,
    background: tuple[int, int, int] | None = None,
) -> pygame.Rect:
    """Draw an icon with integer edges at any target size, including 16/24 px."""
    if name not in ICON_RECTS:
        raise ValueError(f"Unknown TARS95 icon: {name}")

    target = pygame.Rect(rect)
    icon_size = min(target.width, target.height)
    left = target.left + (target.width - icon_size) // 2
    top = target.top + (target.height - icon_size) // 2
    bounds = pygame.Rect(left, top, icon_size, icon_size)
    if background is not None:
        pygame.draw.rect(surface, background, bounds)

    for x, y, width, height in ICON_RECTS[name]:
        x0 = left + x * icon_size // GRID_SIZE
        y0 = top + y * icon_size // GRID_SIZE
        x1 = left + (x + width) * icon_size // GRID_SIZE
        y1 = top + (y + height) * icon_size // GRID_SIZE
        pygame.draw.rect(surface, color, (x0, y0, max(1, x1 - x0), max(1, y1 - y0)))
    return bounds


def render_icon(
    name: str,
    size: int = 16,
    color: tuple[int, int, int] = (232, 227, 209),
) -> pygame.Surface:
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    draw_icon(surface, name, surface.get_rect(), color)
    return surface
