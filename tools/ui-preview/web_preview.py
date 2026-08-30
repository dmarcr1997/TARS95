"""Safe desktop server for previewing the production TARS web interface.

This module intentionally does not import the robot application or its config.
It serves the real Jinja templates/static assets with deterministic fixtures and
turns every write/hardware route into a successful no-op.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Any

import qrcode
from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_socketio import SocketIO, emit

from preview_state import PreviewStateStore


REPO_ROOT = Path(__file__).resolve().parents[2]
WWW_ROOT = REPO_ROOT / "src" / "www"
CHARACTER_ROOT = REPO_ROOT / "src" / "character"
PREVIEW_WEB_ROOT = Path(__file__).resolve().parent / "web"
HOST = "127.0.0.1"
DEFAULT_PORT = 5095
BOOT_ID = "tars95-desktop-preview"

MOVEMENTS = [
    {"id": "wave", "name": "Wave"},
    {"id": "look_left", "name": "Look Left"},
    {"id": "look_right", "name": "Look Right"},
    {"id": "neutral", "name": "Return to Neutral"},
]

CONFIG_FIXTURE = {
    "CHAR": {"character": "TARS", "user_name": "Operator"},
    "LLM": {"llm_backend": "preview", "llm_model": "OFFLINE_FIXTURE"},
    "STT": {"stt_engine": "preview", "wake_word": "tars"},
    "TTS": {"tts_engine": "preview", "voice": "SYSTEM_95"},
    "UI": {"screen_size": "480x320", "startup_app": "clock"},
    "ACCESS": {"webui_port": DEFAULT_PORT, "webui_theme": "default", "webui_auth": False},
    "CONTROLS": {"movement_enabled": False, "arms_enabled": False},
    "BATTERY": {"battery_monitoring": False, "low_battery_threshold": 20},
}

FIELD_OPTIONS = {
    "CHAR.character": {"type": "select", "options": ["TARS", "CASE", "KIPP", "Bishop", "PLEX"]},
    "LLM.llm_backend": {"type": "select", "options": ["preview"]},
    "UI.screen_size": {"type": "select", "options": ["480x320", "800x480"]},
    "UI.startup_app": {"type": "select", "options": ["clock", "eyes", "avatar", "remote", "audio"]},
    "ACCESS.webui_theme": {"type": "select", "options": ["default", "amber", "emerald", "red"]},
    "ACCESS.webui_auth": {"type": "boolean"},
    "CONTROLS.movement_enabled": {"type": "boolean"},
    "CONTROLS.arms_enabled": {"type": "boolean"},
    "BATTERY.battery_monitoring": {"type": "boolean"},
}

CHARACTER_FIXTURE = {
    "char_name": "TARS",
    "description": "Desktop fixture for the TARS95 interface preview.",
    "personality": "Direct, dry, reliable, and suspiciously fond of beige computers.",
    "scenario": "A robot operating system from a timeline where Windows 95 never retired.",
    "char_persona": "Mission companion and systems operator.",
    "world_scenario": "Local development mode; no robot hardware is connected.",
    "first_mes": "DESKTOP PREVIEW ONLINE.",
    "mes_example": "Operator: Status?\nTARS: All simulated systems nominal.",
}

TRAIT_FIXTURE = {
    "verbosity": 38,
    "humor": 72,
    "sarcasm": 64,
    "honesty": 90,
    "empathy": 58,
    "curiosity": 66,
    "confidence": 82,
    "formality": 48,
    "adaptability": 74,
    "discipline": 86,
    "imagination": 55,
    "emotional_stability": 88,
    "pragmatism": 91,
    "optimism": 61,
    "resourcefulness": 89,
    "cheerfulness": 49,
    "engagement": 70,
    "respectfulness": 76,
}

LOG_LINES = [
    {"id": 1, "timestamp": "1995-08-24 09:00:00", "level": "INFO", "message": "TARS95 desktop preview booted"},
    {"id": 2, "timestamp": "1995-08-24 09:00:01", "level": "INFO", "message": "Robot I/O replaced with safe fixtures"},
    {"id": 3, "timestamp": "1995-08-24 09:00:02", "level": "READY", "message": "Production web assets available on localhost"},
]

INTERACTIONS = [
    {
        "id": "preview-2",
        "ts": "1995-08-24T09:02:00",
        "user": "Run diagnostics.",
        "bot": "All simulated systems nominal.",
        "emotion": "confidence",
        "emotion_raw": "confidence:0.82",
        "speaker": "Operator",
        "has_prompt": True,
    },
    {
        "id": "preview-1",
        "ts": "1995-08-24T09:01:00",
        "user": "Are we connected to the robot?",
        "bot": "Negative. Desktop preview mode is fail-closed.",
        "emotion": "pragmatism",
        "emotion_raw": "pragmatism:0.91",
        "speaker": "Operator",
        "has_prompt": True,
    },
]


def _noop_payload(action: str | None = None) -> dict[str, Any]:
    label = action or request.endpoint or "action"
    return {
        "success": True,
        "preview": True,
        "hardware_access": False,
        "message": f"Preview mode: {label} acknowledged; no robot action was performed.",
    }


def create_app(theme: str = "default", port: int = DEFAULT_PORT) -> tuple[Flask, SocketIO]:
    app = Flask(
        __name__,
        template_folder=str(WWW_ROOT / "templates"),
        static_folder=str(WWW_ROOT / "static"),
        static_url_path="/static",
    )
    app.config.update(
        SECRET_KEY="tars95-preview-not-for-production",
        PREVIEW_THEME=theme,
        PREVIEW_PORT=port,
        JSON_SORT_KEYS=False,
    )
    socketio = SocketIO(app, async_mode="threading", logger=False, engineio_logger=False)
    preview_state = PreviewStateStore()

    @app.get("/")
    def index() -> str:
        page = render_template(
            "index.html",
            char_name="TARS95",
            char_greeting="DESKTOP PREVIEW ONLINE",
            talkinghead_base_url=HOST,
            port=app.config["PREVIEW_PORT"],
            user_name="Operator",
            webui_theme=app.config["PREVIEW_THEME"],
        )
        controls = (PREVIEW_WEB_ROOT / "preview_controls.html").read_text(encoding="utf-8")
        return page.replace("</body>", f"{controls}\n</body>")

    @app.get("/preview-assets/<path:filename>")
    def preview_assets(filename: str) -> Response:
        return send_from_directory(PREVIEW_WEB_ROOT, filename)

    @app.route("/api/preview/state", methods=["GET", "POST"])
    def preview_state_api() -> tuple[Response, int] | Response:
        if request.method == "POST":
            try:
                state = preview_state.update(**(request.get_json(silent=True) or {}))
            except (TypeError, ValueError) as exc:
                return jsonify(success=False, error=str(exc)), 400
            payload = preview_state.as_dict()
            socketio.emit("preview_state", payload)
            socketio.emit("talking_state", {"talking": state.machine_state == "talking", "preview": True})
        return jsonify(success=True, state=preview_state.as_dict(), preview=True)

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Response | str:
        if request.method == "POST":
            return redirect(url_for("index"))
        return render_template("login.html", char_name="TARS95", webui_theme=app.config["PREVIEW_THEME"])

    @app.get("/logout")
    def logout() -> Response:
        return redirect(url_for("index"))

    @app.get("/holo")
    def holo() -> str:
        return render_template("holo.html")

    @app.get("/get_ip")
    def get_ip() -> Response:
        return jsonify(talkinghead_base_url=HOST)

    @app.get("/avatar_sprites")
    def avatar_sprites() -> Response:
        base = "/character_sprite/neutral/animation/"
        return jsonify(
            nottalking_open=base + "TARS_neutral_nottalking_eyes_open.png",
            nottalking_closed=base + "TARS_neutral_nottalking_eyes_closed.png",
            talking_open=base + "TARS_neutral_talking_eyes_open.png",
            talking_closed=base + "TARS_neutral_talking_eyes_closed.png",
        )

    @app.get("/character_sprite/<emotion>/animation/<path:filename>")
    def character_sprite(emotion: str, filename: str) -> Response:
        sprite_dir = CHARACTER_ROOT / "TARS" / "images" / emotion / "animation"
        return send_from_directory(sprite_dir, filename)

    @app.get("/camera_feed")
    def camera_feed() -> Response:
        svg = """<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>
        <rect width='100%' height='100%' fill='#050a0d'/><path d='M0 180H640M320 0V360' stroke='#16d9c4' opacity='.25'/>
        <text x='320' y='170' text-anchor='middle' fill='#16d9c4' font-family='monospace' font-size='22'>CAMERA OFFLINE</text>
        <text x='320' y='205' text-anchor='middle' fill='#87999a' font-family='monospace' font-size='13'>DESKTOP PREVIEW // NO DEVICE</text></svg>"""
        return Response(svg, mimetype="image/svg+xml")

    @app.get("/audio_stream")
    @app.get("/get_next_audio_chunk")
    def empty_audio() -> Response:
        return Response(status=204)

    @app.get("/boot_id")
    def boot_id() -> Response:
        return jsonify(boot_id=BOOT_ID)

    @app.get("/config_sync_status")
    def config_sync_status() -> Response:
        return jsonify(synced=True, preview=True)

    @app.get("/api/wifi/status")
    def wifi_status() -> Response:
        connectivity = preview_state.snapshot().connectivity
        if connectivity == "offline":
            return jsonify(mode="disconnected", ssid=None, ip=None, preview=True)
        return jsonify(
            mode="client",
            ssid="TARS95_DESKTOP" if connectivity == "online" else "TARS95_WEAK_LINK",
            ip=HOST,
            signal=100 if connectivity == "online" else 32,
            preview=True,
        )

    @app.get("/api/wifi/networks")
    def wifi_networks() -> Response:
        return jsonify(networks=[
            {"ssid": "TARS95_DESKTOP", "signal": 100, "security": "fixture", "in_use": True},
            {"ssid": "NERV_GUEST", "signal": 72, "security": "WPA2", "in_use": False},
        ])

    @app.get("/api/tunnel/status")
    def tunnel_status() -> Response:
        return jsonify(active=False, status="offline", url=None, preview=True)

    @app.get("/api/tunnel/qr")
    def tunnel_qr() -> Response:
        image = qrcode.make(f"http://{HOST}:{app.config['PREVIEW_PORT']}/?preview=tars95")
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        return Response(stream.getvalue(), mimetype="image/png")

    @app.get("/api/system/metrics")
    def system_metrics() -> Response:
        state = preview_state.snapshot()
        return jsonify(
            cpu_load=19.95,
            ram_usage=42.0,
            ram_total_mb=640,
            cpu_temp=35.0,
            uptime_secs=1995,
            emotion=state.machine_state,
            battery=state.battery,
            character="TARS95",
            alert=state.alert,
            connectivity=state.connectivity,
            preview=True,
        )

    @app.get("/api/memory/stats")
    def memory_stats() -> Response:
        return jsonify(total=128, short_term=16, long_term=112, preview=True)

    @app.get("/api/console/logs")
    def console_logs() -> Response:
        since = request.args.get("since", default=0, type=int)
        lines = [line for line in LOG_LINES if line["id"] > since]
        return jsonify(lines=lines, head=LOG_LINES[-1]["id"])

    @app.get("/api/characters")
    def characters() -> Response:
        return jsonify(characters=["TARS", "CASE", "KIPP", "Bishop", "PLEX"])

    @app.get("/api/character/<name>")
    def character(name: str) -> Response:
        character_data = dict(CHARACTER_FIXTURE, char_name=name)
        return jsonify(character=character_data, traits=TRAIT_FIXTURE)

    @app.get("/get_config")
    def get_config() -> Response:
        config = {section: dict(values) for section, values in CONFIG_FIXTURE.items()}
        config["ACCESS"]["webui_theme"] = app.config["PREVIEW_THEME"]
        config["ACCESS"]["webui_port"] = app.config["PREVIEW_PORT"]
        field_options = {key: dict(value) for key, value in FIELD_OPTIONS.items()}
        field_options["ACCESS.webui_theme"]["options"] = available_themes()
        return jsonify(config=config, field_options=field_options, preview=True)

    @app.get("/get_skills")
    def get_skills() -> Response:
        return jsonify(skills=[
            {"name": "desktop_fixture", "display_name": "Desktop Fixture", "description": "Deterministic local responses", "enabled": True, "config": {}},
            {"name": "robot_hardware", "display_name": "Robot Hardware", "description": "Locked out in preview mode", "enabled": False, "config": {}},
        ])

    @app.get("/get_movements")
    def get_movements() -> Response:
        return jsonify(
            success=True,
            legs_only=MOVEMENTS[1:],
            has_arms=MOVEMENTS[:1],
            movements=MOVEMENTS,
        )

    @app.get("/get_arms_status")
    def get_arms_status() -> Response:
        return jsonify(arms_present=True, preview=True)

    @app.get("/get_saved_sequences")
    def get_saved_sequences() -> Response:
        return jsonify({
            "STARTUP_CHECK": {
                "type": "full_body",
                "quick": False,
                "steps": [{"movement": "look_left", "duration": 0.5}, {"movement": "neutral", "duration": 0.5}],
            }
        })

    @app.get("/get_movement_steps/<name>")
    def get_movement_steps(name: str) -> Response:
        return jsonify(success=True, name=name, steps=[{"movement": name, "duration": 0.5}], preview=True)

    @app.get("/api/dashboard/stats")
    def dashboard_stats() -> Response:
        return jsonify(memories=128, topics=9, interactions=42, current_emotion="pragmatism", emotion_enabled=True)

    @app.get("/api/dashboard/graph")
    def dashboard_graph() -> Response:
        nodes = [
            {"id": "brain", "name": "TARS95", "group": "brain", "size": 28, "color": "rgb(22,217,196)"},
            {"id": "person-operator", "name": "Operator", "group": "person", "size": 18, "color": "rgb(255,180,32)"},
            {"id": "topic-preview", "name": "Desktop Preview", "group": "topic", "size": 14, "color": "rgb(233,81,106)"},
            {"id": "memory-safe", "name": "Hardware lockout", "group": "memory", "size": 9, "color": "rgb(145,174,178)", "details": {"context": "No hardware imports are loaded"}},
        ]
        links = [
            {"source": "brain", "target": "person-operator"},
            {"source": "brain", "target": "topic-preview"},
            {"source": "topic-preview", "target": "memory-safe"},
        ]
        return jsonify(nodes=nodes, links=links, total_memories=1)

    @app.get("/api/dashboard/mood")
    def dashboard_mood() -> Response:
        return jsonify(
            emotional_state={"confidence": 82, "curiosity": 66, "pragmatism": 91, "humor": 72, "empathy": 58},
            timeline=[
                {"ts": "1995-08-24T08:00:00", "emotion": "curiosity", "value": 55},
                {"ts": "1995-08-24T09:00:00", "emotion": "confidence", "value": 82},
            ],
            activity_heatmap={"1995-08-24": 6},
        )

    @app.get("/api/dashboard/interactions")
    def dashboard_interactions() -> Response:
        return jsonify(interactions=INTERACTIONS)

    @app.get("/api/dashboard/topics")
    def dashboard_topics() -> Response:
        return jsonify(topics=[
            {"id": "topic-preview", "name": "Desktop Preview", "summary": "Fast, safe UI iteration", "memory_count": 8},
            {"id": "topic-aesthetic", "name": "TARS95 Aesthetic", "summary": "Windows 95 robot interface", "memory_count": 5},
        ])

    @app.get("/api/dashboard/prompt")
    def dashboard_prompt() -> Response:
        entry_id = request.args.get("id")
        if entry_id:
            return jsonify(id=entry_id, prompt="[DESKTOP PREVIEW FIXTURE]", llm_raw="No model was called.")
        return jsonify(interactions=INTERACTIONS)

    @app.post("/process_llm")
    def process_llm() -> Response:
        message = (request.form.get("message") or "").strip()
        response_text = (
            f"PREVIEW ACKNOWLEDGED: {message}" if message else "PREVIEW ACKNOWLEDGED."
        ) + " No model or robot hardware was called."

        def emit_preview_response() -> None:
            # The production client adds its typing bubble after one second.
            # Reply just after that so the same client lifecycle is exercised.
            socketio.sleep(1.05)
            socketio.emit("bot_stream_start", {})
            for token in ("PREVIEW ACKNOWLEDGED. ", "LOCAL FIXTURE ACTIVE. ", "HARDWARE LOCKOUT CONFIRMED."):
                socketio.emit("bot_token", {"text": token})
            socketio.emit("bot_message", {"message": response_text, "audio_streamed": True, "preview": True})

        socketio.start_background_task(emit_preview_response)
        return jsonify(success=True, response=response_text, preview=True, hardware_access=False)

    @app.route("/upload", methods=["GET", "POST"])
    def upload() -> Response:
        return jsonify(_noop_payload("upload"))

    def noop() -> Response:
        return jsonify(_noop_payload())

    no_op_routes = [
        ("/start_talking", ["POST", "GET"]),
        ("/stop_talking", ["POST", "GET"]),
        ("/emotion", ["POST"]),
        ("/robot_move", ["POST"]),
        ("/execute_action", ["POST"]),
        ("/move_legs", ["POST"]),
        ("/disable_servos", ["POST"]),
        ("/reset_positions", ["POST"]),
        ("/neutral_legs", ["POST"]),
        ("/move_arms", ["POST"]),
        ("/save_config", ["POST"]),
        ("/toggle_skill", ["POST"]),
        ("/save_skill_config", ["POST"]),
        ("/reboot_program", ["POST"]),
        ("/api/wifi/connect", ["POST"]),
        ("/api/wifi/hotspot", ["PUT"]),
        ("/api/tunnel/start", ["POST"]),
        ("/api/tunnel/stop", ["POST"]),
        ("/api/eyes/mood", ["POST"]),
        ("/api/character/<name>/save", ["POST"]),
        ("/api/dashboard/memory/delete", ["POST"]),
        ("/api/dashboard/memory/edit", ["POST"]),
        ("/api/dashboard/topic/edit", ["POST"]),
        ("/api/dashboard/topic/delete", ["POST"]),
        ("/api/dashboard/person/rename", ["POST"]),
        ("/api/dashboard/person/delete", ["POST"]),
        ("/play_sequence", ["POST"]),
        ("/save_sequence", ["POST"]),
        ("/delete_saved_sequence", ["POST"]),
        ("/play_saved_sequence", ["POST"]),
    ]
    for index_number, (route, methods) in enumerate(no_op_routes):
        app.add_url_rule(route, f"preview_noop_{index_number}", noop, methods=methods)

    @socketio.on("connect")
    def socket_connect() -> None:
        state = preview_state.snapshot()
        emit("talking_state", {"talking": state.machine_state == "talking", "preview": True})
        emit("preview_state", preview_state.as_dict())

    @socketio.on("client_debug")
    def client_debug(_payload: Any = None) -> None:
        return None

    @socketio.on("browser_audio")
    def browser_audio(_payload: Any = None) -> None:
        emit("browser_transcription", {"text": "", "preview": True})

    @socketio.on("show_qr")
    def show_qr(_payload: Any = None) -> None:
        emit("qr_status", {"success": True, "preview": True})

    return app, socketio


