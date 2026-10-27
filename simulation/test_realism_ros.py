"""Real ROS wiring of noisy odometry, one TF authority and command timeout."""
import os
from pathlib import Path
import sys
import time
import unittest
os.environ.update(ROS_DOMAIN_ID='86',ROS_LOCALHOST_ONLY='1')
sys.path.insert(0,str(Path(__file__).resolve().parent))
import rclpy
from rclpy.executors import SingleThreadedExecutor
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
from realism import load_profile
from realism_node import RealismNode

class RealismRosTests(unittest.TestCase):
    def test_raw_interfaces_have_one_estimated_tf_and_timeout_stops_actuator(self):
        rclpy.init(); adapter=RealismNode(load_profile(),seed=17,scale=1.)
        source=rclpy.create_node('realism_test_source')
        executor=SingleThreadedExecutor(); executor.add_node(adapter); executor.add_node(source)
        scan_pub=source.create_publisher(LaserScan,'/simulation/raw_scan',10)
        odom_pub=source.create_publisher(Odometry,'/simulation/raw_odom',10)
        command_pub=source.create_publisher(Twist,'/cmd_vel',10)
        scans=[]; odoms=[]; transforms=[]; commands=[]
        subscriptions=[source.create_subscription(LaserScan,'/scan',scans.append,10),
            source.create_subscription(Odometry,'/odom',odoms.append,10),
            source.create_subscription(TFMessage,'/tf',transforms.append,10),
            source.create_subscription(Twist,'/simulation/actuator_cmd_vel',commands.append,10)]
        try:
            end=time.monotonic()+3.; i=0
            while time.monotonic()<end:
                stamp=source.get_clock().now().to_msg()
                scan=LaserScan(); scan.header.stamp=stamp; scan.header.frame_id='laser'
                scan.range_min=.08; scan.range_max=8.; scan.ranges=[2.]*540; scan_pub.publish(scan)
                odom=Odometry(); odom.header.stamp=stamp; odom.header.frame_id='odom'
                odom.child_frame_id='base_link'; odom.pose.pose.position.x=i*.001
                odom.pose.pose.orientation.w=1.; odom_pub.publish(odom)
                command=Twist(); command.linear.x=.1; command_pub.publish(command)
                executor.spin_once(timeout_sec=.01); i+=1
            self.assertGreater(len(scans),2); self.assertGreater(len(odoms),2)
            self.assertTrue(any(c.linear.x>0 for c in commands))
            self.assertTrue(any(v != 2. for v in scans[-1].ranges))
            self.assertEqual({x.node_name for x in source.get_publishers_info_by_topic('/tf')},{'wheeltec_realism'})
            end=time.monotonic()+1.
            while time.monotonic()<end: executor.spin_once(timeout_sec=.02)
            self.assertEqual(commands[-1].linear.x,0.)
            self.assertEqual(commands[-1].angular.z,0.)
            self.assertEqual(transforms[-1].transforms[0].header.stamp,odoms[-1].header.stamp)
            self.assertEqual(transforms[-1].transforms[0].transform.translation.x,odoms[-1].pose.pose.position.x)
        finally:
            executor.shutdown(); source.destroy_node(); adapter.destroy_node(); rclpy.shutdown()

if __name__=='__main__': unittest.main()
