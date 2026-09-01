"""Canonical TARS/95 machine-state presentation rules.

This module is intentionally independent of pygame so the state contract can be
tested without initializing a display or importing robot hardware modules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatePresentation:
    """Copy, color, shape, and motion assigned to one visible machine state."""

    key: str
    label: str
    color: tuple[int, int, int]
    shape: str
    motion: str
    cue: str


STATE_PRESENTATIONS = {
    "BOOTING": StatePresentation(
        "BOOTING", "BOOTING", (47, 119, 208), "stepped-bar", "stepped-progress", "SELF TEST",
    ),
    "STANDBY": StatePresentation(
        "STANDBY", "STANDBY", (120, 144, 156), "square", "ambient-only", "READY",
    ),
    "LISTENING": StatePresentation(
        "LISTENING", "LISTENING", (22, 217, 196), "open-bracket", "input-driven", "MIC LIVE",
    ),
    "THINKING": StatePresentation(
        "THINKING", "PROCESSING", (255, 176, 0), "scan-line", "stepped-scan", "WORKING",
    ),
    "TALKING": StatePresentation(
        "TALKING", "TALKING", (56, 232, 120), "double-bar", "output-driven", "VOICE LIVE",
    ),
    "WARNING": StatePresentation(
        "WARNING", "WARNING", (255, 176, 0), "triangle", "slow-pulse", "CHECK STATUS",
    ),
    "FAULT": StatePresentation(
        "FAULT", "FAULT", (240, 68, 54), "cross", "acknowledgement-only", "SERVICE REQUIRED",
    ),
    "OFFLINE": StatePresentation(
        "OFFLINE", "OFFLINE", (111, 119, 122), "broken-link", "none", "LINK LOST",
    ),
}

STATE_COLORS = {
    key: presentation.color for key, presentation in STATE_PRESENTATIONS.items()
}
STATE_COLORS["PROCESSING"] = STATE_PRESENTATIONS["THINKING"].color
STATE_LABELS = {"THINKING": "PROCESSING"}


def resolve_presentation(
    machine_state: str,
    alert: str = "none",
    connectivity: str = "online",
) -> StatePresentation:
    """Resolve the state shown to the operator using safety-first priority.

    Faults override warnings, warnings/advisories override a lost link, and a
    lost link overrides the nominal machine activity. Unknown values fail safe
    to OFFLINE rather than inventing a healthy state.
    """

    alert_key = str(alert).strip().upper()
    connectivity_key = str(connectivity).strip().upper()
    machine_key = str(machine_state).strip().upper()

    if alert_key == "FAULT":
        return STATE_PRESENTATIONS["FAULT"]
    if alert_key in {"WARNING", "ADVISORY"}:
        return STATE_PRESENTATIONS["WARNING"]
    if connectivity_key == "OFFLINE":
        return STATE_PRESENTATIONS["OFFLINE"]
    return STATE_PRESENTATIONS.get(machine_key, STATE_PRESENTATIONS["OFFLINE"])
