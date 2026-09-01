"""Full desktop smoke coverage for the hardware-safe UI preview stack."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIEW_ROOT = REPO_ROOT / "tools" / "ui-preview"
BASELINE_ROOT = REPO_ROOT / "Documentation" / "review-baselines" / "UI-005"
PROOF_ROOT = REPO_ROOT / "Documentation" / "review-proofs" / "UI-012"
sys.path.insert(0, str(PREVIEW_ROOT))

from capture_baselines import QuietRequestHandler, launch_installed_browser  # noqa: E402
from device_preview import APP_SPECS, PHYSICAL_SIZES, apply_state_to_app  # noqa: E402
from preview_state import (  # noqa: E402
    ALERT_LEVELS,
    CONNECTIVITY_STATES,
    MACHINE_STATES,
    PreviewStateStore,
)
from web_preview import HOST, available_themes, create_app, run_checks  # noqa: E402


class EnvironmentTests(unittest.TestCase):
    def test_preview_dependencies_import(self) -> None:
        modules = (
            "flask", "flask_socketio", "numpy", "PIL", "pygame",
            "OpenGL", "qrcode", "playwright",
        )
        for module_name in modules:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_web_preview_does_not_import_robot_runtime(self) -> None:
        robot_modules = [name for name in sys.modules if name == "modules" or name.startswith("modules.")]
        self.assertEqual([], robot_modules)


class PreviewStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PreviewStateStore()

    def test_defaults_and_valid_updates(self) -> None:
        self.assertEqual("standby", self.store.snapshot().machine_state)
        state = self.store.update(
            machine_state="talking", battery=15, alert="warning", connectivity="offline",
        )
        self.assertEqual(("talking", 15, "warning", "offline"), (
            state.machine_state, state.battery, state.alert, state.connectivity,
        ))

    def test_all_fixture_choices_cycle(self) -> None:
        for field, values in (
            ("machine_state", MACHINE_STATES),
            ("alert", ALERT_LEVELS),
            ("connectivity", CONNECTIVITY_STATES),
        ):
            with self.subTest(field=field):
                seen = {getattr(self.store.snapshot(), field)}
                for _ in range(len(values)):
                    seen.add(getattr(self.store.cycle(field, values), field))
                self.assertEqual(set(values), seen)

    def test_invalid_state_is_rejected(self) -> None:
        for changes in ({"battery": -1}, {"battery": 101}, {"alert": "meltdown"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.store.update(**changes)


class WebContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app, self.socketio = create_app()
        self.client = self.app.test_client()

    def test_complete_contract_check(self) -> None:
        run_checks(self.app, self.socketio)

    def test_tars95_theme_is_selectable_and_offline(self) -> None:
        themed_app, _socketio = create_app(theme="tars95")
        themed_client = themed_app.test_client()
        for route in ("/", "/login"):
            with self.subTest(route=route):
                response = themed_client.get(route)
                page = response.get_data(as_text=True)
                response.close()
                self.assertEqual(200, response.status_code)
                self.assertIn("css/themes/tars95.css", page)
                self.assertNotIn("https://", page)
        self.assertIn("tars95", available_themes())
        theme_response = themed_client.get("/static/css/themes/tars95.css")
        self.assertEqual(200, theme_response.status_code)
        theme_css = theme_response.get_data(as_text=True)
        theme_response.close()
        for token in (
            "--t95-canvas-black: #050708",
            "--t95-chrome-face: #d8c99b",
            "--t95-panel-line: #304044",
            "--t95-phosphor-cyan: #16d9c4",
            "--state-fault: var(--t95-fault-red)",
            "--font-mono: \"Lucida Console\"",
            ".t95-icon-chat { --t95-icon-source:",
        ):
            with self.subTest(token=token):
                self.assertIn(token, theme_css)
        for icon_name in ("chat", "motion", "avatar", "systems", "settings"):
            with self.subTest(icon=icon_name):
                icon_response = themed_client.get(f"/static/icons/tars95/{icon_name}.svg")
                self.assertEqual(200, icon_response.status_code)
                self.assertIn(b"shape-rendering=\"crispEdges\"", icon_response.data)
                icon_response.close()

    def test_all_robot_writes_are_no_ops(self) -> None:
        routes = (
            ("post", "/robot_move"),
            ("post", "/execute_action"),
            ("post", "/move_legs"),
            ("post", "/move_arms"),
            ("post", "/disable_servos"),
            ("post", "/reset_positions"),
            ("post", "/neutral_legs"),
            ("post", "/reboot_program"),
            ("post", "/api/wifi/connect"),
            ("put", "/api/wifi/hotspot"),
            ("post", "/api/tunnel/start"),
            ("post", "/api/tunnel/stop"),
        )
        for method, route in routes:
            with self.subTest(route=route):
                response = getattr(self.client, method)(route, json={})
                self.assertEqual(200, response.status_code)
                payload = response.get_json()
                self.assertTrue(payload["preview"])
                self.assertFalse(payload["hardware_access"])

    def test_state_reaches_metrics_wifi_and_socket(self) -> None:
        socket_client = self.socketio.test_client(self.app)
        response = self.client.post("/api/preview/state", json={
            "machine_state": "talking",
            "battery": 20,
            "alert": "fault",
            "connectivity": "offline",
        })
        self.assertEqual(200, response.status_code)
        metrics = self.client.get("/api/system/metrics").get_json()
        wifi = self.client.get("/api/wifi/status").get_json()
        events = socket_client.get_received()
        socket_client.disconnect()
        self.assertEqual(20, metrics["battery"])
        self.assertEqual("fault", metrics["alert"])
        self.assertEqual("disconnected", wifi["mode"])
        self.assertTrue(any(event["name"] == "preview_state" for event in events))
        self.assertTrue(any(
            event["name"] == "talking_state" and event["args"][0]["talking"]
            for event in events
        ))


class DeviceRenderTests(unittest.TestCase):
    def test_machine_state_presentation_contract_and_priority(self) -> None:
        code = """
