import unittest
import math
from console.backend.policy import Lease, fingerprint, check_origin


class PolicyTests(unittest.TestCase):
    def test_boot_and_expiry_hold(self):
        p = Lease()
        self.assertEqual(p.output(0), (0, 0))
        p.claim('a', 0)
        p.command('a', .1, .2, 0)
        self.assertEqual(p.output(.1), (.1, .2))
        self.assertEqual(p.output(.6), (0, 0))
        self.assertIsNone(p.owner)

    def test_single_owner_and_no_reconnect_resume(self):
        p = Lease()
        p.claim('a', 0)
        with self.assertRaises(ValueError):
            p.claim('b', .1)
        p.release()
        self.assertEqual(p.output(.2), (0, 0))
        p.claim('b', .2)
        self.assertEqual(p.output(.2), (0, 0))

    def test_invalid_and_unowned_commands(self):
        p = Lease()
        with self.assertRaises(ValueError):
            p.command('x', .1, 0, 0)
        p.claim('x', 0)
        with self.assertRaises(ValueError):
            p.command('x', math.nan, 0, 0)
        self.assertEqual(p.output(0), (0, 0))

    def test_limits(self):
        p = Lease()
        p.claim('x', 0)
        p.command('x', 9, -9, 0)
        self.assertEqual(p.output(0), (.1, -.3))

    def test_lease_not_extended_by_polling(self):
        p = Lease()
        p.claim('x', 0)
        p.output(.1)
        self.assertEqual(p.output(.51), (0, 0))

    def test_origin_rejects_foreign_and_null(self):
        self.assertTrue(check_origin(
            'http://127.0.0.1:8766', '127.0.0.1:8766'))
        for origin in ('null', 'http://evil.test', 'http://127.0.0.1:1', None):
            self.assertFalse(check_origin(origin, '127.0.0.1:8766'))

    def test_fingerprint(self):
        self.assertEqual(fingerprint(b'abc'),
                         'SHA256:ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0')


class SimulationBoundaryTests(unittest.TestCase):
    def test_real_board_cannot_enable_simulation_control(self):
        from console.backend.policy import simulation_authorized
        self.assertFalse(simulation_authorized(
            {'WSL_DISTRO_NAME': 'WHEELTEC-Ubuntu-22.04', 'ROS_LOCALHOST_ONLY': '1'}, 'aarch64'))
        self.assertFalse(simulation_authorized({}, 'x86_64'))
        self.assertTrue(simulation_authorized(
            {'WSL_DISTRO_NAME': 'WHEELTEC-Ubuntu-22.04', 'ROS_LOCALHOST_ONLY': '1'}, 'x86_64'))


class ArmTests(unittest.TestCase):
    def test_requires_ack_and_never_rearms_after_drop(self):
        from console.backend.policy import ArmHandshake
        a = ArmHandshake()
        a.start(0)
        self.assertFalse(a.ready)
        self.assertIsNone(a.observe(False, .1))
        self.assertIsNone(a.observe(True, .2))
        self.assertTrue(a.ready)
        self.assertEqual(a.observe(False, .3), 'final_watchdog_hold')
        self.assertFalse(a.ready)
        self.assertEqual(a.observe(True, .4), 'final_watchdog_hold')
        self.assertFalse(a.ready)

    def test_arm_timeout(self):
        from console.backend.policy import ArmHandshake
        a = ArmHandshake()
        a.start(0)
        self.assertEqual(a.observe(False, 1.1), 'watchdog_arm_failed')
        self.assertFalse(a.ready)
