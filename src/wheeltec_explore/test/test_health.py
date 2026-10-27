import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from wheeltec_explore.health import MapHealth
except ImportError:
    MapHealth=None

class HealthTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(MapHealth,'Map health monitor is missing')
        self.h=MapHealth()
        self.h.map(10,10); self.h.scan(10,10)
        self.h.transform(10,10,(0,0,0)); self.h.slam(True)

    def test_fresh_inputs_are_healthy(self):
        self.assertTrue(self.h.snapshot(10.1)['healthy'])

    def test_map_jump_latches_even_if_transform_returns(self):
        self.h.transform(10.1,10.1,(2.2,0,0))
        self.h.transform(10.2,10.2,(0,0,0))
        self.assertIn('map_to_odom_translation_jump',self.h.snapshot(10.2)['issues'])

    def test_rotation_wrap_does_not_create_false_jump(self):
        h=MapHealth(); h.transform(10,10,(0,0,math.pi-.01))
        h.transform(10.1,10.1,(0,0,-math.pi+.01))
        self.assertFalse(h.faults)
        h.transform(10.2,10.2,(0,0,0))
        self.assertIn('map_to_odom_rotation_jump',h.faults)

    def test_stale_or_repeated_measurement_is_rejected(self):
        self.h.map(10,24.9)
        self.assertIn('map_update_timeout',self.h.snapshot(25.1)['issues'])
        self.assertIn('scan_stale',self.h.snapshot(11.1)['issues'])
        self.assertIn('tf_stale',self.h.snapshot(11.1)['issues'])

    def test_dead_slam_and_future_inputs_block_completion(self):
        self.h.slam(False)
        self.assertIn('slam_not_alive',self.h.snapshot(10)['issues'])
        self.h.scan(15,10)
        self.assertIn('scan_stamp_invalid',self.h.snapshot(10)['issues'])

    def test_slam_future_dated_transform_is_not_a_future_scan(self):
        self.h.transform(10.2,10,(0,0,0))
        self.assertNotIn('tf_stamp_invalid',self.h.snapshot(10)['issues'])
        self.h.transform(15,10,(0,0,0))
        self.assertIn('tf_stamp_invalid',self.h.snapshot(10)['issues'])

    def test_clock_rollback_is_explicit_fault(self):
        self.h.snapshot(10)
        self.assertIn('ros_time_moved_backwards',self.h.snapshot(9)['issues'])

    def test_missing_and_nonfinite_transform_cannot_be_healthy(self):
        self.h.transform(10.2,10.2,(float('nan'),0,0))
        self.assertIn('nonfinite_transform',self.h.snapshot(10.2)['issues'])
        self.assertFalse(MapHealth().snapshot(10)['healthy'])

if __name__=='__main__': unittest.main()
