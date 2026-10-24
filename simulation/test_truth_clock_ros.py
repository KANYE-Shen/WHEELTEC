"""Explicit ROS-clock integration fixture; no Gazebo, sensors or motion publishers."""
import os
import time
import unittest


class TerminalRosClockTests(unittest.TestCase):
    def test_callback_delayed_ros_clock_synchronizes_with_new_source_measurements(self):
        os.environ.update(ROS_DOMAIN_ID='85',ROS_LOCALHOST_ONLY='1')
        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from rosgraph_msgs.msg import Clock
        from truth_capture import synchronize_terminal_truth,truth_quality
        rclpy.init()
        node=rclpy.create_node('truth_terminal_clock_fixture',parameter_overrides=[Parameter('use_sim_time',value=True)])
        publisher_node=rclpy.create_node('truth_clock_fixture_publisher')
        publisher=publisher_node.create_publisher(Clock,'/clock',QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT))
        def publish(value):
            message=Clock()
            message.clock.sec=int(value)
            message.clock.nanosec=int((value-int(value))*1e9)
            publisher.publish(message)
        try:
            deadline=time.monotonic()+3
            while node.get_clock().now().nanoseconds==0 and time.monotonic()<deadline:
                publish(.011)
                rclpy.spin_once(node,timeout_sec=.02)
            self.assertGreater(node.get_clock().now().nanoseconds,0)
            started=time.monotonic()-.4
            samples=[{'t':i*.02,'wall_t':i*.02,'pose':[0,0,0]} for i in range(21)]
            initial=truth_quality(samples,time.monotonic()-started,0,node.get_clock().now().nanoseconds/1e9)
            self.assertEqual(initial['issues'],['terminal_measurement_in_future'])
            def poll():
                current=time.monotonic()-started
                if current-samples[-1]['wall_t']>=.02:
                    samples.append({'t':current,'wall_t':current,'pose':[0,0,0]})
            def spin(timeout):
                publish(time.monotonic()-started)
                rclpy.spin_once(node,timeout_sec=timeout)
            result=synchronize_terminal_truth(samples,poll,spin,
                lambda:node.get_clock().now().nanoseconds/1e9,started)
            self.assertTrue(result['valid'],result)
            self.assertTrue(result['terminal_clock_sync']['attempted'])
            self.assertGreaterEqual(result['terminal_clock_sync']['new_distinct_measurement_stamps'],3)
            self.assertLessEqual(result['terminal_clock_sync']['elapsed_wall_s'],2)
            self.assertEqual(result['limits']['maximum_wall_gap_s'],.5)
            self.assertEqual(result['limits']['maximum_sim_gap_s'],.2)
            self.assertEqual(result['limits']['future_tolerance_s'],.1)
        finally:
            node.destroy_node()
            publisher_node.destroy_node()
            rclpy.shutdown()


if __name__=='__main__':
    unittest.main()