"""Bounded frontier exploration using SLAM maps and the Nav2 action interface."""
import json
import math
import os
from pathlib import Path
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, qos_profile_sensor_data
from rclpy.time import Time
from rclpy.signals import SignalHandlerOptions
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import NavigateToPose
from nav2_msgs.srv import SaveMap
from slam_toolbox.srv import SerializePoseGraph
from std_msgs.msg import String
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener, TransformException

from .frontiers import Grid, select_frontiers
from .policy import RetryBook, completion_state, observation_fresh


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))


def atomic_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(content, indent=2, ensure_ascii=False)+'\n')
    os.replace(temporary, path)


class Explorer(Node):
    def __init__(self):
        super().__init__('wheeltec_explore')
        maps = Path.home()/'wheeltec_sim_ws/data/maps'
        default_output = maps/time.strftime('%Y%m%d-%H%M%S_explore')/'room'
        parameters = {'map_frame': 'map', 'base_frame': 'base_link',
                      'map_output': str(default_output), 'reference_yaw_rad': 0.0, 'update_latest': True,
                      'robot_radius': 0.35, 'min_frontier_size': 0.25,
                      'minimum_free_area': 8.0, 'goal_timeout': 120.0,
                      'task_timeout': 900.0, 'max_goals': 60,
                      'retry_cooldown': 20.0, 'max_attempts': 3}
        for name,value in parameters.items():
            self.declare_parameter(name,value)
        self.config = {name:self.get_parameter(name).value for name in parameters}
        self.output = Path(self.config['map_output']).expanduser().resolve()
        self.maps_root = maps
        self.latest_map = None
        self.map_updates = 0
        self.last_scan_wall = None
        self.scan_subscription = self.create_subscription(LaserScan, '/scan', self.receive_scan, qos_profile_sensor_data)
        self.subscription = self.create_subscription(
            OccupancyGrid,'/map',self.receive_map,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                       reliability=ReliabilityPolicy.RELIABLE))
        self.status_publisher = self.create_publisher(
            String,'/exploration/status',
            QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.tf = Buffer(cache_time=Duration(seconds=30))
        self.listener = TransformListener(self.tf,self)
        self.nav = ActionClient(self,NavigateToPose,'/navigate_to_pose')
        self.save = self.create_client(SaveMap,'/map_saver/save_map')
        self.serialize = self.create_client(SerializePoseGraph,'/slam_toolbox/serialize_map')
        self.history = []
        self.active_goal = None
        self.active_result = None
        self.retry = RetryBook(self.config['retry_cooldown'],self.config['max_attempts'])
        self.report = {'state':'starting','map_output':str(self.output),'goals':[],
                       'reference_yaw_rad':self.config['reference_yaw_rad']}
        self.started = time.monotonic()
        self.visited = []

    def receive_scan(self,message):
        self.last_scan_wall = time.monotonic()

    def receive_map(self,message):
        self.latest_map = message
        self.map_updates += 1

    def status(self,state,reason='',**values):
        self.report.update(state=state,reason=reason,**values)
        self.report['elapsed_wall_seconds'] = round(time.monotonic()-self.started,2)
        message = String(data=json.dumps(self.report,ensure_ascii=False))
        self.status_publisher.publish(message)
        atomic_json(self.output.with_suffix('.exploration.json'),self.report)
        entry = {'state':state,'reason':reason,'elapsed_wall_seconds':self.report['elapsed_wall_seconds']}
        self.history.append(entry)
        self.get_logger().info(json.dumps(entry,ensure_ascii=False))

    def wait(self,predicate,timeout,check_task=False,check_sensors=False):
        deadline = time.monotonic()+timeout
        while rclpy.ok() and time.monotonic()<deadline:
            if check_task and time.monotonic()-self.started > self.config['task_timeout']:
                return False
            if check_sensors and not observation_fresh(self.last_scan_wall,time.monotonic()):
                raise RuntimeError('LaserScan updates stopped during navigation')
            rclpy.spin_once(self,timeout_sec=0.1)
            if predicate():
                return True
        return False

    def position(self):
        try:
            transform = self.tf.lookup_transform(self.config['map_frame'],self.config['base_frame'],Time())
            t = transform.transform
            return t.translation.x,t.translation.y,yaw(t.rotation)
        except TransformException:
            return None

    def grid(self):
        m = self.latest_map
        return Grid(m.info.width,m.info.height,m.info.resolution,
                    m.info.origin.position.x,m.info.origin.position.y,
                    yaw(m.info.origin.orientation),m.data)

    def navigate(self,x,y,heading,returning=False):
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = self.config['map_frame']
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x,goal.pose.pose.position.y = float(x),float(y)
        goal.pose.pose.orientation.z = math.sin(heading/2)
        goal.pose.pose.orientation.w = math.cos(heading/2)
        accepted = self.nav.send_goal_async(goal)
        if not self.wait(accepted.done,10):
            raise RuntimeError('Nav2 did not respond to the goal request')
        handle = accepted.result()
        if handle is None or not handle.accepted:
            return False,'rejected'
        self.active_goal = handle
        result = handle.get_result_async()
        self.active_result = result
        if not self.wait(result.done,self.config['goal_timeout'],check_task=not returning,check_sensors=True):
            cancel = handle.cancel_goal_async()
            self.wait(cancel.done,5)
            if not self.wait(result.done,15):
                raise RuntimeError('Nav2 goal timed out and did not confirm cancellation')
            self.active_goal = None
            return False,'timeout'
        self.active_goal = None
        response = result.result()
        if response is None:
            return False,'no_result'
        return response.status==GoalStatus.STATUS_SUCCEEDED,str(response.status)

    def save_map(self):
        self.status('saving','Saving occupancy grid and SLAM pose graph')
        if not self.save.wait_for_service(timeout_sec=10) or not self.serialize.wait_for_service(timeout_sec=10):
            raise RuntimeError('Map saver or SLAM serialization service is not active')
        self.output.parent.mkdir(parents=True,exist_ok=True)
        request = SaveMap.Request()
        request.map_topic = '/map'
        request.map_url = str(self.output)
        request.image_format = 'pgm'
        request.map_mode = 'trinary'
        # 205/255 is the Humble trinary unknown shade; .25 would reload it as free.
        request.free_thresh = 0.19
        request.occupied_thresh = 0.65
        future = self.save.call_async(request)
        if not self.wait(future.done,30) or future.result() is None or not future.result().result:
            raise RuntimeError('Map saver could not write the occupancy map')
        request = SerializePoseGraph.Request(filename=str(self.output))
        future = self.serialize.call_async(request)
        if not self.wait(future.done,30) or future.result() is None or future.result().result!=0:
            raise RuntimeError('SLAM Toolbox could not serialize the pose graph')
        for suffix in ('.yaml','.pgm','.posegraph','.data'):
            if not self.output.with_suffix(suffix).is_file():
                raise RuntimeError('Map saving did not produce '+suffix)
        metadata = {'map_yaml':str(self.output.with_suffix('.yaml')),
                    'posegraph':str(self.output),'reference_yaw_rad':self.config['reference_yaw_rad'],
                    'map_frame':self.config['map_frame'],'saved_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                    'source':'wheeltec_explore','start_pose':self.report['start_pose']}
        atomic_json(self.output.with_suffix('.metadata.json'),metadata)
        if self.config['update_latest']:
            atomic_json(self.maps_root/'latest.json',metadata)
        return True

    def run(self):
        self.status('starting','Waiting for SLAM map, robot transform and Nav2')
        if not self.wait(lambda:self.latest_map is not None and self.position() is not None
                         and observation_fresh(self.last_scan_wall,time.monotonic()),90):
            raise RuntimeError('Timed out waiting for SLAM map and map-to-base transform')
        if not self.nav.wait_for_server(timeout_sec=60):
            raise RuntimeError('Nav2 NavigateToPose action server is unavailable')
        start = self.position()
        self.report['start_pose'] = list(start)
        self.status('exploring','Selecting reachable frontiers')
        stable_empty, attempts, latest_result = 0,0,None
        forced_reason = ''
        while rclpy.ok():
            if time.monotonic()-self.started>self.config['task_timeout']:
                forced_reason = 'task_timeout'
                break
            if attempts>=self.config['max_goals']:
                forced_reason = 'goal_limit'
                break
            pose = self.position()
            if pose is None:
                if not self.wait(lambda:self.position() is not None,15):
                    raise RuntimeError('Robot localization transform was lost')
                continue
            latest_result = select_frontiers(self.grid(),pose[:2],self.config['robot_radius'],
                                              self.config['min_frontier_size'],visited=self.visited)
            self.report.update(known_free_area_m2=round(latest_result.known_free_area,3),
                               frontier_clusters=latest_result.frontier_clusters,
                               unreachable_clusters=latest_result.unreachable_clusters,
                               ignored_small_clusters=latest_result.ignored_small_clusters)
            candidates = [g for g in latest_result.goals
                          if self.retry.available((g.x,g.y),time.monotonic())]
            if not candidates:
                if latest_result.goals:
                    if all(self.retry.exhausted((g.x,g.y)) for g in latest_result.goals):
                        forced_reason = 'frontier_retries_exhausted'
                        break
                    self.status('exploring','Waiting before retrying blocked frontiers')
                    old_revision = self.map_updates
                    self.wait(lambda:self.map_updates>old_revision,3,check_task=True)
                    continue
                stable_empty += 1
                if stable_empty>=3:
                    break
                old_revision = self.map_updates
                # Require fresh observations before concluding there is no target.
                if not self.wait(lambda:self.map_updates>old_revision,15,check_task=True):
                    raise RuntimeError('SLAM map stopped updating during completion check')
                continue
            stable_empty = 0
            target = candidates[0]
            self.status('exploring','Navigating to a frontier approach',target=[target.x,target.y])
            attempts += 1
            success,reason = self.navigate(target.x,target.y,target.yaw)
            self.report['goals'].append({'target':[target.x,target.y], 'success':success, 'result':reason})
            if success:
                self.visited.append((target.x,target.y))
                observed = self.position()
                if observed is not None:
                    self.visited.append(observed[:2])
            else:
                self.retry.failed((target.x,target.y),time.monotonic())
            old_revision = self.map_updates
            if not self.wait(lambda:self.map_updates>old_revision,15,check_task=True):
                forced_reason = 'map_update_timeout'
                break
        if latest_result is None:
            raise RuntimeError('No valid occupancy grid was processed')
        saved = self.save_map()
        self.status('returning','Returning to the exploration start position')
        current = self.position()
        if current is not None and math.dist(current[:2],start[:2])<=0.15:
            returned = True
        else:
            returned,_ = self.navigate(*start,returning=True)
        unresolved = 1 if forced_reason else 0
        final = completion_state(latest_result.known_free_area,latest_result.unreachable_clusters,
                                 unresolved,saved,returned,self.config['minimum_free_area'])
        reason = (forced_reason or ('no_reachable_frontiers' if final=='completed' else
                                   'remaining_unreachable_frontiers_or_insufficient_observed_area'))
        if not returned:
            reason = 'return_to_start_failed'
        self.status(final,reason,map_saved=saved,returned=returned,
                    completion_criteria={'stable_empty_maps':stable_empty,
                    'minimum_free_area_m2':self.config['minimum_free_area'],
                    'no_unreachable_clusters':latest_result.unreachable_clusters==0},history=self.history[:])
        self.wait(lambda:False,0.5)
        return 0 if final=='completed' else 2

    def cancel_active(self):
        if self.active_goal is not None:
            future = self.active_goal.cancel_goal_async()
            acknowledged = self.wait(future.done,5)
            terminal = self.active_result is not None and self.wait(self.active_result.done,15)
            self.active_goal = None
            if not acknowledged or not terminal:
                self.get_logger().error('Nav2 did not confirm cancellation of the exploration goal')
                return False
        return True


def main(args=None):
    rclpy.init(args=args,signal_handler_options=SignalHandlerOptions.NO)
    node = Explorer()
    code = 1
    try:
        code = node.run()
    except KeyboardInterrupt:
        node.cancel_active()
        node.status('failed','operator_interrupted')
        code = 130
    except Exception as error:
        node.cancel_active()
        node.status('failed',str(error))
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__=='__main__':
    raise SystemExit(main())