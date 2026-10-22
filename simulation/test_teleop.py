"""The keyboard command must stop when the operator stops sending keys."""
import importlib.util
from pathlib import Path
import unittest


class DeadmanCommandTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).with_name('teleop.py')
        self.assertTrue(source.is_file(), 'Missing keyboard teleop implementation')
        spec = importlib.util.spec_from_file_location('wheeltec_teleop', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.command = module.DeadmanCommand(timeout=0.35)

    def test_no_key_means_stopped(self):
        self.assertEqual(self.command.velocity(0.0), (0.0, 0.0))

    def test_forward_stops_after_missing_key_repeats(self):
        self.command.feed('i', 10.0)
        self.assertEqual(self.command.velocity(10.1), (0.15, 0.0))
        self.assertEqual(self.command.velocity(10.36), (0.0, 0.0))

    def test_repeated_keys_extend_deadline(self):
        self.command.feed('i', 10.0)
        self.command.feed('i', 10.3)
        self.assertEqual(self.command.velocity(10.5), (0.15, 0.0))
        self.assertEqual(self.command.velocity(10.66), (0.0, 0.0))

    def test_turn_and_reverse(self):
        for key, expected in [('j', (0.0, 0.5)), ('l', (0.0, -0.5)), (',', (-0.15, 0.0))]:
            self.command.feed(key, 10.0)
            self.assertEqual(self.command.velocity(10.1), expected)

    def test_stop_exit_and_unknown_keys_clear_motion(self):
        for key in ['k', ' ', 'q', '\x03', 'x']:
            self.command.feed('i', 10.0)
            self.command.feed(key, 10.1)
            self.assertEqual(self.command.velocity(10.2), (0.0, 0.0))


if __name__ == '__main__':
    unittest.main()