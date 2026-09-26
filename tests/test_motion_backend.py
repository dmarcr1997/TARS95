"""Test touch-command hardware initialization with an isolated fake driver."""

import ast
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


class MotionBackendTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'src/modules/UI/apps/module_app_motion.py'
        source = ast.parse(path.read_text(encoding='utf-8'))
        backend = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'RobotMotionBackend')
        namespace = {}
        exec(compile(ast.Module(body=[backend], type_ignores=[]), str(path), 'exec'), namespace)
        self.backend = namespace['RobotMotionBackend']()
        self.driver = ModuleType('modules.module_servoctl')
        self.driver.pca = None
        self.driver.clear_emergency_stop = Mock()
        self.driver.request_emergency_stop = Mock()
        self.driver.initialize_servos = Mock()
        self.driver.initialize_pca9685 = Mock(side_effect=self.initialize)
        self.movements = ModuleType('modules.module_movements')
        self.movements.step_forward = Mock()
        self.modules = ModuleType('modules')
        self.modules.module_servoctl = self.driver
        self.modules.module_movements = self.movements
        self.patcher = patch.dict(sys.modules, {'modules': self.modules})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def initialize(self):
        self.driver.pca = object()
        return True

    def test_touch_command_initializes_unavailable_driver_once(self):
        self.driver.initialize_pca9685.assert_not_called()
        self.backend.run('forward')
        self.backend.run('forward')
        self.driver.initialize_pca9685.assert_called_once()
        self.assertEqual(self.movements.step_forward.call_count, 2)
        self.driver.initialize_servos.assert_not_called()

    def test_existing_driver_is_reused(self):
        self.driver.pca = object()
        self.backend.run('forward')
        self.driver.initialize_pca9685.assert_not_called()
        self.movements.step_forward.assert_called_once()

    def test_failed_initialization_blocks_movement_and_can_retry(self):
        def fail():
            self.driver.pca = object()  # Frequency setup can fail after allocation.
            return False
        self.driver.initialize_pca9685.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, 'SERVO CONTROLLER N/A'):
            self.backend.run('forward')
        self.assertIsNone(self.driver.pca)
        self.driver.clear_emergency_stop.assert_not_called()
        self.movements.step_forward.assert_not_called()
        self.driver.initialize_pca9685.side_effect = self.initialize
        self.backend.run('forward')
        self.movements.step_forward.assert_called_once()

    def test_stop_does_not_initialize_hardware(self):
        self.backend.emergency_stop()
        self.driver.initialize_pca9685.assert_not_called()
        self.driver.request_emergency_stop.assert_called_once()
