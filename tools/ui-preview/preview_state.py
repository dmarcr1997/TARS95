"""Shared, thread-safe state fixtures for the desktop preview tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, Iterable


MACHINE_STATES = ("standby", "listening", "thinking", "talking")
ALERT_LEVELS = ("none", "advisory", "warning", "fault")
CONNECTIVITY_STATES = ("online", "degraded", "offline")


@dataclass(frozen=True)
class PreviewState:
    machine_state: str = "standby"
    battery: int = 95
    alert: str = "none"
    connectivity: str = "online"


class PreviewStateStore:
    """Validated mutable state shared by a single preview process."""

    def __init__(self, initial: PreviewState | None = None) -> None:
        self._state = initial or PreviewState()
        self._lock = RLock()

    def snapshot(self) -> PreviewState:
        with self._lock:
            return self._state

    def as_dict(self) -> dict[str, Any]:
        return asdict(self.snapshot())

    def update(self, **changes: Any) -> PreviewState:
        with self._lock:
            current = asdict(self._state)
            current.update({key: value for key, value in changes.items() if value is not None})
            current["machine_state"] = _choice("machine_state", current["machine_state"], MACHINE_STATES)
            current["alert"] = _choice("alert", current["alert"], ALERT_LEVELS)
            current["connectivity"] = _choice("connectivity", current["connectivity"], CONNECTIVITY_STATES)
            try:
                current["battery"] = int(current["battery"])
            except (TypeError, ValueError) as exc:
                raise ValueError("battery must be an integer from 0 to 100") from exc
            if not 0 <= current["battery"] <= 100:
                raise ValueError("battery must be from 0 to 100")
            self._state = PreviewState(**current)
            return self._state

    def cycle(self, field: str, values: Iterable[Any], step: int = 1) -> PreviewState:
        options = tuple(values)
        current = getattr(self.snapshot(), field)
        return self.update(**{field: options[(options.index(current) + step) % len(options)]})


def _choice(name: str, value: Any, choices: tuple[str, ...]) -> str:
    normalized = str(value).lower()
    if normalized not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(choices)}")
    return normalized
