"""Verify capture persistence while ROS simulation time remains frozen.

Run explicitly after sourcing ROS; creates no publishers and moves no robot.
"""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest


class CaptureClockTests(unittest.TestCase):
    def test_steady_clock_flushes_when_simulation_clock_is_paused(self):
        os.environ.update(ROS_DOMAIN_ID='84',ROS_LOCALHOST_ONLY='1')
        import rclpy
        from rclpy.parameter import Parameter
        from tf2_ros import Buffer
        from std_msgs.msg import String
        from process_capture import ProcessCapture
        rclpy.init()
        node=rclpy.create_node('capture_paused_clock_test',parameter_overrides=[Parameter('use_sim_time',value=True)])
        capture=None
        try:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'process.json'
                capture=ProcessCapture(node,Buffer(node=node),path,{'id':'clock_pause_test'})
                capture.receive_status(String(data=json.dumps({'state':'paused_clock_marker'})))
                start=node.get_clock().now().nanoseconds
                deadline=time.monotonic()+5.8
                while time.monotonic()<deadline:
                    rclpy.spin_once(node,timeout_sec=.05)
                self.assertEqual(node.get_clock().now().nanoseconds,start)
                self.assertEqual(capture.timeline.document['frames'],[])
                self.assertTrue(path.is_file(),'capture must flush even while /clock is stopped')
                saved=json.loads(path.read_text())
                self.assertEqual(saved['statuses'][-1]['state'],'paused_clock_marker')
                capture.close({'state':'test_finished'})
                capture=None
        finally:
            if capture is not None:
                capture.close({'state':'test_cleanup'})
            node.destroy_node()
            rclpy.shutdown()


if __name__=='__main__':
    unittest.main()
