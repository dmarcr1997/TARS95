"""Capture and verify the four canonical pre-redesign UI baseline frames."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from werkzeug.serving import WSGIRequestHandler, make_server

from web_preview import HOST, create_app


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "Documentation" / "review-baselines" / "UI-005"
DEVICE_PREVIEW = Path(__file__).resolve().parent / "device_preview.py"

CAPTURES = {
    "device-480x320.png": (480, 320),
    "device-800x480.png": (800, 480),
    "web-desktop-1440x900.png": (1440, 900),
    "web-mobile-390x844.png": (390, 844),
}


class QuietRequestHandler(WSGIRequestHandler):
    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=5095)
    return parser.parse_args()


def capture_device(output_dir: Path, size: str) -> None:
    output_path = output_dir / f"device-{size}.png"
    command = [
        sys.executable,
        str(DEVICE_PREVIEW),
        "--app", "avatar",
        "--size", size,
        "--state", "standby",
        "--battery", "95",
        "--alert", "none",
        "--connectivity", "online",
        "--headless",
        "--frames", "6",
        "--screenshot", str(output_path),
    ]
    environment = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)


def launch_installed_browser(playwright):
    errors = []
    for channel in ("chrome", "msedge"):
        try:
            return playwright.chromium.launch(channel=channel, headless=True), channel
        except PlaywrightError as exc:
            errors.append(f"{channel}: {exc}")
    raise RuntimeError("Could not launch installed Chrome or Edge.\n" + "\n".join(errors))


def capture_web(output_dir: Path, port: int) -> str:
    url = f"http://{HOST}:{port}/"
    with sync_playwright() as playwright:
        browser, channel = launch_installed_browser(playwright)
        try:
            viewports = (
                ("web-desktop-1440x900.png", 1440, 900, False),
                ("web-mobile-390x844.png", 390, 844, True),
            )
            for filename, width, height, mobile in viewports:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    is_mobile=mobile,
                    has_touch=mobile,
                    reduced_motion="reduce",
                )
                page = context.new_page()
                console_errors: list[str] = []
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: console_errors.append(str(error)))
                page.on(
                    "response",
                    lambda response: console_errors.append(f"HTTP {response.status}: {response.url}")
                    if response.url.startswith(url) and response.status >= 400 else None,
                )
                page.route(
                    "https://fonts.googleapis.com/**",
                    lambda route: route.fulfill(status=200, content_type="text/css", body=""),
                )
                page.route(
                    "https://unpkg.com/**",
                    lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
                )
                page.goto(url, wait_until="domcontentloaded")
                page.locator("#chat").wait_for(state="visible")
                page.wait_for_timeout(1200)
                page.add_style_tag(content="""
                    .preview-console, .preview-readout { display: none !important; }
                    * { caret-color: transparent !important; }
                """)
                page.screenshot(
                    path=output_dir / filename,
                    full_page=False,
                    animations="disabled",
                    scale="css",
                )
                context.close()
                if console_errors:
                    raise RuntimeError(f"Browser console errors in {filename}: {console_errors}")
        finally:
            browser.close()
    return channel


def verify_and_write_manifest(output_dir: Path, browser_channel: str) -> None:
    files: list[dict[str, Any]] = []
    for filename, expected_size in CAPTURES.items():
        path = output_dir / filename
        with Image.open(path) as image:
            actual_size = image.size
        if actual_size != expected_size:
            raise RuntimeError(f"{filename}: expected {expected_size}, got {actual_size}")
        files.append({
            "file": filename,
            "width": actual_size[0],
            "height": actual_size[1],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    manifest = {
        "baseline": "UI-005",
        "purpose": "Pre-redesign reference; not a locked pixel-regression set.",
        "source_revision": revision,
        "browser_channel": browser_channel,
        "web_preview_controls": "hidden",
        "external_web_assets": "neutralized; offline fallback captured",
        "files": files,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    output_dir = args.output.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    capture_device(output_dir, "480x320")
    capture_device(output_dir, "800x480")

    app, _socketio = create_app(port=args.port)
    server = make_server(HOST, args.port, app, threaded=True, request_handler=QuietRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        browser_channel = capture_web(output_dir, args.port)
    finally:
        server.shutdown()
        server_thread.join(timeout=5)

    verify_and_write_manifest(output_dir, browser_channel)
    print(f"PASS: 4 verified baseline frames written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
