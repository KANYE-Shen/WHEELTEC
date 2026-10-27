import ast
import unittest
from pathlib import Path


class ManualLaunchTests(unittest.TestCase):
    def test_separate_manual_stack_has_no_autonomous_publishers(self):
        text = Path('robot/launch/manual.launch.py').read_text(encoding='utf-8')
        ast.parse(text)
        self.assertNotIn('controller_server', text)
        self.assertNotIn('behavior_server', text)
        self.assertNotIn('gazebo', text.lower())
        for expected in ('validate(', 'velocity_smoother', 'collision_monitor', 'watchdog.py', '--gate'):
            self.assertIn(expected, text)
