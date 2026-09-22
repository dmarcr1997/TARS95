"""TARS/95 safety-first locomotion controls."""

from __future__ import annotations

import threading

import pygame

from modules.UI.module_ui_state import resolve_presentation
from modules.UI.module_ui_tars95 import (
    CANVAS_BLACK,
    CAUTION_AMBER,
    CHROME_FACE,
    CHROME_HIGHLIGHT,
    CHROME_SHADOW,
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
    draw_lamp,
    draw_panel,
    draw_rule,
    draw_status_bar,
    draw_title_bar,
    load_font,
    scale_for,
    scaled,
)


class RobotMotionBackend:
    """Resolve robot motion lazily so importing the UI never probes hardware."""

    label = "LIVE / DEFERRED"

    _ACTIONS = {
        "forward": "step_forward",
        "backward": "step_backward",
        "left": "turn_left",
        "right": "turn_right",
        "neutral": "neutral_legs",
    }

    def run(self, action: str) -> None:
        from modules import module_movements as movements
        from modules import module_servoctl as servoctl

        if servoctl.pca is None:
            raise RuntimeError("SERVO CONTROLLER N/A")
        servoctl.clear_emergency_stop()
        function_name = self._ACTIONS[action]
        getattr(movements, function_name)()

    def emergency_stop(self) -> None:
        from modules import module_servoctl as servoctl

        servoctl.request_emergency_stop()


