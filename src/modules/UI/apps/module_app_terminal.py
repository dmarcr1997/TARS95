"""Hardware-safe app adapter for previewing the production command console."""

from __future__ import annotations

import time

from modules.UI.module_ui_terminal import TerminalSystem


class TerminalPreviewApp:
    def __init__(self, screen, width: int, height: int) -> None:
        self.screen = screen
        self.terminal = TerminalSystem(width, height)
        now = time.time()
        self.terminal.messages = [
            ("SYSTEM", "Local command channel initialized. Hardware output remains locked.", "INFO", now - 3),
            ("OPERATOR", "Run a complete status check.", "USER", now - 2),
            ("TARS", "Display path ready. Audio, vision, and motion await live device telemetry.", "TARS", now - 1),
        ]
        self.terminal.cache_dirty = True

    def reset(self) -> None:
        self.terminal.scroll_offset = 0
        self.terminal.auto_scroll = True

    def update(self) -> None:
        self.terminal.update()

    def render(self) -> None:
        self.terminal.draw(self.screen)

    def set_preview_state(self, snapshot) -> None:
        self.terminal.set_tars_status(str(snapshot.machine_state).upper())
        self.terminal._alert = str(snapshot.alert).upper()
        self.terminal._connectivity = str(snapshot.connectivity).upper()
        mode = "client" if snapshot.connectivity == "online" else (
            "hotspot" if snapshot.connectivity == "degraded" else "disconnected"
        )
        self.terminal.set_wifi_status(mode, 100 if mode == "client" else 32 if mode == "hotspot" else 0)
        self.terminal.thinking = snapshot.machine_state == "thinking"

    def handle_event(self, event):
        if hasattr(event, "pos"):
            self.terminal.handle_click(event.pos)
            return True
        return False

    def cleanup(self) -> None:
        pass
