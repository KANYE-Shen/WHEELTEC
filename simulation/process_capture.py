"""Reusable, estimate-only process recording for validation and normal launches.

ProcessCapture(node, tf_buffer, output, scenario_metadata) subscribes only to
estimated ROS interfaces. It never reads world geometry or simulator truth.
Atomic process.json is refreshed every 5 wall seconds and finalized by close().
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import time


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))


class Timeline:
    def __init__(self, scenario=None):
        self.document={'version':1,'coordinate_frame':'map','scenario':scenario or {},
                       'frames':[],'maps':[],'statuses':[],'path':[],'terminal':None}
        self.map_keys={}
        self.map_index=None

    def add_map(self, grid):
        key=hashlib.sha256(json.dumps(grid,separators=(',',':')).encode()).hexdigest()
        if key not in self.map_keys:
            self.map_keys[key]=len(self.document['maps'])
            self.document['maps'].append(copy.deepcopy(grid))
        self.map_index=self.map_keys[key]
        return self.map_index

    def append_frame(self, frame):
        self.document['frames'].append(frame)
        pose=frame.get('pose')
        path=self.document['path']
        if pose is not None and (not path or math.dist(pose[:2],path[-1])>=.02):
            path.append(pose[:2])

    def save(self, output, terminal=None):
        path=Path(output)
        path.parent.mkdir(parents=True,exist_ok=True)
        if terminal is not None:
            self.document['terminal']=terminal
        temporary=path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(json.dumps(self.document,separators=(',',':'),ensure_ascii=False)+'\n')
        os.replace(temporary,path)


class ProcessCapture:
    def __init__(self,node,tf_buffer,output,scenario_metadata=None):
        from nav_msgs.msg import OccupancyGrid, Path as RosPath
        from sensor_msgs.msg import LaserScan
        from std_msgs.msg import String
        from rclpy.qos import QoSProfile,DurabilityPolicy,qos_profile_sensor_data
        from rclpy.clock import Clock,ClockType
        self.node=node
        self.tf=tf_buffer
        self.output=Path(output)
        self.timeline=Timeline(scenario_metadata)
        self.started=time.monotonic()
        self.latest_scan=self.latest_plan=None
        self.scan_received=self.plan_received=None
        self.status={}
        self.initial_pose=None
        self.initial_pose_time=None
        self.issue_counts={}
        self._pose_stamp_ns=self._pose_stamp_seen_wall=None
        durable=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.subscriptions=[
            node.create_subscription(OccupancyGrid,'/map',self.receive_map,durable),
            node.create_subscription(LaserScan,'/scan',self.receive_scan,qos_profile_sensor_data),
            node.create_subscription(RosPath,'/plan',self.receive_plan,10),
            node.create_subscription(String,'/exploration/status',self.receive_status,durable)]
        self.timer=node.create_timer(.5,self.tick)
        # Persistence must continue when Gazebo pauses or /clock stops.
        self.wall_clock=Clock(clock_type=ClockType.STEADY_TIME)
        self.wall_timer=node.create_timer(5.0,self.save,clock=self.wall_clock)

    def now(self):
        return self.node.get_clock().now().nanoseconds/1e9

    def receive_map(self,message):
        self.timeline.add_map({'width':message.info.width,'height':message.info.height,
                              'resolution':message.info.resolution,
                              'origin':[message.info.origin.position.x,message.info.origin.position.y,
                                        yaw(message.info.origin.orientation)],'data':list(message.data)})

    def receive_scan(self,message):
        self.latest_scan=message
        self.scan_received=time.monotonic()

    def receive_plan(self,message):
        self.latest_plan=message
        self.plan_received=time.monotonic()

    def receive_status(self,message):
        try:
            report=json.loads(message.data)
        except (ValueError,TypeError):
            self.issue_counts['invalid_status_json']=self.issue_counts.get('invalid_status_json',0)+1
            return
        self.status=report
        self.timeline.document['statuses'].append({'t':self.now(),'wall_t':time.monotonic()-self.started,**report})

    def stamped_transform(self,frame,stamp=None):
        from rclpy.time import Time
        query=Time.from_msg(stamp) if stamp is not None else Time()
        return self.tf.lookup_transform('map',frame,query)

    def transform(self,frame,stamp=None):
        return self.stamped_transform(frame,stamp).transform

    @staticmethod
    def point(x,y,transform):
        heading=yaw(transform.rotation)
        c,s=math.cos(heading),math.sin(heading)
        return [transform.translation.x+c*x-s*y,transform.translation.y+s*x+c*y]

    def tick(self):
        now=self.now()
        wall=time.monotonic()
        issues=[]
        pose=None
        scan=None
        plan=None
        pose_age=pose_wall_age=pose_stamp=None
        try:
            stamped=self.stamped_transform('base_link')
            stamp=stamped.header.stamp
            stamp_ns=stamp.sec*1_000_000_000+stamp.nanosec
            pose_stamp=stamp_ns/1e9
            pose_age=now-pose_stamp
            if stamp_ns!=self._pose_stamp_ns:
                self._pose_stamp_ns=stamp_ns
                self._pose_stamp_seen_wall=wall
            pose_wall_age=wall-self._pose_stamp_seen_wall
            if pose_age>1.0 or pose_age<-.1 or pose_wall_age>2.0:
                issues.append('stale_pose_transform')
            else:
                transform=stamped.transform
                pose=[transform.translation.x,transform.translation.y,yaw(transform.rotation)]
                if self.initial_pose is None:
                    self.initial_pose=pose[:]
                    self.initial_pose_time=now
        except Exception:
            issues.append('missing_map_transform')
        scan_age=None
        if self.latest_scan is None:
            issues.append('missing_scan')
        else:
            message=self.latest_scan
            stamp=message.header.stamp.sec+message.header.stamp.nanosec/1e9
            scan_age=now-stamp
            if wall-self.scan_received>2 or scan_age>1.0 or scan_age<-.1:
                issues.append('stale_scan')
            else:
                try:
                    transform=self.transform(message.header.frame_id,message.header.stamp)
                    scan=[self.point(distance*math.cos(message.angle_min+i*message.angle_increment),
                                     distance*math.sin(message.angle_min+i*message.angle_increment),transform)
                          for i,distance in enumerate(message.ranges)
                          if math.isfinite(distance) and message.range_min<=distance<=message.range_max]
                except Exception:
                    issues.append('missing_scan_transform')
        plan_age=None
        if self.latest_plan is not None:
            plan_age=wall-self.plan_received
            message=self.latest_plan
            try:
                if message.header.frame_id=='map':
                    plan=[[p.pose.position.x,p.pose.position.y] for p in message.poses]
                else:
                    transform=self.transform(message.header.frame_id,message.header.stamp)
                    plan=[self.point(p.pose.position.x,p.pose.position.y,transform) for p in message.poses]
            except Exception:
                issues.append('missing_plan_transform')
        for issue in issues:
            self.issue_counts[issue]=self.issue_counts.get(issue,0)+1
        self.timeline.append_frame({'t':now,'wall_t':wall-self.started,'pose':pose,
                                    'pose_stamp_s':pose_stamp,'pose_age_s':pose_age,'pose_transform_wall_age_s':pose_wall_age,
                                    'scan':scan,'scan_age_s':scan_age,'plan':plan,'plan_age_wall_s':plan_age,
                                    'status':copy.deepcopy(self.status),'map':self.timeline.map_index,'issues':issues})

    def save(self,terminal=None):
        self.timeline.document['capture']={'initial_pose':self.initial_pose,
                                          'initial_pose_t':self.initial_pose_time,
                                          'issue_counts':self.issue_counts,'sample_period_sim_s':.5,
                                          'pose_transform_limits':{'maximum_sim_age_s':1.0,'maximum_repeated_stamp_wall_age_s':2.0,'future_tolerance_s':.1}}
        self.timeline.save(self.output,terminal)

    def close(self,terminal=None):
        self.node.destroy_timer(self.timer)
        self.node.destroy_timer(self.wall_timer)
        self.tick()
        self.save(terminal)