class MotionApp:
    """Single-command motion authorization with always-available stop actions."""

    ARM_HOLD_MS = 700

    def __init__(
        self,
        screen: pygame.Surface,
        width: int,
        height: int,
        *,
        motion_backend=None,
    ) -> None:
        self.output_screen = screen
        self.logical_width = width
        self.logical_height = height
        self.width = height
        self.height = width
        self.screen = pygame.Surface((self.width, self.height))

        self.motion_backend = motion_backend or RobotMotionBackend()
        self._machine_state = "STANDBY"
        self._alert = "NONE"
        self._connectivity = "N/A"
        self._preview_mode = False

        self._armed = False
        self._servos_disabled = False
        self._busy = False
        self._status = "OUTPUT LOCKED"
        self._last_action = "NONE"
        self._arm_started_ms: int | None = None
        self._worker: threading.Thread | None = None
        self._worker_error: str | None = None
        self._targets: dict[str, pygame.Rect] = {}

    def reset(self) -> None:
        self._armed = False
        self._arm_started_ms = None
        self._status = "OUTPUT LOCKED"

    def cleanup(self) -> None:
        self._armed = False
        self._arm_started_ms = None
        if self._busy:
            self._request_stop(disable=False)

    def set_preview_state(self, snapshot) -> None:
        self._preview_mode = True
        self._machine_state = str(snapshot.machine_state).upper()
        self._alert = str(snapshot.alert).upper()
        self._connectivity = str(snapshot.connectivity).upper()

    def update(self) -> None:
        if not self._preview_mode:
            try:
                from modules.module_state import get_tars_state

                self._machine_state = str(get_tars_state().value).upper()
            except Exception:
                pass

        if self._worker is not None and not self._worker.is_alive():
            self._worker = None
            self._busy = False
            if self._worker_error:
                self._status = self._worker_error
                self._worker_error = None
            elif not self._servos_disabled and not self._status.startswith("STOP"):
                self._status = "COMMAND COMPLETE // LOCKED"

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            return False
        if getattr(event, "button", 1) != 1:
            return False

        logical_x, logical_y = event.pos
        position = (self.width - 1 - logical_y, logical_x)
        target = next(
            (name for name, rect in self._targets.items() if rect.collidepoint(position)),
            None,
        )

        if event.type == pygame.MOUSEBUTTONDOWN:
            if target == "arm" and not self._busy:
                self._arm_started_ms = pygame.time.get_ticks()
                self._status = "HOLDING // KEEP PRESSURE"
                return True
            if target == "stop":
                self._request_stop(disable=False)
                return True
            if target == "disable":
                self._request_stop(disable=True)
                return True
            if target in {"forward", "backward", "left", "right", "neutral"}:
                if self._armed and not self._busy and not self._servos_disabled:
                    self._dispatch(target)
                else:
                    self._status = "LOCKED // HOLD ARM"
                return True

        if event.type == pygame.MOUSEBUTTONUP and self._arm_started_ms is not None:
            elapsed = pygame.time.get_ticks() - self._arm_started_ms
            self._arm_started_ms = None
            if target == "arm" and elapsed >= self.ARM_HOLD_MS:
                self._armed = True
                self._servos_disabled = False
                self._status = "ARMED // ONE COMMAND"
            else:
                self._armed = False
                self._status = "HOLD TO ARM // 0.7 SEC"
            return True
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
            "MOTION // LOCOMOTION",
            presentation.label,
            height=title_h,
            state_color=presentation.color,
            icon="motion",
        )
        self._draw_content(content, scale)

        authorization = "ARMED" if self._armed else "LOCKED"
        drive = "ACTIVE" if self._busy else "IDLE"
        servo_state = "OFF" if self._servos_disabled else "READY"
        draw_status_bar(
            self.screen,
            (
                ("HOME", "EYES", CHROME_FACE),
                ("AUTH", authorization, READY_GREEN if self._armed else CAUTION_AMBER),
                ("DRIVE", drive, PHOSPHOR_CYAN if self._busy else OFFLINE_GRAY),
                ("LAST", self._last_action, PAPER_TEXT),
                ("SERVO", servo_state, FAULT_RED if self._servos_disabled else READY_GREEN),
            ),
            height=status_h,
        )
        self.output_screen.blit(pygame.transform.rotate(self.screen, 90), (0, 0))

    def _draw_content(self, content: pygame.Rect, scale: float) -> None:
        margin = scaled(10, scale)
        gap = scaled(8, scale)
        top = content.top + margin
        height = content.height - margin * 2
        safety_w = scaled(151, scale)
        vector_rect = pygame.Rect(margin, top, self.width - margin * 2 - gap - safety_w, height)
        safety_rect = pygame.Rect(vector_rect.right + gap, top, safety_w, height)
        draw_panel(self.screen, vector_rect)
        draw_panel(self.screen, safety_rect)
        self._targets.clear()
        self._draw_vector_panel(vector_rect, scale)
        self._draw_safety_panel(safety_rect, scale)

    def _draw_vector_panel(self, rect: pygame.Rect, scale: float) -> None:
        draw_label(
            self.screen,
            "MOTION VECTOR // SINGLE STEP",
            (rect.left + scaled(9, scale), rect.top + scaled(8, scale)),
            size=scaled(8, scale),
            color=CAUTION_AMBER,
        )
        draw_label(
            self.screen,
            "ARM AUTHORIZATION EXPIRES AFTER ONE COMMAND",
            (rect.left + scaled(9, scale), rect.top + scaled(21, scale)),
            size=scaled(6, scale),
            color=PANEL_MUTED,
        )

        button_w = scaled(78, scale)
        button_h = scaled(48, scale)
        gap = scaled(6, scale)
        center_x = rect.centerx
        center_y = rect.top + scaled(87, scale)
        positions = {
            "forward": pygame.Rect(center_x - button_w // 2, center_y - button_h - gap, button_w, button_h),
            "left": pygame.Rect(center_x - button_w // 2 - gap - button_w, center_y, button_w, button_h),
            "stop": pygame.Rect(center_x - button_w // 2, center_y, button_w, button_h),
            "right": pygame.Rect(center_x + button_w // 2 + gap, center_y, button_w, button_h),
            "backward": pygame.Rect(center_x - button_w // 2, center_y + button_h + gap, button_w, button_h),
        }
        for action, button_rect in positions.items():
            if action == "stop":
                self._draw_control(button_rect, "STOP", "CUT OUTPUT", FAULT_RED, True, scale)
            else:
                labels = {
                    "forward": ("FORWARD", "STEP +Y"),
                    "backward": ("REVERSE", "STEP -Y"),
                    "left": ("LEFT", "TURN -X"),
                    "right": ("RIGHT", "TURN +X"),
                }
                color = PHOSPHOR_CYAN if self._armed and not self._busy else PANEL_LINE
                self._draw_control(button_rect, *labels[action], color, self._armed, scale)
            self._targets[action] = button_rect

        neutral_rect = pygame.Rect(
            rect.left + scaled(9, scale),
            rect.bottom - scaled(39, scale),
            rect.width - scaled(18, scale),
            scaled(30, scale),
        )
        neutral_color = CHROME_FACE if self._armed and not self._busy else PANEL_LINE
        self._draw_control(neutral_rect, "RETURN TO NEUTRAL", "LEGS // HOME", neutral_color, self._armed, scale)
        self._targets["neutral"] = neutral_rect

    def _draw_safety_panel(self, rect: pygame.Rect, scale: float) -> None:
        draw_label(
            self.screen,
            "OUTPUT AUTHORIZATION",
            (rect.left + scaled(9, scale), rect.top + scaled(8, scale)),
            size=scaled(7, scale),
            color=CHROME_FACE,
        )
        state_color = READY_GREEN if self._armed else FAULT_RED if self._servos_disabled else CAUTION_AMBER
        state_text = "ARMED" if self._armed else "SERVOS OFF" if self._servos_disabled else "LOCKED"
        draw_lamp(
            self.screen,
            (rect.left + scaled(12, scale), rect.top + scaled(30, scale)),
            state_color,
            size=scaled(6, scale),
        )
        draw_label(
            self.screen,
            state_text,
            (rect.left + scaled(23, scale), rect.top + scaled(23, scale)),
            size=scaled(13, scale),
            color=state_color,
            role="pixel",
        )

        arm_rect = pygame.Rect(
            rect.left + scaled(9, scale),
            rect.top + scaled(48, scale),
            rect.width - scaled(18, scale),
            scaled(48, scale),
        )
        pygame.draw.rect(self.screen, CHROME_FACE, arm_rect)
        pygame.draw.rect(self.screen, CHROME_SHADOW, arm_rect, scaled(1, scale))
        arm_label = "RELEASE TO ARM" if self._arm_started_ms is not None else "HOLD TO ARM"
        label = load_font(scaled(10, scale), "pixel").render(arm_label, True, CHROME_SHADOW)
        self.screen.blit(label, label.get_rect(centerx=arm_rect.centerx, top=arm_rect.top + scaled(9, scale)))
        draw_label(
            self.screen,
            "0.7 SEC // ONE CMD",
            (arm_rect.left + scaled(18, scale), arm_rect.top + scaled(28, scale)),
            size=scaled(7, scale),
            color=CHROME_SHADOW,
        )
        self._targets["arm"] = arm_rect

        progress_rect = pygame.Rect(
            rect.left + scaled(9, scale),
            arm_rect.bottom + scaled(6, scale),
            rect.width - scaled(18, scale),
            scaled(5, scale),
        )
        pygame.draw.rect(self.screen, PANEL_LINE, progress_rect)
        if self._arm_started_ms is not None:
            held = max(0, pygame.time.get_ticks() - self._arm_started_ms)
            progress = min(1.0, held / self.ARM_HOLD_MS)
            pygame.draw.rect(
                self.screen,
                CAUTION_AMBER,
                (progress_rect.left, progress_rect.top, int(progress_rect.width * progress), progress_rect.height),
            )

        status_y = progress_rect.bottom + scaled(8, scale)
        status_text = self._status[:27]
        draw_label(
            self.screen,
            status_text,
            (rect.left + scaled(9, scale), status_y),
            size=scaled(7, scale),
            color=PAPER_TEXT,
        )
        source = getattr(self.motion_backend, "label", "BACKEND N/A")
        draw_label(
            self.screen,
            source,
            (rect.left + scaled(9, scale), status_y + scaled(13, scale)),
            size=scaled(6, scale),
            color=PANEL_MUTED,
        )
        draw_rule(
            self.screen,
            (rect.left + scaled(9, scale), status_y + scaled(27, scale)),
            (rect.right - scaled(9, scale), status_y + scaled(27, scale)),
            PANEL_LINE,
        )

        disable_rect = pygame.Rect(
            rect.left + scaled(9, scale),
            rect.bottom - scaled(47, scale),
            rect.width - scaled(18, scale),
            scaled(38, scale),
        )
        self._draw_control(disable_rect, "SERVOS OFF", "LATCH OUTPUT SAFE", FAULT_RED, True, scale)
        self._targets["disable"] = disable_rect

    def _draw_control(
        self,
        rect: pygame.Rect,
        label: str,
        detail: str,
        color: tuple[int, int, int],
        enabled: bool,
        scale: float,
    ) -> None:
        fill = SCREEN_INK if enabled else CANVAS_BLACK
        line = color if enabled else PANEL_LINE
        pygame.draw.rect(self.screen, fill, rect)
        pygame.draw.rect(self.screen, line, rect, scaled(1, scale))
        pygame.draw.rect(self.screen, line, (rect.left, rect.top, scaled(4, scale), rect.height))
        text_color = CHROME_HIGHLIGHT if enabled else PANEL_MUTED
        title_image = load_font(scaled(9, scale), "pixel").render(label, True, text_color)
        detail_image = load_font(scaled(6, scale), "mono").render(detail, True, color if enabled else PANEL_MUTED)
        total_h = title_image.get_height() + detail_image.get_height() + scaled(2, scale)
        y = rect.centery - total_h // 2
        self.screen.blit(title_image, title_image.get_rect(centerx=rect.centerx, top=y))
        self.screen.blit(detail_image, detail_image.get_rect(centerx=rect.centerx, top=y + title_image.get_height() + scaled(2, scale)))

    def _dispatch(self, action: str) -> None:
        self._armed = False
        self._busy = True
        self._last_action = {
            "forward": "FWD",
            "backward": "REV",
            "left": "LEFT",
            "right": "RIGHT",
            "neutral": "NEUTRAL",
        }[action]
        self._status = f"EXECUTING // {self._last_action}"
        self._worker_error = None

        def run() -> None:
            try:
                self.motion_backend.run(action)
            except Exception as exc:
                message = str(exc).strip() or type(exc).__name__
                self._worker_error = message.upper()[:27]

        self._worker = threading.Thread(target=run, daemon=True, name=f"ui-motion-{action}")
        self._worker.start()

    def _request_stop(self, *, disable: bool) -> None:
        self._armed = False
        self._arm_started_ms = None
        self._servos_disabled = disable
        self._last_action = "OFF" if disable else "STOP"
        self._status = "SERVOS DISABLED // LATCHED" if disable else "STOP REQUESTED // LOCKED"

        def stop() -> None:
            try:
                self.motion_backend.emergency_stop()
            except Exception as exc:
                message = str(exc).strip() or type(exc).__name__
                self._worker_error = message.upper()[:27]

        threading.Thread(target=stop, daemon=True, name="ui-motion-stop").start()
