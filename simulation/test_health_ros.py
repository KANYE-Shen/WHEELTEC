"""Actual ROS messages must block Explorer on unhealthy estimated transforms."""
import math
import os
from pathlib import Path
import sys
import time
import unittest
os.environ.update(ROS_DOMAIN_ID='84',ROS_LOCALHOST_ONLY='1')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/wheeltec_explore'))
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import QoSProfile,DurabilityPolicy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import LaserScan
from tf2_ros import TransformBroadcaster
from wheeltec_explore.node import Explorer
from wheeltec_explore.health import MapUnstableError

class HealthRosTest(unittest.TestCase):
    def test_real_tf_jump_prevents_completion_and_latches(self):
        rclpy.init()
        explorer=Explorer(); source=rclpy.create_node('slam_toolbox')
        executor=SingleThreadedExecutor(); executor.add_node(explorer); executor.add_node(source)
        scan_pub=source.create_publisher(LaserScan,'/scan',10)
        map_pub=source.create_publisher(OccupancyGrid,'/map',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        tf=TransformBroadcaster(source)
        def publish(x):
            stamp=source.get_clock().now().to_msg()
            scan=LaserScan(); scan.header.stamp=stamp; scan.header.frame_id='laser'
            scan_pub.publish(scan)
            grid=OccupancyGrid(); grid.header.stamp=stamp; grid.header.frame_id='map'
            grid.info.width=20; grid.info.height=20; grid.info.resolution=.1
            grid.info.origin.orientation.w=1.; grid.data=[0]*400; map_pub.publish(grid)
            transforms=[]
            for parent,child,tx in (('map','odom',x),('odom','base_link',0.)):
                t=TransformStamped(); t.header.stamp=stamp; t.header.frame_id=parent
                t.child_frame_id=child; t.transform.translation.x=float(tx)
                t.transform.rotation.w=1.; transforms.append(t)
            tf.sendTransform(transforms)
        try:
            until=time.monotonic()+4
            while time.monotonic()<until:
                publish(0); executor.spin_once(timeout_sec=.02)
            self.assertTrue(explorer.health_tick()['healthy'])
            explorer.health_active=True
            self.assertTrue(explorer.require_health())
            until=time.monotonic()+1
            while time.monotonic()<until:
                publish(2.2); executor.spin_once(timeout_sec=.01)
            with self.assertRaises(MapUnstableError): explorer.require_health()
            self.assertIn('map_to_odom_translation_jump',explorer.health_latched)
        finally:
            executor.shutdown(); explorer.destroy_node(); source.destroy_node(); rclpy.shutdown()

if __name__=='__main__': unittest.main()