import sys
sys.path.insert(0, r'{src}')
from modules.UI.module_ui_state import STATE_PRESENTATIONS, resolve_presentation

expected = {{
    'BOOTING': ('BOOTING', (47, 119, 208), 'stepped-progress'),
    'STANDBY': ('STANDBY', (120, 144, 156), 'ambient-only'),
    'LISTENING': ('LISTENING', (22, 217, 196), 'input-driven'),
    'THINKING': ('PROCESSING', (255, 176, 0), 'stepped-scan'),
    'TALKING': ('TALKING', (56, 232, 120), 'output-driven'),
    'WARNING': ('WARNING', (255, 176, 0), 'slow-pulse'),
    'FAULT': ('FAULT', (240, 68, 54), 'acknowledgement-only'),
    'OFFLINE': ('OFFLINE', (111, 119, 122), 'none'),
}}
assert set(STATE_PRESENTATIONS) == set(expected)
for key, values in expected.items():
    presentation = STATE_PRESENTATIONS[key]
    assert (presentation.label, presentation.color, presentation.motion) == values
assert resolve_presentation('talking', 'fault', 'offline').key == 'FAULT'
assert resolve_presentation('talking', 'warning', 'offline').key == 'WARNING'
assert resolve_presentation('talking', 'none', 'offline').key == 'OFFLINE'
assert resolve_presentation('thinking').label == 'PROCESSING'
""".format(src=str(REPO_ROOT / "src"))
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_original_pixel_icons_render_cleanly_at_contract_sizes(self) -> None:
        code = """
import sys
sys.path.insert(0, r'{src}')
import pygame
pygame.init()
from modules.UI.module_ui_icons import ICON_NAMES, render_icon
assert len(ICON_NAMES) == 10
for size in (16, 24):
    for name in ICON_NAMES:
        surface = render_icon(name, size, (22, 217, 196))
        assert surface.get_size() == (size, size)
        colors = {{tuple(pixel) for column in pygame.surfarray.array3d(surface) for pixel in column}}
        assert colors <= {{(0, 0, 0), (22, 217, 196)}}
        assert (22, 217, 196) in colors
