#!/usr/bin/env python3
"""Hardware-safe desktop runner for the production TARS pygame apps."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import types
from pathlib import Path

from preview_state import (
    ALERT_LEVELS,
    CONNECTIVITY_STATES,
    MACHINE_STATES,
    PreviewState,
    PreviewStateStore,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
MODULES_DIR = SRC_DIR / "modules"

PHYSICAL_SIZES = {
    "480x320": (480, 320),
    "800x480": (800, 480),
}

APP_SPECS = {
    "boot": ("modules.UI.apps.module_app_boot", "BootApp"),
    "clock": ("modules.UI.apps.module_app_clock", "ClockApp"),
    "eyes": ("modules.UI.apps.module_app_eyes", "EyesApp"),
    "avatar": ("modules.UI.apps.module_app_avatar", "AvatarApp"),
    "remote": ("modules.UI.apps.module_app_remote", "RemoteApp"),
    "audio": ("modules.UI.apps.module_app_audio_timeline", "AudioTimelineApp"),
}

HARDWARE_ATTEMPTS: list[str] = []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render the real TARS 2D pygame apps in a desktop window without "
            "loading config.ini or accessing robot hardware."
        )
    )
    parser.add_argument("--app", choices=APP_SPECS, default="clock")
    parser.add_argument("--size", choices=PHYSICAL_SIZES, default="480x320")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use SDL's dummy video driver for automated render checks.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        help="Exit after this many frames. Headless mode defaults to two frames.",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="Save the final physical display frame as a PNG.",
    )
    parser.add_argument(
        "--harness-screenshot",
        type=Path,
        help="Save the desktop harness, including preview controls, as a PNG.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available app names and exit.",
    )
    parser.add_argument("--state", choices=MACHINE_STATES, default="standby")
    parser.add_argument("--battery", type=int, default=95)
    parser.add_argument("--alert", choices=ALERT_LEVELS, default="none")
    parser.add_argument("--connectivity", choices=CONNECTIVITY_STATES, default="online")
    return parser.parse_args()


def _blocked_hardware(name: str):
    def blocked(*_args, **_kwargs):
        HARDWARE_ATTEMPTS.append(name)
        raise RuntimeError(f"Hardware action blocked by UI preview: {name}")

    return blocked


def _install_module(name: str, **members) -> None:
    module = types.ModuleType(name)
    module.__dict__.update(members)
    sys.modules[name] = module


def install_preview_stubs(preview_state: PreviewStateStore) -> None:
    """Replace lazy robot integrations before any production app is imported."""

    preview_config = {
        "CHAR": {
            "character_card_path": "character/TARS/TARS.json",
            "character_name": "TARS",
        },
        "ACCESS": {"webui_port": 80},
        "TTS": {"ttsoption": "preview-disabled"},
    }

    class PreviewWiFiManager:
        HOTSPOT_SSID = "TARS95-PREVIEW"
        HOTSPOT_PASSWORD = "hardware-disabled"
        HOTSPOT_IP = "127.0.0.1"

    _install_module("modules.module_config", load_config=lambda: preview_config)
    _install_module("modules.module_stt", get_stt_manager=lambda: None)
    _install_module(
        "modules.module_state",
        get_tars_state=lambda: types.SimpleNamespace(
            value=preview_state.snapshot().machine_state,
        ),
    )
    _install_module(
        "modules.module_tts",
        is_tts_playing=lambda: preview_state.snapshot().machine_state == "talking",
        play_audio_chunks=_blocked_hardware("audio.play"),
    )
    _install_module(
        "modules.module_mic",
        get_native_rate=_blocked_hardware("microphone.read"),
    )
    _install_module(
        "modules.module_wifi",
        WiFiManager=PreviewWiFiManager,
        _get_manager=_blocked_hardware("wifi.access"),
    )
    _install_module(
        "modules.module_chatui",
        _start_tunnel=_blocked_hardware("tunnel.start"),
        _stop_tunnel=_blocked_hardware("tunnel.stop"),
    )
    _install_module(
        "modules.module_messageQue",
        queue_message=lambda message: print(f"[preview log] {message}"),
    )


def load_app(app_name: str, surface, width: int, height: int):
    module_name, class_name = APP_SPECS[app_name]
    module = importlib.import_module(module_name)

    # Eye touch normally triggers TTS. Input is not forwarded in preview, and
    # this override makes that safety boundary explicit if it changes later.
    if app_name == "eyes":
        module._speak_in_background = _blocked_hardware("audio.play")

    app_class = getattr(module, class_name)
    return app_class(surface, width, height)


class PreviewControlPanel:
    """Mouse and keyboard controls drawn outside the robot framebuffer."""

    WIDTH = 260

    def __init__(self, pygame_module, state: PreviewStateStore, x: int, height: int):
        self.pygame = pygame_module
        self.state = state
        self.rect = pygame_module.Rect(x, 0, self.WIDTH, height)
        self.compact = height < 400
        self.targets: list[tuple[Any, str, Any]] = []
        self.title_font = pygame_module.font.SysFont("consolas", 17, bold=True)
        self.label_font = pygame_module.font.SysFont("consolas", 11, bold=True)
        self.button_font = pygame_module.font.SysFont("consolas", 11)
        self.small_font = pygame_module.font.SysFont("consolas", 10)

    def handle_click(self, position: tuple[int, int]) -> bool:
        for rect, field, value in self.targets:
            if rect.collidepoint(position):
                if field == "battery_delta":
                    battery = max(0, min(100, self.state.snapshot().battery + int(value)))
                    self.state.update(battery=battery)
                else:
                    self.state.update(**{field: value})
                return True
        return False

    def draw(self, surface) -> None:
        pg = self.pygame
        x, width, height = self.rect.x, self.rect.width, self.rect.height
        pg.draw.rect(surface, (12, 18, 20), self.rect)
        pg.draw.line(surface, (255, 176, 0), (x, 0), (x, height), 3)
        pg.draw.rect(surface, (3, 28, 85), (x + 3, 0, width - 3, 34))
        surface.blit(self.title_font.render("PREVIEW CONTROL", True, (255, 255, 255)), (x + 15, 8))
        self.targets.clear()
        y = 42 if self.compact else 48
        y = self._draw_choices(surface, "MACHINE STATE  [S]", "machine_state", MACHINE_STATES, y)
        y = self._draw_battery(surface, y)
        y = self._draw_choices(surface, "ALERT LEVEL  [A]", "alert", ALERT_LEVELS, y)
        y = self._draw_choices(surface, "CONNECTIVITY  [C]", "connectivity", CONNECTIVITY_STATES, y)

        help_lines = ("KEYS: S STATE / B BAT / A ALERT / C LINK",) if self.compact else (
            "LEFT/RIGHT  APP", "1–5         SELECT", "R           RELOAD", "ESC         EXIT",
        )
        help_y = y + 2 if self.compact else max(y + 5, height - 62)
        for line in help_lines:
            surface.blit(self.small_font.render(line, True, (145, 169, 171)), (x + 15, help_y))
            help_y += 13

    def _draw_choices(self, surface, label: str, field: str, values: tuple[str, ...], y: int) -> int:
        pg = self.pygame
        x = self.rect.x + 15
        surface.blit(self.label_font.render(label, True, (255, 176, 0)), (x, y))
        y += 15 if self.compact else 18
        current = getattr(self.state.snapshot(), field)
        columns = 2
        gap = 6
        button_width = (self.WIDTH - 30 - gap) // columns
        for index, value in enumerate(values):
            row, column = divmod(index, columns)
            row_height = 23 if self.compact else 27
            button_height = 19 if self.compact else 22
            rect = pg.Rect(x + column * (button_width + gap), y + row * row_height, button_width, button_height)
            active = value == current
            fill = (22, 217, 196) if active else (35, 46, 49)
            ink = (4, 15, 17) if active else (211, 226, 222)
            pg.draw.rect(surface, fill, rect)
            pg.draw.rect(surface, (120, 143, 145), rect, 1)
            text = self.button_font.render(value.upper(), True, ink)
            surface.blit(text, text.get_rect(center=rect.center))
            self.targets.append((rect, field, value))
        rows = (len(values) + columns - 1) // columns
        return y + rows * row_height + (5 if self.compact else 10)

    def _draw_battery(self, surface, y: int) -> int:
        pg = self.pygame
        x = self.rect.x + 15
        snapshot = self.state.snapshot()
        surface.blit(self.label_font.render("BATTERY  [B]", True, (255, 176, 0)), (x, y))
        y += 15 if self.compact else 18
        height = 20 if self.compact else 24
        minus = pg.Rect(x, y, 35, height)
        plus = pg.Rect(x + self.WIDTH - 65, y, 35, height)
        meter = pg.Rect(x + 42, y, self.WIDTH - 114, height)
        for rect, text, delta in ((minus, "−", -5), (plus, "+", 5)):
            pg.draw.rect(surface, (35, 46, 49), rect)
            pg.draw.rect(surface, (120, 143, 145), rect, 1)
            label = self.button_font.render(text, True, (255, 255, 255))
            surface.blit(label, label.get_rect(center=rect.center))
            self.targets.append((rect, "battery_delta", delta))
        pg.draw.rect(surface, (3, 9, 11), meter)
        fill_width = int(meter.width * snapshot.battery / 100)
        color = (240, 68, 54) if snapshot.battery <= 20 else (255, 176, 0) if snapshot.battery <= 40 else (56, 232, 120)
        pg.draw.rect(surface, color, (meter.x, meter.y, fill_width, meter.height))
        label = self.button_font.render(f"{snapshot.battery:03d}%", True, (255, 255, 255))
        surface.blit(label, label.get_rect(center=meter.center))
        return y + height + (6 if self.compact else 14)


def apply_state_to_app(app_name: str, app, preview_state: PreviewStateStore) -> None:
    module_name, _class_name = APP_SPECS[app_name]
    app_module = sys.modules.get(module_name)
    if hasattr(app, "set_preview_state"):
        app.set_preview_state(preview_state.snapshot())
    if app_name == "avatar":
        if app_module and hasattr(app_module, "set_talking_state"):
            app_module.set_talking_state(preview_state.snapshot().machine_state == "talking")


def main() -> int:
    args = parse_args()
    if args.list:
        print("\n".join(APP_SPECS))
        return 0

    if args.frames is not None and args.frames < 1:
        raise SystemExit("--frames must be at least 1")
    if not 0 <= args.battery <= 100:
        raise SystemExit("--battery must be from 0 to 100")
    if args.headless and args.frames is None:
        args.frames = 2

    preview_state = PreviewStateStore(PreviewState(
        machine_state=args.state,
        battery=args.battery,
        alert=args.alert,
        connectivity=args.connectivity,
    ))

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    sys.path.insert(0, str(SRC_DIR))
    os.chdir(MODULES_DIR)
    install_preview_stubs(preview_state)

    import pygame

    physical_width, physical_height = PHYSICAL_SIZES[args.size]
    logical_width, logical_height = physical_height, physical_width
    controls_visible = not args.headless or args.harness_screenshot is not None
    display_width = physical_width + (PreviewControlPanel.WIDTH if controls_visible else 0)

    pygame.display.init()
    pygame.font.init()
    display = pygame.display.set_mode((display_width, physical_height))
    pygame.display.set_caption(
        f"TARS/95 preview — {args.app} — physical {args.size} / "
        f"logical {logical_width}x{logical_height}"
    )

    logical_surface = pygame.Surface((logical_width, logical_height)).convert()
    control_panel = PreviewControlPanel(
        pygame, preview_state, physical_width, physical_height,
    ) if controls_visible else None
    app_names = list(APP_SPECS)
    app_index = app_names.index(args.app)
    app = load_app(args.app, logical_surface, logical_width, logical_height)
    clock = pygame.time.Clock()
    frame_count = 0
    running = True

    print(
        f"Previewing {args.app}: logical={logical_width}x{logical_height}, "
        f"physical={physical_width}x{physical_height}, rotation=270"
    )
    print(
        "Preview state: "
        f"{preview_state.snapshot().machine_state}, "
        f"battery={preview_state.snapshot().battery}%, "
        f"alert={preview_state.snapshot().alert}, "
        f"connectivity={preview_state.snapshot().connectivity}"
    )
    if args.frames is None:
        print(f"ESC quits; LEFT/RIGHT or 1-{len(app_names)} switches apps; S/B/A/C cycles preview state.")

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                        step = -1 if event.key == pygame.K_LEFT else 1
                        app_index = (app_index + step) % len(app_names)
                        app.cleanup()
                        app = load_app(
                            app_names[app_index], logical_surface,
                            logical_width, logical_height,
                        )
                        pygame.display.set_caption(
                            f"TARS/95 preview — {app_names[app_index]} — {args.size}"
                        )
                    elif pygame.K_1 <= event.key < pygame.K_1 + len(app_names):
                        app_index = event.key - pygame.K_1
                        app.cleanup()
                        app = load_app(
                            app_names[app_index], logical_surface,
                            logical_width, logical_height,
                        )
                    elif event.key == pygame.K_r:
                        app.cleanup()
                        app = load_app(
                            app_names[app_index], logical_surface,
                            logical_width, logical_height,
                        )
                    elif event.key == pygame.K_s:
                        preview_state.cycle("machine_state", MACHINE_STATES)
                    elif event.key == pygame.K_b:
                        battery = preview_state.snapshot().battery
                        preview_state.update(battery=25 if battery >= 100 else min(100, battery + 25))
                    elif event.key == pygame.K_a:
                        preview_state.cycle("alert", ALERT_LEVELS)
                    elif event.key == pygame.K_c:
                        preview_state.cycle("connectivity", CONNECTIVITY_STATES)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if control_panel:
                        control_panel.handle_click(event.pos)

            apply_state_to_app(app_names[app_index], app, preview_state)
            app.update()
            app.render()
            physical_frame = pygame.transform.rotate(logical_surface, 270)
            display.fill((4, 8, 9))
            display.blit(physical_frame, (0, 0))
            if control_panel:
                control_panel.draw(display)
            pygame.display.flip()

            if app_names[app_index] == "boot" and getattr(app, "complete", False):
                app.cleanup()
                app_index = app_names.index("eyes")
                app = load_app("eyes", logical_surface, logical_width, logical_height)
                pygame.display.set_caption(
                    f"TARS/95 preview — eyes — {args.size} // BOOT HANDOFF"
                )

            frame_count += 1
            if args.frames is not None and frame_count >= args.frames:
                running = False
            clock.tick(30)

        if args.screenshot:
            screenshot_path = args.screenshot.expanduser().resolve()
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(physical_frame, screenshot_path)
            print(f"Screenshot: {screenshot_path}")
        if args.harness_screenshot:
            harness_path = args.harness_screenshot.expanduser().resolve()
            harness_path.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(display, harness_path)
            print(f"Harness screenshot: {harness_path}")
    finally:
        if hasattr(app, "cleanup"):
            app.cleanup()
        pygame.quit()

    if HARDWARE_ATTEMPTS:
        print("Blocked hardware attempts: " + ", ".join(HARDWARE_ATTEMPTS), file=sys.stderr)
        return 2

    print(f"Render check: OK ({frame_count} frames, hardware attempts: 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
