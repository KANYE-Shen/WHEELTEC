"""Interface checks must distinguish a topic name from usable live data."""
import unittest
from inspect_interfaces import assess_stream


class StreamAssessmentTests(unittest.TestCase):
    def test_publisher_without_messages_is_not_live(self):
        report = assess_stream([], [], now=10, stamp_now=100, minimum_hz=5)
        self.assertFalse(report['passed'])
        self.assertEqual(report['messages'], 0)
        self.assertIsNone(report['wall_hz'])

    def test_fresh_monotonic_sensor_stream_is_usable(self):
        received = [i/10 for i in range(21)]
        report = assess_stream(received, [100+t for t in received], now=2.1, stamp_now=102.1, minimum_hz=5)
        self.assertTrue(report['passed'])
        self.assertAlmostEqual(report['wall_hz'], 10)
        self.assertAlmostEqual(report['stamp_age_seconds'], .1)

    def test_stale_or_slow_data_does_not_pass(self):
        self.assertFalse(assess_stream([0, .1, .2], [100,100.1,100.2], now=3, stamp_now=103, minimum_hz=5)['passed'])
        self.assertFalse(assess_stream([0, 1, 2], [100,101,102], now=2, stamp_now=102, minimum_hz=5)['passed'])

    def test_backwards_zero_and_future_timestamps_fail(self):
        times = [0, .1, .2]
        for stamps, stamp_now in [([100,100.1,100.05],100.2), ([0,0,0],100), ([101,101.1,101.2],100.2)]:
            with self.subTest(stamps=stamps):
                self.assertFalse(assess_stream(times, stamps, now=.2, stamp_now=stamp_now, minimum_hz=5)['passed'])


    def test_republished_old_measurements_do_not_inflate_sensor_rate(self):
        received = [i / 10 for i in range(150)]
        stamps = [100 + int(i / 10) for i in range(150)]
        result = assess_stream(received, stamps, 14.9, 114.9, 5)
        self.assertFalse(result['passed'])
        self.assertAlmostEqual(result['wall_hz'], 10)
        self.assertAlmostEqual(result['measurement_wall_hz'], 1)
        self.assertEqual(result['duplicate_stamps'], 135)

    def test_frozen_clock_and_republished_tail_is_stale(self):
        result = assess_stream([0,.1,.2,15], [100,100.1,100.2,100.2], 15,100.2,5)
        self.assertFalse(result['passed'])
        self.assertAlmostEqual(result['measurement_age_seconds'], 14.8)

    def test_nonfinite_scan_still_produces_failure_report(self):
        import inspect_interfaces as checker
        import itertools, json, sys
        from pathlib import Path
        from types import SimpleNamespace as NS
        from unittest.mock import Mock, patch
        callbacks = {}
        node = Mock()
        node.create_subscription.side_effect = lambda typ, topic, cb, qos: callbacks.setdefault(topic, cb)
        node.count_publishers.return_value = 1
        node.get_topic_names_and_types.return_value = [("/imu",["sensor_msgs/msg/Imu"])]
        node.get_node_names.return_value = ["driver"]
        node.get_clock.return_value.now.return_value.nanoseconds = 100_200_000_000
        header = lambda frame: NS(stamp=NS(sec=100,nanosec=200_000_000),frame_id=frame)
        scan = NS(header=header('laser'),range_min=.1,range_max=10.,
                  angle_min=0.,angle_max=float('nan'),ranges=[1.])
        odom = NS(header=header('odom'),child_frame_id='base_link')
        ros = NS(init=Mock(),create_node=Mock(return_value=node),ok=lambda:True,shutdown=Mock(),
                 spin_once=lambda *a,**kw:(callbacks['/scan'](scan),callbacks['/odom'](odom)))
        transform = NS(transform=NS(translation=NS(x=0.,y=0.,z=0.),rotation=NS(x=0.,y=0.,z=0.,w=1.)))
        buffer = Mock(lookup_transform=Mock(return_value=transform))
        modules = {'rclpy':ros,'rclpy.parameter':NS(Parameter=lambda *a,**kw:None),
                   'rclpy.qos':NS(qos_profile_sensor_data=None),
                   'rclpy.time':NS(Time=NS(from_msg=lambda stamp:stamp)),
                   'sensor_msgs.msg':NS(LaserScan=object,Image=object),'nav_msgs.msg':NS(Odometry=object),
                   'tf2_ros':NS(Buffer=lambda **kw:buffer,TransformListener=lambda *a:object(),TransformException=RuntimeError)}
        ticks = itertools.count(step=.1)
        with patch.dict(sys.modules,modules), \
             patch.object(sys,'argv',['inspect','--seconds','3','--output','never-written.json']), \
             patch.object(checker,'resources',return_value={}), \
             patch.object(checker.time,'monotonic',side_effect=lambda:next(ticks)), \
             patch.object(Path,'mkdir'),patch.object(Path,'exists',return_value=False), \
             patch.object(Path,'write_text') as write,patch('builtins.print'):
            exit_code = checker.main()
        result = json.loads(write.call_args.args[0])
        self.assertEqual(exit_code,1)
        self.assertFalse(result['interface_check_passed'])
        self.assertIsNone(result['scan']['angle_max_rad'])
        self.assertTrue(result['invalid_numeric_fields'])
        self.assertEqual(result['imu_topic_candidates'],['/imu'])
        self.assertFalse(result['imu_hardware_confirmed'])


class G0ClockRegressionTests(unittest.TestCase):
    def test_uninitialized_clock_cannot_be_reported_as_ready(self):
        from inspect_interfaces import clock_assessment
        self.assertFalse(clock_assessment(946687000)['plausible_utc'])
        self.assertFalse(clock_assessment(1793196000)['synchronization_verified'])
        self.assertTrue(clock_assessment(1793196000)['plausible_utc'])

    def test_future_sample_is_not_erased_by_a_fresh_last_sample(self):
        result=assess_stream([0,1,2],[100.8,101,102],2,102,.5,sample_clocks=[100,101,102])
        self.assertFalse(result['passed'])
        self.assertEqual(result['future_samples'],1)

if __name__ == '__main__':
    unittest.main()
