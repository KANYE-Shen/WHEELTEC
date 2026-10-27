"""Simulation-only ROS adapters; raw odom/scan in, estimated interfaces out."""
import argparse
import copy
import json
import math
from pathlib import Path
import resource
import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_ros import TransformBroadcaster
from realism import load_profile,value,ScanModel,OdomModel,ActuatorModel


def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))


class RealismNode(Node):
    def __init__(self, profile, seed=0, scale=1.):
        super().__init__('wheeltec_realism')
        self.profile=profile; self.seed=seed; self.scale=scale
        self.scan_model=ScanModel(profile,seed,scale)
        self.odom_model=OdomModel(profile,seed,scale)
        self.actuator_model=ActuatorModel(profile,seed,scale)
        self.counts={'scan':0,'odom':0,'commands':0}
        self.scan_pub=self.create_publisher(LaserScan,'/scan',10)
        self.odom_pub=self.create_publisher(Odometry,'/odom',50)
        self.command_pub=self.create_publisher(Twist,'/simulation/actuator_cmd_vel',10)
        self.status_pub=self.create_publisher(String,'/simulation/realism_status',10)
        self.tf=TransformBroadcaster(self)
        self.input_subscriptions=[
            self.create_subscription(LaserScan,'/simulation/raw_scan',self.scan,qos_profile_sensor_data),
            self.create_subscription(Odometry,'/simulation/raw_odom',self.odom,qos_profile_sensor_data),
            self.create_subscription(Twist,'/cmd_vel',self.command,10)]
        self.timer=self.create_timer(.02,self.actuate)
        self.status_timer=self.create_timer(1.,self.status)

    def seconds(self): return self.get_clock().now().nanoseconds/1e9

    def scan(self, message):
        output=copy.deepcopy(message)
        stamp=message.header.stamp.sec+message.header.stamp.nanosec/1e9
        ranges,stamp=self.scan_model.apply(message.ranges,stamp,message.range_min,message.range_max)
        ns=max(0,round(stamp*1e9)); output.header.stamp.sec=ns//1_000_000_000
        output.header.stamp.nanosec=ns%1_000_000_000
        output.ranges=ranges
        self.scan_pub.publish(output); self.counts['scan']+=1

    def odom(self, message):
        v=message.pose.pose.position; q=message.pose.pose.orientation
        stamp=message.header.stamp.sec+message.header.stamp.nanosec/1e9
        estimate=self.odom_model.update((v.x,v.y,yaw(q)),stamp)
        if estimate is None: return
        output=copy.deepcopy(message); x,y,theta=estimate['pose']
        output.pose.pose.position.x=x; output.pose.pose.position.y=y
        output.pose.pose.orientation.x=output.pose.pose.orientation.y=0.
        output.pose.pose.orientation.z=math.sin(theta/2); output.pose.pose.orientation.w=math.cos(theta/2)
        output.twist.twist.linear.x,output.twist.twist.angular.z=estimate['twist']
        for index,variance in zip((0,7,35),estimate['variance']): output.pose.covariance[index]=variance
        self.odom_pub.publish(output)
        transform=TransformStamped(); transform.header=output.header
        transform.child_frame_id=output.child_frame_id
        transform.transform.translation.x=x; transform.transform.translation.y=y
        transform.transform.rotation=output.pose.pose.orientation
        self.tf.sendTransform(transform); self.counts['odom']+=1

    def command(self, message):
        self.actuator_model.submit((message.linear.x,message.angular.z),self.seconds())
        self.counts['commands']+=1

    def actuate(self):
        linear,angular=self.actuator_model.update(self.seconds())
        output=Twist(); output.linear.x=linear; output.angular.z=angular
        self.command_pub.publish(output)

    def status(self):
        usage=resource.getrusage(resource.RUSAGE_SELF)
        self.status_pub.publish(String(data=json.dumps({
            'seed':self.seed,'noise_scale':self.scale,'counts':self.counts,
            'calibration_complete':self.profile.get('calibration_complete',False),
            'imu_present':value(self.profile,'imu.present'),'ekf_enabled':False,
            'cpu_seconds':usage.ru_utime+usage.ru_stime,'max_rss_kib':usage.ru_maxrss,
            'no_truth_subscription':True})))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=0); parser.add_argument('--scale',type=float,default=1.)
    args,ros_args=parser.parse_known_args()
    rclpy.init(args=ros_args,signal_handler_options=SignalHandlerOptions.NO); node=RealismNode(load_profile(args.profile),args.seed,args.scale)
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.command_pub.publish(Twist())
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()

if __name__=='__main__': main()
