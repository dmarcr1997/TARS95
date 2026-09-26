"""Exercise the Pi event loop without starting its hardware services."""

import ast
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MotionEventRoutingTests(unittest.TestCase):
    def test_pi_hold_release_routes_to_motion(self):
        # Execute the actual event loop and coordinate transform in isolation;
        # importing UIManager would start unrelated robot dependencies.
        source = ast.parse((ROOT / 'src/modules/module_ui.py').read_text(encoding='utf-8'))
        manager = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'UIManager')
        transform = next(node for node in manager.body if isinstance(node, ast.FunctionDef) and node.name == '_transform_mouse_pos')
        run = next(node for node in manager.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
        loop = next(node for node in ast.walk(run) if isinstance(node, ast.For) and ast.unparse(node.iter) == 'pygame.event.get()')
        script = '''
import os, sys, threading
from types import SimpleNamespace
from unittest.mock import patch
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path[:0] = [str(ROOT / 'tools/ui-preview'), str(ROOT / 'src'), str(ROOT / 'src/modules')]
from device_preview import install_preview_stubs, HARDWARE_ATTEMPTS
from preview_state import PreviewStateStore
install_preview_stubs(PreviewStateStore())
import pygame
pygame.init()
pygame.display.set_mode((480, 320))
from modules.UI.module_ui_apps import AppManager

class Backend:
    def __init__(self): self.commands = []
    def run(self, action): self.commands.append(action)
    def emergency_stop(self): self.commands.append('stop')

exec(TRANSFORM)
for display_width, display_height in ((480, 320), (480, 800)):
    backend = Backend()
    apps = AppManager(pygame.Surface((display_height, display_width)), display_height, display_width, motion_backend=backend)
    apps.launch('motion')
    app = apps.current_app
    app.render()
    self = SimpleNamespace(show_app=True, app_manager=apps, terminal_system=None,
        _overlay_lock=threading.Lock(), _overlay_image=None,
        effective_rotate=270, logical_width=display_height, logical_height=display_width)
    self._transform_mouse_pos = lambda *args: _transform_mouse_pos(self, *args)

    def deliver(kind, position, ticks):
        event = pygame.event.Event(kind, pos=position, button=1)
        with patch.object(pygame.event, 'get', return_value=[event]), patch.object(pygame.time, 'get_ticks', return_value=ticks):
            exec(LOOP, globals())

    arm = app._targets['arm'].center
    deliver(pygame.MOUSEBUTTONDOWN, arm, 1000)
    deliver(pygame.MOUSEBUTTONUP, arm, 1100)
    assert not app._armed, 'Short taps must remain locked'
    deliver(pygame.MOUSEBUTTONDOWN, arm, 2000)
    deliver(pygame.MOUSEBUTTONUP, (0, 0), 2800)
    assert not app._armed, 'Release outside ARM must remain locked'
    deliver(pygame.MOUSEBUTTONDOWN, arm, 3000)
    deliver(pygame.MOUSEBUTTONUP, arm, 3800)
    assert app._armed, 'Pi release must complete the hold'
    assert backend.commands == [], 'Arming alone must never move servos'
    deliver(pygame.MOUSEBUTTONDOWN, app._targets['forward'].center, 3900)
    app._worker.join(timeout=1)
    app.update()
    assert backend.commands == ['forward']
    assert not app._armed, 'Authorization expires after one command'
    apps.deactivate()

releases = []
self.show_app = False
self.terminal_system = SimpleNamespace(handle_mouse_up=lambda: releases.append(True))
deliver(pygame.MOUSEBUTTONUP, (0, 0), 4000)
assert releases == [True], 'Terminal release routing must still work'
assert HARDWARE_ATTEMPTS == []
pygame.quit()
'''
        preamble = f'from pathlib import Path\nROOT = Path({str(ROOT)!r})\nTRANSFORM = {ast.unparse(transform)!r}\nLOOP = {ast.unparse(loop)!r}\n'
        result = subprocess.run([sys.executable, '-c', preamble + script], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
