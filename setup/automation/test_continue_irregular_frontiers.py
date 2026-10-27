import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('wake',Path(__file__).with_name('continue_irregular_frontiers.py'))

class WakeGuardTests(unittest.TestCase):
    def test_completed_is_quiet_and_active_recent_is_not_duplicated(self):
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertFalse(module.should_resume({'status':'completed','heartbeat_epoch':0},1000))
        self.assertFalse(module.should_resume({'status':'running','heartbeat_epoch':950},1000))
        self.assertTrue(module.should_resume({'status':'pending','heartbeat_epoch':999},1000))
        self.assertTrue(module.should_resume({'status':'running','heartbeat_epoch':0},1000))
    def test_fail_closed_on_invalid_task_state(self):
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaises(ValueError):module.should_resume({'status':'typo'},1000)