pygame.quit()
""".format(src=str(REPO_ROOT / "src"))
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_preview_state_reaches_fixture_aware_device_apps(self) -> None:
        class FixtureAwareApp:
            snapshot = None

            def set_preview_state(self, snapshot) -> None:
                self.snapshot = snapshot

        store = PreviewStateStore()
        store.update(
            machine_state="listening", battery=40,
            alert="warning", connectivity="degraded",
        )
        app = FixtureAwareApp()
        apply_state_to_app("eyes", app, store)
        self.assertEqual(
            ("listening", 40, "warning", "degraded"),
            (
                app.snapshot.machine_state, app.snapshot.battery,
                app.snapshot.alert, app.snapshot.connectivity,
            ),
        )

    def test_eyes_render_as_horizontal_tars95_instrument_at_480x320(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tars95-eyes-style-") as temp_dir:
            directory = Path(temp_dir)
            self._render_case("eyes", "480x320", "listening", directory)
            with Image.open(directory / "eyes-480x320.png").convert("RGB") as image:
                self.assertEqual((216, 201, 155), image.getpixel((240, 10)))
                for position in ((190, 160), (290, 160)):
                    with self.subTest(position=position):
                        red, green, blue = image.getpixel(position)
                        self.assertLess(red, 80)
                        self.assertGreater(green, 150)
                        self.assertGreater(blue, 140)

    def test_all_apps_render_at_both_physical_sizes_without_hardware(self) -> None:
        cases = [
            (app_name, size, MACHINE_STATES[index % len(MACHINE_STATES)])
            for index, app_name in enumerate(APP_SPECS)
            for size in PHYSICAL_SIZES
        ]
        failures: list[str] = []
        with tempfile.TemporaryDirectory(prefix="tars95-device-smoke-") as temp_dir:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    pool.submit(self._render_case, app, size, state, Path(temp_dir)): (app, size)
                    for app, size, state in cases
                }
                for future in as_completed(futures):
                    app, size = futures[future]
                    try:
                        future.result()
                    except Exception as exc:  # aggregate every failing render
                        failures.append(f"{app}@{size}: {exc}")
        self.assertEqual([], failures, "\n".join(failures))

    def _render_case(self, app: str, size: str, state: str, temp_dir: Path) -> None:
        screenshot = temp_dir / f"{app}-{size}.png"
        command = [
            sys.executable, str(PREVIEW_ROOT / "device_preview.py"),
            "--app", app, "--size", size, "--state", state,
            "--battery", "55", "--alert", "advisory", "--connectivity", "degraded",
            "--headless", "--frames", "3", "--screenshot", str(screenshot),
        ]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy"),
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        if "hardware attempts: 0" not in result.stdout:
            raise AssertionError("hardware lockout result missing\n" + result.stdout)
        expected_size = PHYSICAL_SIZES[size]
        with Image.open(screenshot) as image:
            if image.size != expected_size:
                raise AssertionError(f"expected {expected_size}, got {image.size}")
            header_pixel = image.convert("RGB").getpixel((expected_size[0] // 2, 10))
            if header_pixel != (216, 201, 155):
                raise AssertionError(f"shared TARS95 header missing: {header_pixel}")


class BrowserRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app, _socketio = create_app(theme="tars95", port=0)
        cls.server = make_server(HOST, 0, cls.app, threaded=True, request_handler=QuietRequestHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)

    def test_desktop_and_mobile_render_without_browser_errors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tars95-web-smoke-") as temp_dir:
            with sync_playwright() as playwright:
                browser, _channel = launch_installed_browser(playwright)
                try:
                    self._check_viewport(browser, 1440, 900, False, Path(temp_dir) / "desktop.png")
                    self._check_viewport(browser, 390, 844, True, Path(temp_dir) / "mobile.png")
                finally:
                    browser.close()

    def _check_viewport(self, browser, width: int, height: int, mobile: bool, screenshot: Path) -> None:
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
            is_mobile=mobile,
            has_touch=mobile,
            reduced_motion="reduce",
        )
        page = context.new_page()
        errors: list[str] = []
        external_requests: list[str] = []
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: external_requests.append(request.url) if (
            request.url.startswith(("http://", "https://"))
            and not request.url.startswith(f"http://{HOST}:{self.port}/")
        ) else None)
        page.goto(f"http://{HOST}:{self.port}/", wait_until="domcontentloaded")
        page.locator("#chat").wait_for(state="visible")
        page.wait_for_timeout(500)
        self.assertEqual("#16d9c4", page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--t95-phosphor-cyan').trim()"
        ))
        self.assertEqual("none", page.locator("#particleBg").evaluate("element => getComputedStyle(element).display"))
        self.assertEqual("rgb(216, 201, 155)", page.locator(".tab-bar").evaluate(
            "element => getComputedStyle(element).backgroundColor"
        ))
        self.assertEqual("none", page.locator(".tab-bar").evaluate(
            "element => getComputedStyle(element).boxShadow"
        ))
        self.assertEqual("none", page.locator(".input-pill").evaluate(
            "element => getComputedStyle(element).boxShadow"
        ))
        input_rule_width = float(page.locator(".input-pill").evaluate(
            "element => getComputedStyle(element).borderBottomWidth"
        ).removesuffix("px"))
        self.assertGreater(input_rule_width, 0)
        self.assertLessEqual(input_rule_width, 1)
        decorative_shadows = page.locator("body *").evaluate_all("""
            elements => elements
                .filter(element => {
                    const style = getComputedStyle(element);
                    return style.boxShadow !== 'none' || style.textShadow !== 'none';
                })
                .map(element => ({
                    element: element.tagName.toLowerCase() + (element.id ? '#' + element.id : ''),
                    boxShadow: getComputedStyle(element).boxShadow,
                    textShadow: getComputedStyle(element).textShadow,
                }))
        """)
        self.assertEqual([], decorative_shadows)
        self.assertEqual(5, page.locator(".custom-tab[data-bs-toggle='tab']").count())
        self.assertEqual(5, page.locator(".custom-tab[data-bs-toggle='tab'] .t95-icon").count())
        icon_size = page.locator("#chat-tab .t95-icon").evaluate(
            "element => getComputedStyle(element, '::before').width"
        )
        self.assertAlmostEqual(24.0, float(icon_size.removesuffix("px")), delta=0.1)
        self.assertTrue(page.locator("#previewConsole").is_visible())
        if mobile:
            self.assertTrue(page.locator("#mobileNav").is_visible())
        else:
            page.locator("[data-preview-value='thinking']").click()
            page.wait_for_function("document.body.dataset.previewState === 'thinking'")
            self.assertEqual("PROCESSING", page.locator("#previewReadoutState").inner_text())
            page.locator("[data-preview-value='talking']").click()
            page.locator("#previewAlert").select_option("warning")
            page.locator("#previewConnectivity").select_option("offline")
            page.wait_for_function("document.body.dataset.previewState === 'warning'")
            self.assertEqual("WARNING", page.locator("#previewReadoutState").inner_text())
            self.assertEqual("WARNING", page.locator("#previewReadoutAlert").inner_text())
            self.assertIn("disconnected", page.locator("#connDot").get_attribute("class"))
        page.screenshot(path=screenshot, animations="disabled", scale="css")
        context.close()
        self.assertEqual([], errors)
        self.assertEqual([], external_requests)
        with Image.open(screenshot) as image:
            self.assertEqual((width, height), image.size)


class BaselineIntegrityTests(unittest.TestCase):
    def test_ui012_shell_proof_dimensions_and_hash(self) -> None:
        manifest = json.loads((PROOF_ROOT / "manifest.json").read_text(encoding="utf-8"))
        proof_path = PROOF_ROOT / manifest["file"]
        self.assertEqual("UI-012", manifest["action"])
        self.assertEqual([480, 320], manifest["dimensions"])
        with Image.open(proof_path) as image:
            self.assertEqual((480, 320), image.size)
        self.assertEqual(
            manifest["sha256"], hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        )

    def test_manifest_files_dimensions_and_hashes(self) -> None:
        manifest = json.loads((BASELINE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("UI-005", manifest["baseline"])
        self.assertEqual(4, len(manifest["files"]))
        for entry in manifest["files"]:
            with self.subTest(file=entry["file"]):
                path = BASELINE_ROOT / entry["file"]
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    self.assertEqual((entry["width"], entry["height"]), image.size)
                self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main(verbosity=2)
