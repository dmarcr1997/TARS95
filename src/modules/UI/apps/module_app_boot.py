"""Deterministic TARS/95 power-on self-test and Eyes handoff surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame

from modules.UI.module_ui_state import STATE_PRESENTATIONS
from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CHROME_FACE,
    OFFLINE_GRAY,
    PANEL_LINE,
    PAPER_TEXT,
    READY_GREEN,
    SCREEN_INK,
    draw_grid,
    draw_label,
    draw_lamp,
    draw_rule,
    draw_status_bar,
    draw_title_bar,
    load_font,
    scale_for,
    scaled,
)


BOOT_STEPS = (
    ("DISPLAY PIPE", "READY"),
    ("UI TOKENS", "READY"),
    ("DEVICE I/O", "DEFERRED"),
    ("MOTION OUTPUT", "LOCKED"),
    ("NETWORK LINK", "DEFERRED"),
    ("EYES HOME", "READY"),
)


@dataclass(frozen=True)
class BootSnapshot:
    elapsed_ms: int
    completed_steps: int
    progress: float
    complete: bool


class BootSequence:
    """Pure timing model shared by production rendering and smoke tests."""

    STEP_MS = 360
    HANDOFF_MS = 480
    TOTAL_MS = len(BOOT_STEPS) * STEP_MS + HANDOFF_MS

    def snapshot(self, elapsed_ms: int) -> BootSnapshot:
        elapsed = max(0, int(elapsed_ms))
        completed = min(len(BOOT_STEPS), elapsed // self.STEP_MS)
        return BootSnapshot(
            elapsed_ms=elapsed,
            completed_steps=completed,
            progress=min(1.0, elapsed / self.TOTAL_MS),
            complete=elapsed >= self.TOTAL_MS,
        )


class BootApp:
    """Physical-first boot surface that never probes robot hardware."""

    def __init__(
        self,
        screen: pygame.Surface,
        width: int,
        height: int,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.screen = screen
        self.width = width
        self.height = height
        self.physical_width = height
        self.physical_height = width
        self._physical_frame = pygame.Surface((self.physical_width, self.physical_height))
        self._clock_ms = clock_ms or pygame.time.get_ticks
        self.sequence = BootSequence()
        self._started_ms = self._clock_ms()
        self.snapshot = self.sequence.snapshot(0)

    @property
    def complete(self) -> bool:
        return self.snapshot.complete

    def reset(self) -> None:
        self._started_ms = self._clock_ms()
        self.snapshot = self.sequence.snapshot(0)

    def update(self) -> None:
        self.snapshot = self.sequence.snapshot(self._clock_ms() - self._started_ms)

    def handle_event(self, _event: pygame.event.Event) -> bool:
        return False

    def render(self) -> None:
        frame = self._physical_frame
        frame.fill(CANVAS_BLACK)
        scale = scale_for(frame)
        title_h = scaled(28, scale)
        status_h = scaled(25, scale)
        content = pygame.Rect(0, title_h, frame.get_width(), frame.get_height() - title_h - status_h)
        draw_grid(frame, content, step=scaled(32, scale))

        presentation = STATE_PRESENTATIONS["BOOTING"]
        draw_title_bar(
            frame,
            "TARS/95",
            "POWER-ON // SELF TEST",
            presentation.label,
            height=title_h,
            state_color=presentation.color,
            icon="systems",
        )

        left = pygame.Rect(
            scaled(10, scale), title_h + scaled(12, scale),
            scaled(166, scale), content.height - scaled(24, scale),
        )
        right = pygame.Rect(
            left.right + scaled(18, scale), left.top,
            frame.get_width() - left.right - scaled(28, scale), left.height,
        )
        self._draw_identity(frame, left, presentation.color, scale)
        self._draw_checks(frame, right, presentation.color, scale)
        self._draw_progress(frame, content, presentation.color, scale)

        draw_status_bar(
            frame,
            (
                ("MODE", "SAFE", CHROME_FACE),
                ("I/O", "DEFER", OFFLINE_GRAY),
                ("NEXT", "EYES", presentation.color),
                ("BUILD", "V3", READY_GREEN),
            ),
            height=status_h,
        )
        self.screen.blit(pygame.transform.rotate(frame, 90), (0, 0))

    def _draw_identity(
        self,
        frame: pygame.Surface,
        rect: pygame.Rect,
        signal: tuple[int, int, int],
        scale: float,
    ) -> None:
        draw_label(frame, "ROBOT OPERATING ENVIRONMENT", rect.topleft, size=scaled(7, scale), color=OFFLINE_GRAY)
        mark_font = load_font(scaled(34, scale), "pixel")
        mark = mark_font.render("TARS", True, PAPER_TEXT)
        frame.blit(mark, (rect.left, rect.top + scaled(24, scale)))
        draw_label(
            frame, "/95", (rect.left + scaled(84, scale), rect.top + scaled(52, scale)),
            size=scaled(18, scale), color=CHROME_FACE, role="pixel",
        )
        draw_rule(
            frame,
            (rect.left, rect.top + scaled(86, scale)),
            (rect.right, rect.top + scaled(86, scale)),
            PANEL_LINE,
        )
        progress_number = min(99, int(self.snapshot.progress * 100))
        draw_label(
            frame, f"POST {progress_number:02d}",
            (rect.left, rect.top + scaled(98, scale)),
            size=scaled(14, scale), color=signal, role="pixel",
        )
        cue = "HANDOFF READY" if self.snapshot.complete else "SEQUENCE ACTIVE"
        draw_label(
            frame, cue,
            (rect.left, rect.top + scaled(123, scale)),
            size=scaled(8, scale), color=READY_GREEN if self.snapshot.complete else PAPER_TEXT,
        )

    def _draw_checks(
        self,
        frame: pygame.Surface,
        rect: pygame.Rect,
        signal: tuple[int, int, int],
        scale: float,
    ) -> None:
        draw_label(frame, "SELF-TEST INDEX", rect.topleft, size=scaled(8, scale), color=CHROME_FACE, role="pixel")
        row_h = scaled(25, scale)
        row_y = rect.top + scaled(20, scale)
        for index, (label, result) in enumerate(BOOT_STEPS):
            complete = index < self.snapshot.completed_steps
            active = index == self.snapshot.completed_steps and not self.snapshot.complete
            value = result if complete else "CHECK" if active else "--"
            value_color = (
                READY_GREEN if complete and result == "READY"
                else signal if complete and result == "LOCKED"
                else OFFLINE_GRAY if complete
                else signal if active
                else PANEL_LINE
            )
            draw_lamp(
                frame, (rect.left + scaled(3, scale), row_y + scaled(5, scale)),
                value_color, size=scaled(4, scale),
            )
            draw_label(
                frame, f"{index + 1:02d} {label}",
                (rect.left + scaled(12, scale), row_y),
                size=scaled(8, scale), color=PAPER_TEXT if complete or active else OFFLINE_GRAY,
            )
            value_image = load_font(scaled(8, scale)).render(value, True, value_color)
            frame.blit(value_image, value_image.get_rect(topright=(rect.right, row_y)))
            draw_rule(
                frame,
                (rect.left, row_y + scaled(15, scale)),
                (rect.right, row_y + scaled(15, scale)),
                SCREEN_INK if index % 2 else PANEL_LINE,
            )
            row_y += row_h

    def _draw_progress(
        self,
        frame: pygame.Surface,
        content: pygame.Rect,
        signal: tuple[int, int, int],
        scale: float,
    ) -> None:
        segments = 20
        filled = min(segments, int(self.snapshot.progress * segments))
        gap = scaled(3, scale)
        bar_h = scaled(7, scale)
        bar_x = scaled(10, scale)
        bar_y = content.bottom - scaled(12, scale)
        available = frame.get_width() - scaled(20, scale)
        segment_w = max(2, (available - gap * (segments - 1)) // segments)
        for index in range(segments):
            color = signal if index < filled else PANEL_LINE
            pygame.draw.rect(frame, color, (bar_x + index * (segment_w + gap), bar_y, segment_w, bar_h))

    def cleanup(self) -> None:
        pass
