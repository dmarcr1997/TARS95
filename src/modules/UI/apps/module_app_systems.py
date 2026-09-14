"""TARS/95 operator-facing power and subsystem monitor."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import shutil
import time

import pygame

from modules.UI.module_ui_state import resolve_presentation
from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CAUTION_AMBER,
    CHROME_FACE,
    FAULT_RED,
    OFFLINE_GRAY,
    PANEL_LINE,
    PANEL_MUTED,
    PAPER_TEXT,
    PHOSPHOR_CYAN,
    READY_GREEN,
    SCREEN_INK,
    draw_grid,
    draw_label,
    draw_panel,
    draw_rule,
    draw_status_bar,
    draw_title_bar,
    load_font,
    scale_for,
    scaled,
)


@dataclass(frozen=True)
class SystemTelemetry:
    """A single systems sample; missing readings remain explicit."""

    battery: float | None = None
    voltage: float | None = None
    current_ma: float | None = None
    battery_mode: str = "N/A"
    cpu: float | None = None
    temperature_c: float | None = None
    memory: float | None = None
    storage: float | None = None
    connectivity: str = "N/A"
    signal: int | None = None
    audio: str = "READY"
    source: str = "LIVE"


class SystemsApp:
    """Physical-first systems monitor with optional Pi telemetry sources."""

    SAMPLE_INTERVAL = 1.0

    def __init__(
        self,
        screen: pygame.Surface,
        width: int,
        height: int,
        *,
        battery_module=None,
        cpu_temp_module=None,
    ) -> None:
        self.output_screen = screen
        self.logical_width = width
        self.logical_height = height
        self.width = height
        self.height = width
        self.screen = pygame.Surface((self.width, self.height))

        self.battery_module = battery_module
        self.cpu_temp_module = cpu_temp_module
        self.telemetry = SystemTelemetry()
        self._machine_state = "STANDBY"
        self._alert = "NONE"
        self._connectivity = "N/A"
        self._signal = None
        self._preview_mode = False
        self._last_sample = 0.0
        self._previous_cpu_ticks: tuple[int, int] | None = None

    def reset(self) -> None:
        self._last_sample = 0.0
        self._previous_cpu_ticks = None

    def update(self) -> None:
        try:
            from modules.module_state import get_tars_state

            self._machine_state = str(get_tars_state().value).upper()
        except Exception:
            pass

        if self._preview_mode:
            self.telemetry = replace(
                self.telemetry,
                audio=self._audio_state(),
                connectivity=self._connectivity,
            )
            return

        now = time.monotonic()
        if now - self._last_sample < self.SAMPLE_INTERVAL:
            return
        self._last_sample = now
        self.telemetry = self._collect_live_sample()

    def set_preview_state(self, snapshot) -> None:
        """Use labeled deterministic fixtures; never probe desktop hardware."""
        self._preview_mode = True
        self._machine_state = str(snapshot.machine_state).upper()
        self._alert = str(snapshot.alert).upper()
        self._connectivity = str(snapshot.connectivity).upper()
        self._signal = 72 if self._connectivity == "ONLINE" else 34 if self._connectivity == "DEGRADED" else None
        self.telemetry = SystemTelemetry(
            battery=float(snapshot.battery),
            voltage=None,
            current_ma=None,
            battery_mode="FIXTURE",
            cpu=34.0,
            temperature_c=None,
            memory=41.0,
            storage=28.0,
            connectivity=self._connectivity,
            signal=self._signal,
            audio=self._audio_state(),
            source="PREVIEW FIXTURE",
        )

    def set_connectivity_status(self, mode: str, signal: int | None = None) -> None:
        normalized = str(mode).strip().upper()
        if normalized in {"CLIENT", "HOTSPOT", "ONLINE"}:
            self._connectivity = "ONLINE"
        elif normalized in {"DISCONNECTED", "OFFLINE"}:
            self._connectivity = "OFFLINE"
        elif normalized == "DEGRADED":
            self._connectivity = "DEGRADED"
        else:
            self._connectivity = "N/A"
        self._signal = signal

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def render(self) -> None:
        self.screen.fill(CANVAS_BLACK)
        scale = scale_for(self.screen)
        title_h = scaled(28, scale)
        status_h = scaled(25, scale)
        content = pygame.Rect(0, title_h, self.width, self.height - title_h - status_h)
        draw_grid(self.screen, content, step=scaled(32, scale))

        presentation = resolve_presentation(
            self._machine_state, self._alert, self._connectivity,
        )
        draw_title_bar(
            self.screen,
            "TARS/95",
            "SYSTEMS // MONITOR",
            presentation.label,
            height=title_h,
            state_color=presentation.color,
            icon="systems",
        )
        self._draw_content(content, scale)

        battery_text = self._format_percent(self.telemetry.battery)
        draw_status_bar(
            self.screen,
            (
                ("HOME", "EYES", CHROME_FACE),
                ("PWR", battery_text, self._level_color(self.telemetry.battery, 20, 40)),
                ("CPU", self._format_percent(self.telemetry.cpu), self._level_color(self.telemetry.cpu, 90, 75, high_bad=True)),
                ("MEM", self._format_percent(self.telemetry.memory), self._level_color(self.telemetry.memory, 90, 75, high_bad=True)),
                ("LINK", self.telemetry.connectivity, self._link_color()),
            ),
            height=status_h,
        )
        self.output_screen.blit(pygame.transform.rotate(self.screen, 90), (0, 0))

    def cleanup(self) -> None:
        pass

    def _collect_live_sample(self) -> SystemTelemetry:
        battery = voltage = current = None
        battery_mode = "N/A"
        if self.battery_module is not None:
            try:
                status = self.battery_module.get_battery_status()
                if status.get("sensor_initialized", False):
                    battery = float(status.get("normalized_percentage"))
                    voltage = float(status.get("voltage"))
                    current = float(status.get("current"))
                    battery_mode = str(status.get("charging_state", "N/A")).upper()
            except (AttributeError, TypeError, ValueError):
                pass

        temperature = None
        if self.cpu_temp_module is not None:
            try:
                status = self.cpu_temp_module.get_status()
                if status.get("sensor_available", False):
                    temperature = float(self.cpu_temp_module.get_temperature())
            except (AttributeError, TypeError, ValueError):
                pass

        return SystemTelemetry(
            battery=battery,
            voltage=voltage,
            current_ma=current,
            battery_mode=battery_mode,
            cpu=self._read_cpu_percent(),
            temperature_c=temperature,
            memory=self._read_memory_percent(),
            storage=self._read_storage_percent(),
            connectivity=self._connectivity,
            signal=self._signal,
            audio=self._audio_state(),
            source="LIVE",
        )

    def _read_cpu_percent(self) -> float | None:
        try:
            fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()[1:]
            ticks = [int(value) for value in fields]
            idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
            total = sum(ticks)
            previous = self._previous_cpu_ticks
            self._previous_cpu_ticks = (idle, total)
            if previous is None:
                return None
            idle_delta = idle - previous[0]
            total_delta = total - previous[1]
            if total_delta <= 0:
                return None
            return max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0))
        except (OSError, ValueError, IndexError):
            return None

    @staticmethod
    def _read_memory_percent() -> float | None:
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0])
            total = values["MemTotal"]
            available = values["MemAvailable"]
            return (1.0 - available / total) * 100.0 if total else None
        except (OSError, ValueError, KeyError):
            return None

    @staticmethod
    def _read_storage_percent() -> float | None:
        try:
            usage = shutil.disk_usage(os.path.abspath(os.sep))
            return usage.used / usage.total * 100.0 if usage.total else None
        except OSError:
            return None

    def _audio_state(self) -> str:
        if self._machine_state == "TALKING":
            return "PLAYING"
        if self._machine_state == "LISTENING":
            return "LISTENING"
        return "READY"

    def _draw_content(self, content: pygame.Rect, scale: float) -> None:
        margin = scaled(10, scale)
        gap = scaled(8, scale)
        top = content.top + margin
        height = content.height - margin * 2
        power_width = scaled(150, scale)
        power_rect = pygame.Rect(margin, top, power_width, height)
        draw_panel(self.screen, power_rect)
        self._draw_power_panel(power_rect, scale)

        grid_left = power_rect.right + gap
        grid_width = self.width - grid_left - margin
        cell_width = (grid_width - gap) // 2
        cell_height = (height - gap * 2) // 3
        cells = (
            ("CPU LOAD", self.telemetry.cpu, "%", 90, 75, True),
            ("THERMAL", self.telemetry.temperature_c, "C", 80, 70, True),
            ("MEMORY", self.telemetry.memory, "%", 90, 75, True),
            ("STORAGE", self.telemetry.storage, "%", 95, 85, True),
        )
        for index, item in enumerate(cells):
            row, column = divmod(index, 2)
            rect = pygame.Rect(
                grid_left + column * (cell_width + gap),
                top + row * (cell_height + gap),
                cell_width,
                cell_height,
            )
            self._draw_metric_panel(rect, *item, scale)

        row_y = top + 2 * (cell_height + gap)
        network_rect = pygame.Rect(grid_left, row_y, cell_width, cell_height)
        audio_rect = pygame.Rect(grid_left + cell_width + gap, row_y, cell_width, cell_height)
        self._draw_text_panel(
            network_rect,
            "NETWORK",
            self.telemetry.connectivity,
            "SIGNAL " + (f"{self.telemetry.signal:03d}%" if self.telemetry.signal is not None else "N/A"),
            self._link_color(),
            scale,
        )
        audio_color = READY_GREEN if self.telemetry.audio == "PLAYING" else PHOSPHOR_CYAN
        self._draw_text_panel(
            audio_rect,
            "AUDIO I/O",
            self.telemetry.audio,
            "STATE BUS",
            audio_color,
            scale,
        )

    def _draw_power_panel(self, rect: pygame.Rect, scale: float) -> None:
        draw_label(
            self.screen,
            "POWER CORE // 01",
            (rect.left + scaled(10, scale), rect.top + scaled(10, scale)),
            size=scaled(8, scale),
            color=CAUTION_AMBER,
        )
        battery_color = self._level_color(self.telemetry.battery, 20, 40)
        value = self._format_percent(self.telemetry.battery)
        image = load_font(scaled(33, scale), "mono").render(value, True, battery_color)
        self.screen.blit(image, (rect.left + scaled(10, scale), rect.top + scaled(39, scale)))

        meter = pygame.Rect(
            rect.left + scaled(11, scale),
            rect.top + scaled(88, scale),
            rect.width - scaled(22, scale),
            scaled(56, scale),
        )
        self._draw_segment_meter(meter, self.telemetry.battery, battery_color, scale)
        draw_label(
            self.screen,
            f"MODE {self.telemetry.battery_mode}",
            (rect.left + scaled(10, scale), rect.top + scaled(157, scale)),
            size=scaled(8, scale),
            color=PAPER_TEXT,
        )
        draw_label(
            self.screen,
            "VOLT " + self._format_value(self.telemetry.voltage, "V", 2),
            (rect.left + scaled(10, scale), rect.top + scaled(178, scale)),
            size=scaled(8, scale),
            color=PANEL_MUTED,
        )
        draw_label(
            self.screen,
            "DRAW " + self._format_value(self.telemetry.current_ma, "mA", 0),
            (rect.left + scaled(10, scale), rect.top + scaled(196, scale)),
            size=scaled(8, scale),
            color=PANEL_MUTED,
        )
        draw_rule(
            self.screen,
            (rect.left + scaled(10, scale), rect.bottom - scaled(29, scale)),
            (rect.right - scaled(10, scale), rect.bottom - scaled(29, scale)),
            PANEL_LINE,
        )
        draw_label(
            self.screen,
            self.telemetry.source,
            (rect.left + scaled(10, scale), rect.bottom - scaled(20, scale)),
            size=scaled(7, scale),
            color=OFFLINE_GRAY,
        )

    def _draw_metric_panel(
        self,
        rect: pygame.Rect,
        label: str,
        value: float | None,
        suffix: str,
        fault_at: float,
        warn_at: float,
        high_bad: bool,
        scale: float,
    ) -> None:
        color = self._level_color(value, fault_at, warn_at, high_bad=high_bad)
        draw_panel(self.screen, rect)
        draw_label(
            self.screen,
            label,
            (rect.left + scaled(8, scale), rect.top + scaled(7, scale)),
            size=scaled(7, scale),
            color=CHROME_FACE,
        )
        display = self._format_value(value, suffix, 0)
        image = load_font(scaled(18, scale), "mono").render(display, True, color)
        self.screen.blit(image, (rect.left + scaled(8, scale), rect.top + scaled(25, scale)))
        meter = pygame.Rect(
            rect.left + scaled(8, scale),
            rect.bottom - scaled(13, scale),
            rect.width - scaled(16, scale),
            scaled(5, scale),
        )
        self._draw_segment_meter(meter, value, color, scale)

    def _draw_text_panel(
        self,
        rect: pygame.Rect,
        label: str,
        value: str,
        detail: str,
        color: tuple[int, int, int],
        scale: float,
    ) -> None:
        draw_panel(self.screen, rect)
        draw_label(
            self.screen,
            label,
            (rect.left + scaled(8, scale), rect.top + scaled(7, scale)),
            size=scaled(7, scale),
            color=CHROME_FACE,
        )
        draw_label(
            self.screen,
            value,
            (rect.left + scaled(8, scale), rect.top + scaled(27, scale)),
            size=scaled(12, scale),
            color=color,
            role="pixel",
        )
        draw_label(
            self.screen,
            detail,
            (rect.left + scaled(8, scale), rect.bottom - scaled(17, scale)),
            size=scaled(7, scale),
            color=PANEL_MUTED,
        )

    def _draw_segment_meter(
        self,
        rect: pygame.Rect,
        value: float | None,
        color: tuple[int, int, int],
        scale: float,
    ) -> None:
        segments = 10
        gap = scaled(2, scale)
        active = 0 if value is None else max(0, min(segments, int(round(value / 10.0))))
        for index in range(segments):
            width = (rect.width - gap * (segments - 1)) // segments
            segment = pygame.Rect(rect.left + index * (width + gap), rect.top, width, rect.height)
            pygame.draw.rect(self.screen, color if index < active else PANEL_LINE, segment)

    def _link_color(self) -> tuple[int, int, int]:
        return {
            "ONLINE": READY_GREEN,
            "DEGRADED": CAUTION_AMBER,
            "OFFLINE": OFFLINE_GRAY,
        }.get(self.telemetry.connectivity, OFFLINE_GRAY)

    @staticmethod
    def _level_color(
        value: float | None,
        fault_at: float,
        warn_at: float,
        *,
        high_bad: bool = False,
    ) -> tuple[int, int, int]:
        if value is None:
            return OFFLINE_GRAY
        if high_bad:
            if value >= fault_at:
                return FAULT_RED
            if value >= warn_at:
                return CAUTION_AMBER
        else:
            if value <= fault_at:
                return FAULT_RED
            if value <= warn_at:
                return CAUTION_AMBER
        return READY_GREEN

    @staticmethod
    def _format_percent(value: float | None) -> str:
        return "N/A" if value is None else f"{int(round(value)):03d}%"

    @staticmethod
    def _format_value(value: float | None, suffix: str, decimals: int) -> str:
        if value is None:
            return "N/A"
        return f"{value:.{decimals}f}{suffix}"
