#!/usr/bin/env python3
"""Hardware-safe desktop runner for the production TARS pygame apps."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
MODULES_DIR = SRC_DIR / "modules"

PHYSICAL_SIZES = {
    "480x320": (480, 320),
    "800x480": (800, 480),
}

APP_SPECS = {
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
        "--list",
        action="store_true",
        help="List available app names and exit.",
    )
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


def install_preview_stubs() -> None:
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
        get_tars_state=_blocked_hardware("state.read"),
    )
    _install_module(
        "modules.module_tts",
        is_tts_playing=lambda: False,
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


def main() -> int:
    args = parse_args()
    if args.list:
        print("\n".join(APP_SPECS))
        return 0

    if args.frames is not None and args.frames < 1:
        raise SystemExit("--frames must be at least 1")
    if args.headless and args.frames is None:
        args.frames = 2

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    sys.path.insert(0, str(SRC_DIR))
    os.chdir(MODULES_DIR)
    install_preview_stubs()

    import pygame

    physical_width, physical_height = PHYSICAL_SIZES[args.size]
    logical_width, logical_height = physical_height, physical_width

    pygame.display.init()
    pygame.font.init()
    display = pygame.display.set_mode((physical_width, physical_height))
    pygame.display.set_caption(
        f"TARS/95 preview — {args.app} — physical {args.size} / "
        f"logical {logical_width}x{logical_height}"
    )

    logical_surface = pygame.Surface((logical_width, logical_height)).convert()
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
    if args.frames is None:
        print("ESC quits; LEFT/RIGHT or 1-5 switches apps; R reconstructs the app.")

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
                    elif pygame.K_1 <= event.key <= pygame.K_5:
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

            app.update()
            app.render()
            physical_frame = pygame.transform.rotate(logical_surface, 270)
            display.blit(physical_frame, (0, 0))
            pygame.display.flip()

            frame_count += 1
            if args.frames is not None and frame_count >= args.frames:
                running = False
            clock.tick(30)

        if args.screenshot:
            screenshot_path = args.screenshot.expanduser().resolve()
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(display, screenshot_path)
            print(f"Screenshot: {screenshot_path}")
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
