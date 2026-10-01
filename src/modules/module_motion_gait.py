"""Experimental timed forward gait for the device Motion screen only.

No hardware imports at module load. Targets are relative to configured neutral
and travel endpoints, not hard-coded pulse offsets. This is an open-loop gait:
phase names describe intended support, not measured balance or foot contact.
Validate short steps with the robot supported before using it unassisted.
"""
from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class Phase:
    name: str
    target: tuple
    seconds: float


def verify_outputs(servo):
    """Read PWM registers; verifies controller state, not servo power/position."""
    for channel in range(4):
        expected = servo.pulse_to_duty_cycle(servo.servo_positions[channel])
        actual = servo.pca.channels[channel].duty_cycle
        # PCA9685 has 12-bit resolution; the library exposes 16-bit values.
        if actual >> 4 != expected >> 4:
            raise RuntimeError(f"PWM READBACK FAILED CH {channel}")
    print("[MOTION] Leg PWM registers verified; servo power/position not measured", flush=True)


def forward_phases(servo):
    """One small left/right cycle, with explicit planting/settling phases."""
    neutral = (servo.leftNeutralHeight, servo.rightNeutralHeight,
               servo.neutralLeftLeg, servo.neutralRightLeg)
    up = (servo.leftUpHeight, servo.rightUpHeight)
    down = (servo.leftDownHeight, servo.rightDownHeight)
    forward = (servo.forwardLeftLeg, servo.forwardRightLeg)
    backward = (servo.backLeftLeg, servo.backRightLeg)
    def toward(start, end, fraction):
        return round(start + (end - start) * fraction)
    # First Pi trial produced no useful movement; increase clearance. Use 16% of
    # directional travel for stride, 30% for weight transfer, and 45% for
    # unloaded-leg lift. These are fractions of neutral-to-endpoint travel,
    # not fractions of the entire servo range. Mirrored servo axes use
    # their own calibrated endpoints rather than assumed pulse directions.
    extend = [toward(neutral[i], down[i], .30) for i in range(2)]
    unload = [toward(neutral[i], up[i], .20) for i in range(2)]
    lift = [toward(neutral[i], up[i], .45) for i in range(2)]
    ahead = [toward(neutral[i + 2], forward[i], .16) for i in range(2)]
    behind = [toward(neutral[i + 2], backward[i], .16) for i in range(2)]
    lh, rh, ll, rl = neutral
    return (
        Phase("STAND", neutral, 1.0),
        Phase("SHIFT LEFT", (extend[0], unload[1], ll, rl), 1.2),
        Phase("LIFT RIGHT", (extend[0], lift[1], ll, rl), .8),
        Phase("STEP RIGHT", (extend[0], lift[1], behind[0], ahead[1]), 1.0),
        Phase("PLANT RIGHT", (lh, rh, behind[0], ahead[1]), 1.2),
        Phase("SETTLE RIGHT", (lh, rh, behind[0], ahead[1]), .25),
        Phase("SHIFT RIGHT", (unload[0], extend[1], behind[0], ahead[1]), 1.2),
        Phase("LIFT LEFT", (lift[0], extend[1], behind[0], ahead[1]), .8),
        Phase("STEP LEFT", (lift[0], extend[1], ahead[0], behind[1]), 1.0),
        Phase("PLANT LEFT", (lh, rh, ahead[0], behind[1]), 1.2),
        Phase("SETTLE LEFT", (lh, rh, ahead[0], behind[1]), .25),
        Phase("CENTER", neutral, 1.0),
        Phase("SETTLE", neutral, .25),
    )


def run_forward(servo, on_phase=lambda name: None, *, clock=time.monotonic, sleep=time.sleep):
    """Execute at 50 Hz with quintic easing, checked writes, and cancellation.

    PWM remains enabled at the final standing pose; explicit STOP / SERVOS OFF
    still removes output. Failed writes abort and latch output off. No hardware
    recovery or automatic retry of a whole gait is attempted.
    """
    if servo.MOVING:
        raise RuntimeError("MOTION ALREADY ACTIVE")
    if servo.emergency_stop_requested():
        raise RuntimeError("STOP LATCHED")
    phases = forward_phases(servo)
    positions = [servo.servo_positions.get(i, phases[0].target[i]) for i in range(4)]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 600
           for phase in phases for v in phase.target):
        raise ValueError("INVALID GAIT CALIBRATION")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 600 for v in positions):
        raise ValueError("INVALID START POSITION")
    servo.MOVING = True
    sent = {}  # PWM remains active; don't resend identical pulses every frame.
    try:
        servo.signal_servo_activity()
        for phase in phases:
            if servo.emergency_stop_requested():
                return False
            on_phase(phase.name)
            print(f"[MOTION] {phase.name}: target PWM {phase.target}, duration {phase.seconds:.2f}s", flush=True)
            start = list(positions)
            started = clock()
            while True:
                if servo.emergency_stop_requested():
                    return False
                elapsed = clock() - started
                progress = min(1.0, max(0.0, elapsed / phase.seconds))
                if phase.seconds - elapsed <= 1e-6:
                    progress = 1.0
                # Zero velocity and acceleration at each phase boundary.
                eased = progress ** 3 * (10 - 15 * progress + 6 * progress ** 2)
                for channel in range(4):
                    if servo.emergency_stop_requested():
                        return False
                    pulse = round(start[channel] + (phase.target[channel] - start[channel]) * eased)
                    if sent.get(channel) == pulse:
                        continue
                    if not servo.set_servo_pwm(channel, pulse):
                        raise RuntimeError(f"SERVO WRITE FAILED CH {channel}")
                    sent[channel] = pulse
                    positions[channel] = pulse
                    # Keep only successfully sent positions, including on stop.
                    servo.servo_positions[channel] = pulse
                servo.signal_servo_activity()
                if progress >= 1.0:
                    break
                sleep(min(.02, max(0.0, phase.seconds - elapsed)))
        return True
    except Exception:
        servo.request_emergency_stop()
        raise
    finally:
        servo.MOVING = False
        servo._save_servo_positions()