def run_checks(app: Flask, socketio: SocketIO) -> None:
    client = app.test_client()
    get_routes = [
        "/", "/static/css/main.css", "/static/js/main.js", "/get_ip", "/avatar_sprites",
        "/character_sprite/neutral/animation/TARS_neutral_nottalking_eyes_open.png",
        "/api/wifi/status", "/api/system/metrics", "/api/console/logs", "/get_config",
        "/get_skills", "/get_movements", "/get_arms_status", "/get_saved_sequences",
        "/api/dashboard/stats", "/api/dashboard/graph", "/api/dashboard/mood",
        "/api/dashboard/interactions", "/api/dashboard/topics", "/api/dashboard/prompt",
        "/api/preview/state", "/preview-assets/preview_controls.css", "/preview-assets/preview_controls.js",
    ]
    for route in get_routes:
        response = client.get(route)
        try:
            if response.status_code != 200:
                raise RuntimeError(f"GET {route} returned {response.status_code}")
        finally:
            response.close()

    page_response = client.get("/")
    page = page_response.get_data(as_text=True)
    page_response.close()
    for marker in (
        "id=\"chat-tab\"", "id=\"motion-tab\"", "id=\"dashboard-tab\"",
        "/static/js/main.js", "id=\"previewConsole\"",
    ):
        if marker not in page:
            raise RuntimeError(f"Rendered index is missing {marker}")

    response = client.post("/robot_move", json={"movement": "wave"})
    robot_status = response.status_code
    robot_data = response.get_json()
    response.close()
    if robot_status != 200 or robot_data.get("hardware_access") is not False:
        raise RuntimeError("Robot no-op contract failed")

    movement_response = client.get("/get_movements")
    movement_data = movement_response.get_json()
    movement_response.close()
    if not movement_data["legs_only"] or not movement_data["has_arms"] or not movement_data["movements"]:
        raise RuntimeError("Movement fixture groups are empty")

    state_response = client.post("/api/preview/state", json={
        "machine_state": "talking", "battery": 15, "alert": "warning", "connectivity": "offline",
    })
    state_status = state_response.status_code
    state_response.close()
    if state_status != 200:
        raise RuntimeError("Preview state update was rejected")
    metrics_response = client.get("/api/system/metrics")
    metrics = metrics_response.get_json()
    metrics_response.close()
    wifi_response = client.get("/api/wifi/status")
    wifi = wifi_response.get_json()
    wifi_response.close()
    if metrics["battery"] != 15 or metrics["alert"] != "warning" or wifi["mode"] != "disconnected":
        raise RuntimeError("Preview state did not reach production-shaped fixtures")
    invalid_response = client.post("/api/preview/state", json={"battery": 101})
    invalid_status = invalid_response.status_code
    invalid_response.close()
    if invalid_status != 400:
        raise RuntimeError("Invalid preview state was accepted")

    socket_client = socketio.test_client(app)
    if not socket_client.is_connected():
        raise RuntimeError("Socket.IO preview connection failed")
    socket_events = socket_client.get_received()
    chat_response = client.post("/process_llm", data={"message": "status"})
    chat_status = chat_response.status_code
    chat_response.close()
    socketio.sleep(1.2)
    chat_events = socket_client.get_received()
    socket_client.disconnect()
    if not any(event["name"] == "talking_state" for event in socket_events):
        raise RuntimeError("Socket.IO preview fixture was not emitted")
    if chat_status != 200 or not any(event["name"] == "bot_message" for event in chat_events):
        raise RuntimeError("Deterministic chat fixture was not emitted")

    robot_modules = [name for name in sys.modules if name == "modules" or name.startswith("modules.")]
    if robot_modules:
        raise RuntimeError(f"Robot runtime modules were imported: {robot_modules}")

    print(
        f"PASS: {len(get_routes)} routes, state controls, deterministic chat, "
        "write no-op, Socket.IO, and robot-import lockout"
    )


def available_themes() -> list[str]:
    return sorted(path.stem for path in (WWW_ROOT / "static" / "css" / "themes").glob("*.css"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the production TARS web UI with safe desktop fixtures.")
    parser.add_argument("--host", default=HOST, choices=[HOST], help="Preview is intentionally localhost-only.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--theme", default="default", choices=available_themes())
    parser.add_argument("--check", action="store_true", help="Run contract checks and exit without opening a server.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app, socketio = create_app(args.theme, args.port)
    if args.check:
        run_checks(app, socketio)
        return 0

    print(f"TARS95 web preview: http://{args.host}:{args.port}")
    print("Preview safety: localhost only; robot writes are no-ops; Ctrl+C stops the server.")
    socketio.run(app, host=args.host, port=args.port, debug=False, allow_unsafe_werkzeug=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
