"""Forward gait acceptance without importing or exercising robot hardware."""
import importlib.util
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'motion_gait_under_test', Path(__file__).resolve().parents[1] / 'src/modules/module_motion_gait.py')
gait = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gait
spec.loader.exec_module(gait)


class MotionGaitTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.writes = []
        self.saved = []
        self.stopped = False
        self.servo = SimpleNamespace(
            MOVING=False, servo_positions={0: 350, 1: 350, 2: 300, 3: 300},
            leftNeutralHeight=350, rightNeutralHeight=350,
            neutralLeftLeg=300, neutralRightLeg=300,
            leftUpHeight=220, leftDownHeight=460,
            rightUpHeight=460, rightDownHeight=220,
            forwardLeftLeg=160, backLeftLeg=460,
            forwardRightLeg=460, backRightLeg=160,
            emergency_stop_requested=lambda: self.stopped,
            request_emergency_stop=self.stop, signal_servo_activity=lambda: None,
            set_servo_pwm=self.write,
            _save_servo_positions=lambda: self.saved.append(dict(self.servo.servo_positions)),
        )

    def stop(self):
        self.stopped = True

    def write(self, channel, pulse):
        self.writes.append((self.now, channel, pulse))
        return True

    def sleep(self, seconds):
        self.now += seconds

    def run_gait(self, on_phase=lambda _: None):
        return gait.run_forward(self.servo, on_phase, clock=lambda: self.now, sleep=self.sleep)

    def test_one_timed_cycle_returns_to_standing_and_keeps_output_enabled(self):
        seen = []
        phases = gait.forward_phases(self.servo)
        self.assertTrue(self.run_gait(lambda phase: seen.append((self.now, phase))))
        self.assertEqual([name for _, name in seen], [p.name for p in phases])
        self.assertAlmostEqual(self.now, sum(p.seconds for p in phases), places=5)
        self.assertEqual(self.servo.servo_positions, {0: 350, 1: 350, 2: 300, 3: 300})
        self.assertFalse(self.servo.MOVING)
        self.assertFalse(self.stopped)
        self.assertEqual(len(self.saved), 1)
        # Small bounded stride, no large gait pulse jumps, mirrored axes.
        for channel in range(4):
            pulses = [p for _, ch, p in self.writes if ch == channel]
            self.assertLessEqual(max(abs(b - a) for a, b in zip(pulses, pulses[1:])), 2)
        self.assertGreater(phases[3].target[3], 300)
        self.assertEqual(phases[8].target[2:], (300, 300))

    def test_trailing_leg_closes_before_planting_without_grounded_swing_reset(self):
        phases = gait.forward_phases(self.servo)
        closing = next(p for p in phases if p.name == 'CLOSE LEFT')
        self.assertEqual(closing.target[2:], (300, 300))
        self.assertLess(closing.target[0], self.servo.leftNeutralHeight)
        self.assertLess(closing.target[1], self.servo.rightNeutralHeight)
        planting_index = next(i for i, p in enumerate(phases) if p.name == 'PLANT LEFT')
        self.assertTrue(all(p.target == (350, 350, 300, 300) for p in phases[planting_index:]))

    def test_stop_mid_phase_prevents_any_later_writes(self):
        def stopping_sleep(seconds):
            self.sleep(seconds)
            if self.now >= 1.3:
                self.stop()
        self.assertFalse(gait.run_forward(self.servo, clock=lambda: self.now, sleep=stopping_sleep))
        self.assertLess(self.now, 1.4)
        self.assertFalse(self.servo.MOVING)
        last_written = {ch: pulse for _, ch, pulse in self.writes}
        self.assertEqual(self.servo.servo_positions, last_written)

    def test_write_failure_aborts_and_latches_stop_without_advancing_failed_channel(self):
        def failing_write(channel, pulse):
            if self.now >= 1.2 and channel == 1:
                return False
            return self.write(channel, pulse)
        self.servo.set_servo_pwm = failing_write
        with self.assertRaisesRegex(RuntimeError, 'SERVO WRITE FAILED CH 1'):
            self.run_gait()
        self.assertTrue(self.stopped)
        self.assertFalse(self.servo.MOVING)
        self.assertEqual(self.servo.servo_positions[1], [p for _, ch, p in self.writes if ch == 1][-1])
        self.assertLess(self.now, 1.3)

    def test_busy_latched_and_invalid_calibration_never_write(self):
        self.servo.MOVING = True
        with self.assertRaisesRegex(RuntimeError, 'ALREADY ACTIVE'):
            self.run_gait()
        self.servo.MOVING = False
        self.stop()
        with self.assertRaisesRegex(RuntimeError, 'STOP LATCHED'):
            self.run_gait()
        self.stopped = False
        self.servo.leftNeutralHeight = 999
        with self.assertRaisesRegex(ValueError, 'CALIBRATION'):
            self.run_gait()
        self.assertEqual(self.writes, [])

    def test_offsets_shift_pose_without_changing_stride(self):
        initial = gait.forward_phases(self.servo)
        for field in ('leftNeutralHeight', 'leftUpHeight', 'leftDownHeight'):
            setattr(self.servo, field, getattr(self.servo, field) + 12)
        shifted = gait.forward_phases(self.servo)
        for before, after in zip(initial, shifted):
            self.assertEqual(after.target[0], before.target[0] + 12)
            self.assertEqual(after.target[1:], before.target[1:])

    def test_motion_screen_routes_forward_only_to_new_gait(self):
        path = Path(__file__).resolve().parents[1] / 'src/modules/UI/apps/module_app_motion.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        backend_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RobotMotionBackend')
        namespace = {}
        exec(compile(ast.Module(body=[backend_class], type_ignores=[]), str(path), 'exec'), namespace)
        backend = namespace['RobotMotionBackend']()
        servo = SimpleNamespace(pca=object(), MOVING=False, servo_positions={}, clear_emergency_stop=Mock())
        movements = Mock()
        root = ModuleType('modules')
        root.module_servoctl = servo
        root.module_movements = movements
        runner = Mock(return_value=True)
        verify = Mock()
        with patch.dict(sys.modules, {'modules': root, 'modules.module_motion_gait': SimpleNamespace(run_forward=runner, verify_outputs=verify)}):
            backend.run('forward')
            runner.assert_called_once()
            verify.assert_called_once_with(servo)
            movements.step_forward.assert_not_called()
            backend.run('backward')
            movements.step_backward.assert_called_once()
        self.assertIsNone(backend.phase)

    def test_two_successive_commands_complete_without_stale_busy_or_redundant_writes(self):
        self.assertTrue(self.run_gait())
        first_count = len(self.writes)
        self.assertTrue(self.run_gait())
        self.assertFalse(self.servo.MOVING)
        self.assertEqual(len(self.saved), 2)
        for channel in range(4):
            pulses = [p for _, ch, p in self.writes[:first_count] if ch == channel]
            self.assertTrue(all(a != b for a, b in zip(pulses, pulses[1:])))
        self.assertLess(first_count, 500)  # Previously ~2,200 writes per cycle.

    def test_readback_detects_silent_controller_reset(self):
        self.servo.pulse_to_duty_cycle = lambda pulse: pulse * 16
        self.servo.pca = SimpleNamespace(channels=[SimpleNamespace(duty_cycle=p * 16)
                                                  for p in self.servo.servo_positions.values()])
        gait.verify_outputs(self.servo)
        self.servo.pca.channels[2].duty_cycle = 0
        with self.assertRaisesRegex(RuntimeError, 'PWM READBACK FAILED CH 2'):
            gait.verify_outputs(self.servo)


if __name__ == '__main__':
    unittest.main()
