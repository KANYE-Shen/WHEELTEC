import unittest
import math
from console.target.data import finite_ranges, grid_payload, jpeg_from_image


class DataTests(unittest.TestCase):
    def test_invalid_ranges_preserve_beam_positions(self):
        self.assertEqual(finite_ranges([1, float('inf'), float('nan'), 0, 4], .1, 3), [
                         1, None, None, None, None])

    def test_grid_rejects_shape_and_preserves_unknown(self):
        self.assertEqual(grid_payload(2, 1, [-1, 100]), [-1, 100])
        with self.assertRaises(ValueError):
            grid_payload(2, 2, [0])

    def test_image_encoding_rejects_unsupported(self):
        class M:
            encoding = '16UC1'
        with self.assertRaises(ValueError):
            jpeg_from_image(M())


class FreshnessTests(unittest.TestCase):
    def test_zero_future_and_receive_stale_are_rejected(self):
        from console.target.data import fresh_measurement
        self.assertTrue(fresh_measurement(10, 10.1, 20, 20.1, 1))
        for stamp, ros, received, now in [(0, 0, 20, 20), (12, 10, 20, 20), (10, 10, 18, 20), (10, 12, 20, 20)]:
            self.assertFalse(fresh_measurement(stamp, ros, received, now, 1))


class TFChainTests(unittest.TestCase):
    def test_paused_ros_clock_does_not_keep_dynamic_tf_alive(self):
        from console.target.data import tf_chain_fresh
        edges = {('map', 'odom'): (10, False), ('odom', 'base'): (10, False), ('base', 'laser'): (0, True)}
        self.assertTrue(tf_chain_fresh(edges, 'map', 'laser', 10.2))
        self.assertFalse(tf_chain_fresh(edges, 'map', 'laser', 12))
        self.assertTrue(tf_chain_fresh(edges, 'base', 'laser', 120))
        self.assertFalse(tf_chain_fresh(edges, 'map', 'missing', 10.2))
