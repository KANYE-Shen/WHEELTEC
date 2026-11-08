"""Bounded frontier exploration using SLAM maps and the Nav2 action interface."""
import json
from concurrent.futures import ThreadPoolExecutor
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
from nav2_msgs.action import NavigateToPose, Spin
from nav2_msgs.srv import SaveMap
from slam_toolbox.srv import SerializePoseGraph
from std_msgs.msg import String
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener, TransformException

from .defaults import DEFAULTS
from .startup import wait_for_console_start
from .active_scan import choose_scan, rotation_clearance, ScanBudget, simulation_observation_allowed, startup_assumption_allowed
from .health import MapHealth, MapUnstableError
from .frontiers import Grid, FrontierResult, select_frontiers
from .vendor_frontiers import safe_vendor_goals, validate_vendor_geometry, validate_vendor_output
from .policy import RetryBook, completion_state, observation_fresh, local_known_ratio, ObservationProgress


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
        parameters = {**DEFAULTS, 'map_output':str(default_output),
                      'reference_yaw_rad':0.0, 'update_latest':True}
        for name,value in parameters.items():
            self.declare_parameter(name,value)
        self.config = {name:self.get_parameter(name).value for name in parameters}
        if self.config['frontier_backend'] not in ('grid', 'vendor'):
            raise ValueError('Unknown frontier backend')
        if self.config['frontier_backend'] == 'vendor' and (not math.isfinite(self.config['vendor_max_age']) or self.config['vendor_max_age'] <= 0):
            raise ValueError('Invalid vendor candidate age')
        if (not 0 < self.config['local_observation_threshold'] <= 1 or
                self.config['local_observation_maps'] < 1 or
                any(not math.isfinite(self.config[k]) or self.config[k] <= 0 for k in
                    ('local_observation_radius','local_observation_distance',
                     'goal_no_progress_timeout','goal_progress_distance'))):
            raise ValueError('Invalid local observation/progress parameters')
        angle = self.config['active_scan_angle_deg']
        if not math.isfinite(angle) or not 0 <= angle <= 360:
            raise ValueError('Active scan angle must be between 0 and 360 degrees')
        if angle or self.config['initial_rotation_assumed_safe']:
            board = Path('/proc/device-tree/model')
            model = board.read_text() if board.exists() else ''
            if not simulation_observation_allowed(self.get_parameter('use_sim_time').value,
                                                   os.environ.get('ROS_LOCALHOST_ONLY',''),model):
                raise RuntimeError('Active observation is available only in localhost simulation')
        self.scan_budget = ScanBudget(self.config['active_scan_max_attempts'])
        self.spin_action = ActionClient(self,Spin,'spin') if angle else None
        self.output = (validate_vendor_output(self.config['map_output'])
                       if self.config['frontier_backend'] == 'vendor'
                       else Path(self.config['map_output']).expanduser().resolve())
        self.maps_root = maps
        self.health = MapHealth(
            jump_translation=self.config['map_jump_translation'],
            jump_rotation=self.config['map_jump_rotation'],
            map_timeout=self.config['map_update_timeout'],scan_timeout=self.config['scan_max_age'],
            tf_timeout=self.config['tf_max_age'],future_tolerance=self.config['future_tolerance'],
            tf_future_offset=self.config['slam_transform_timeout'])
        self.health_active = False
        self.health_latched = {}
        self.vendor_points = ()
        self.vendor_received = None
        self.vendor_revision = 0
        self.vendor_initialized = False
        self.vendor_runtime = None
        self.vendor_map_bounds = None
        if self.config['frontier_backend'] == 'vendor':
            validate_vendor_geometry(self.config['robot_radius'],self.config['footprint_exclusion_radius'])
            from geometry_msgs.msg import PointStamped
            from wheeltec_rrt_msg.msg import PointArray
            if self.config['map_frame'] != 'map' or self.config['base_frame'] != 'base_footprint':
                raise ValueError('Vendor RRT requires map and base_footprint frames')
            self.boundary_pub = self.create_publisher(PointStamped, '/wheeltec_explore/vendor_boundary', 10)
            self.vendor_sub = self.create_subscription(PointArray, '/wheeltec_explore/vendor_points', self.receive_vendor_points, 10)
        self.latest_map = None
        self.map_updates = 0
        self.last_scan_ros = None
        self.scan_subscription = self.create_subscription(LaserScan, '/scan', self.receive_scan, qos_profile_sensor_data)
        self.subscription = self.create_subscription(
            OccupancyGrid,'/map',self.receive_map,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                       reliability=ReliabilityPolicy.RELIABLE))
        self.status_publisher = self.create_publisher(
            String,'/exploration/status',
            QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.tf = Buffer(cache_time=Duration(seconds=30),node=self)
        self.listener = TransformListener(self.tf,self)
        self.health_timer = self.create_timer(.2,self.health_tick)
        self.nav = ActionClient(self,NavigateToPose,'/navigate_to_pose')
        self.save = self.create_client(SaveMap,'/map_saver/save_map')
        self.serialize = self.create_client(SerializePoseGraph,'/slam_toolbox/serialize_map')
        self.history = []
        self.active_goal = None
        self.active_result = None
        self.pending_action = None
        self.retry = RetryBook(self.config['retry_cooldown'],self.config['max_attempts'],self.config['retry_radius'])
        self.report = {'state':'starting','map_output':str(self.output),'goals':[],
                       'reference_yaw_rad':self.config['reference_yaw_rad']}
        self.started = time.monotonic()
        self.started_ros = None
        self.wait_reason = None
        self.visited = []
        self.observations = []

    def receive_vendor_points(self, message):
        self.vendor_points = tuple((p.x, p.y) for p in message.points)
        self.vendor_received = time.monotonic()
        self.vendor_revision += 1

    def run_vendor_operation(self, operation):
        # Process startup/reaping may take seconds; keep TF/scan callbacks alive.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='vendor-process') as worker:
            future = worker.submit(operation)
            if not self.wait(future.done, 20., check_task=True, check_sensors=True):
                raise RuntimeError('厂家探索节点操作超时: '+str(self.wait_reason))
            return future.result()

    def prepare_managed_vendor(self, pose):
        from .vendor_runtime import VendorProcesses, bounds_changed, map_sampling_bounds
        bounds = map_sampling_bounds(self.latest_map.info)
        if self.vendor_initialized and not bounds_changed(self.vendor_map_bounds,bounds,self.latest_map.info.resolution):
            self.vendor_runtime.check()
            return
        if self.vendor_runtime is not None:
            previous, self.vendor_runtime = self.vendor_runtime, None
            self.run_vendor_operation(previous.stop)
            # Wait for old DDS endpoints to disappear before sending new five points.
            if not self.wait(lambda:self.boundary_pub.get_subscription_count() == 0 and
                             len(self.get_publishers_info_by_topic('/wheeltec_explore/vendor_points')) == 0,
                             10.,check_task=True,check_sensors=True):
                raise RuntimeError('旧厂家探索节点尚未退出')
        self.vendor_initialized = False
        self.vendor_points, self.vendor_received = (), None
        candidate = VendorProcesses()
        self.vendor_runtime = candidate
        # Linux parent-death notification follows the creating thread. Popen is
        # nonblocking; create the supervisor on this long-lived ROS thread.
        candidate.start()
        self.config['vendor_bounds'] = ','.join(str(v) for v in bounds)
        self.initialize_vendor(pose)
        self.vendor_map_bounds = bounds

    def initialize_vendor(self, pose):
        from geometry_msgs.msg import PointStamped
        try:
            bounds = [float(v) for v in self.config['vendor_bounds'].split(',')]
        except ValueError as exc:
            raise ValueError('Vendor bounds require xmin,ymin,xmax,ymax') from exc
        if (len(bounds) != 4 or not all(math.isfinite(v) for v in bounds) or
                bounds[0] >= bounds[2] or bounds[1] >= bounds[3] or
                not (bounds[0] <= pose[0] <= bounds[2] and bounds[1] <= pose[1] <= bounds[3])):
            raise ValueError('Invalid vendor bounds or start pose outside bounds')
        if not self.wait(lambda:self.boundary_pub.get_subscription_count() == 2 and
                         len(self.get_publishers_info_by_topic('/wheeltec_explore/vendor_boundary')) == 1 and
                         len(self.get_publishers_info_by_topic('/wheeltec_explore/vendor_points')) == 1,
                         self.config['initialization_timeout'],check_task=True,check_sensors=True):
            raise RuntimeError('Vendor RRT candidate nodes unavailable or topic ownership is ambiguous')
        xmin,ymin,xmax,ymax = bounds
        for x,y in ((xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax),pose[:2]):
            msg=PointStamped()
            msg.header.frame_id='map'
            msg.header.stamp=self.get_clock().now().to_msg()
            msg.point.x=float(x);msg.point.y=float(y)
            self.boundary_pub.publish(msg)
        self.vendor_initialized = True

    def plan_vendor_frontiers(self, pose):
        grid=self.grid()
        grid.data=tuple(grid.data)
        samples = (self.vendor_points if self.vendor_received is not None and
                   0 <= time.monotonic()-self.vendor_received <= self.config['vendor_max_age'] else ())
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='vendor-frontiers') as worker:
            future=worker.submit(safe_vendor_goals,grid,pose[:2],samples,self.config['robot_radius'],
                self.config['start_snap_distance'],self.config['frontier_approach_radius'],
                self.config['min_goal_distance'],tuple(self.visited),self.config['visited_radius'])
            if not self.wait(future.done,self.config['task_timeout'],check_task=True,check_sensors=True):
                future.cancel()
                raise RuntimeError('Vendor frontier validation stopped: '+self.wait_reason)
            goals=future.result()
        self.require_health()
        free_area=sum(0 <= value <= 25 for value in grid.data)*grid.resolution**2
        # Samples are not a full frontier inventory. Unknown metrics remain null.
        return FrontierResult(goals,free_area,None,None,None)

    def receive_scan(self,message):
        self.last_scan_ros = self.ros_seconds()
        self.health.scan(message.header.stamp.sec+message.header.stamp.nanosec/1e9,self.ros_seconds())

    def ros_seconds(self):
        return self.get_clock().now().nanoseconds/1e9

    def health_tick(self):
        now = self.ros_seconds()
        self.health.slam('slam_toolbox' in self.get_node_names())
        reference_issue = 'tf_missing'
        try:
            t = self.tf.lookup_transform(self.config['map_frame'],self.config['odom_frame'],Time())
            reference_issue = 'odom_tf_missing'
            odom = self.tf.lookup_transform(self.config['odom_frame'],self.config['base_frame'],Time())
            odom_stamp = odom.header.stamp.sec+odom.header.stamp.nanosec/1e9
            reference_issue = 'odom_tf_stale'
            if (odom_stamp > 0 and math.isfinite(odom_stamp) and
                    -self.config['future_tolerance'] <= now-odom_stamp <= self.config['tf_max_age']):
                v = t.transform.translation
                p = odom.transform.translation
                self.health.transform(t.header.stamp.sec+t.header.stamp.nanosec/1e9,
                                      now,(v.x,v.y,yaw(t.transform.rotation)),
                                      reference_xy=(p.x,p.y),reference_stamp=odom_stamp)
                reference_issue = None
        except TransformException:
            pass
        snapshot = self.health.snapshot(now)
        if reference_issue:
            snapshot['healthy'] = False
            snapshot['issues'] = sorted(set(snapshot['issues'])|{reference_issue})
        if self.health_active and not snapshot['healthy']:
            for issue in snapshot['issues']:
                self.health_latched.setdefault(issue,now)
        return snapshot

    def require_health(self):
        if self.vendor_initialized and self.vendor_runtime is not None:
            self.vendor_runtime.check()
        snapshot = self.health_tick()
        if self.health_latched or not snapshot['healthy']:
            raise MapUnstableError(','.join(sorted(set(snapshot['issues'])|set(self.health_latched))))
        return True

    def receive_map(self,message):
        self.latest_map = message
        self.map_updates += 1
        self.health.map(message.header.stamp.sec+message.header.stamp.nanosec/1e9,self.ros_seconds())

    def status(self,state,reason='',**values):
        self.report.update(state=state,reason=reason,**values)
        self.report['map_health'] = self.health.snapshot(self.ros_seconds())
        self.report['map_health']['latched_issues'] = self.health_latched.copy()
        self.report['elapsed_ros_seconds'] = (round(self.ros_seconds()-self.started_ros,2)
                                               if self.started_ros is not None else 0.)
        self.report['timeout_clock'] = 'ROS'
        self.report['parameters'] = self.config.copy()
        self.report['elapsed_wall_seconds'] = round(time.monotonic()-self.started,2)
        message = String(data=json.dumps(self.report,ensure_ascii=False))
        self.status_publisher.publish(message)
        atomic_json(self.output.with_suffix('.exploration.json'),self.report)
        entry = {'state':state,'reason':reason,'elapsed_wall_seconds':self.report['elapsed_wall_seconds']}
        self.history.append(entry)
        self.get_logger().info(json.dumps(entry,ensure_ascii=False))

    def wait(self,predicate,timeout,check_task=False,check_sensors=False):
        start = None
        self.wait_reason = None
        while rclpy.ok():
            now = self.ros_seconds()
            if now > 0:
                if start is None:
                    start = now
                if self.started_ros is None:
                    self.started_ros = now
                if check_task and now-self.started_ros >= self.config['task_timeout']:
                    self.wait_reason = 'task_timeout'
                    return False
                if now-start >= timeout:
                    self.wait_reason = 'wait_timeout'
                    return False
                if check_sensors:
                    self.require_health()
            rclpy.spin_once(self,timeout_sec=0.1)
            if predicate():
                return True
        self.wait_reason = 'shutdown'
        return False

    def position(self):
        try:
            transform = self.tf.lookup_transform(self.config['map_frame'],self.config['base_frame'],Time())
            stamp = transform.header.stamp.sec+transform.header.stamp.nanosec/1e9
            age = self.ros_seconds()-stamp
            if stamp <= 0 or not -self.config['future_tolerance'] <= age <= self.config['tf_max_age']:
                return None
            t = transform.transform
            pose = (t.translation.x,t.translation.y,yaw(t.rotation))
            return pose if all(math.isfinite(v) for v in pose) else None
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
        if not self.wait(accepted.done,self.config['goal_response_timeout']):
            raise RuntimeError('Nav2 did not respond to the goal request')
        handle = accepted.result()
        if handle is None or not handle.accepted:
            return False,'rejected'
        self.active_goal = handle
        result = handle.get_result_async()
        self.active_result = result
        pose = self.position()
        progress = (ObservationProgress(self.ros_seconds(),math.dist(pose[:2],(x,y)),
                                       self.map_updates,self.config,position=pose[:2]) if pose and not returning else None)
        local_reason = None
        sampled_revision = self.map_updates
        ratio = 0.
        def finished():
            nonlocal local_reason, sampled_revision, ratio
            if result.done():
                return True
            if progress is not None:
                current = self.position()
                if current is not None:
                    if self.map_updates != sampled_revision:
                        sampled_revision = self.map_updates
                        ratio = local_known_ratio(self.grid(),(x,y),self.config['local_observation_radius'])
                    local_reason = progress.update(self.ros_seconds(),math.dist(current[:2],(x,y)),
                                                   self.map_updates,ratio,position=current[:2])
            return local_reason is not None
        done = self.wait(finished,self.config['goal_timeout'],check_task=not returning,check_sensors=True)
        if not done or local_reason:
            reason = local_reason or self.wait_reason
            if not self.cancel_active():
                raise RuntimeError('Nav2 goal cancellation not confirmed')
            if local_reason:
                self.report.setdefault('local_observation_events',[]).append({
                    'target':[x,y], 'result':reason, 'known_ratio':ratio,
                    'radius_m':self.config['local_observation_radius'], 'map_revision':self.map_updates})
            return False,reason
        self.active_goal = None
        response = result.result()
        if response is None:
            return False,'no_result'
        return response.status==GoalStatus.STATUS_SUCCEEDED,str(response.status)

    def active_observe(self, pose, initial=False):
        """One bounded simulation observation; all motion stays in Nav2's Spin action."""
        assumed = startup_assumption_allowed(initial,self.config['initial_rotation_assumed_safe'],
                                             self.report.get('active_scans',[]),self.report.get('goals',[]))
        plan = choose_scan(self.grid(),pose,self.config['robot_radius'],
                           self.config['active_scan_angle_deg'],self.config['active_scan_fov_deg'],
                           assume_start_safe=assumed)
        event = dict(plan=plan,started_ros=self.ros_seconds(),motion_requested=False,
                     initial_assumption_used=assumed)
        self.report.setdefault('active_scans',[]).append(event)
        self.status('initial_observation' if initial else 'active_scan',plan['reason'])
        if plan['angle_rad'] is None:
            return False,('active_scan_clearance_unproven' if not plan['safe'] else 'active_scan_no_information_gain')
        if not self.wait(self.spin_action.server_is_ready,self.config['nav_server_timeout'],check_task=True,check_sensors=True):
            return False,'active_scan_server_unavailable'
        # Recheck after waiting: the map used for permission cannot be an old snapshot.
        fresh_pose = self.position()
        if fresh_pose is None or (not assumed and not rotation_clearance(self.grid(),fresh_pose,self.config['robot_radius'])['safe']):
            return False,'active_scan_clearance_lost'
        goal = Spin.Goal()
        goal.target_yaw = float(plan['angle_rad'])
        goal.time_allowance = Duration(seconds=self.config['active_scan_timeout']).to_msg()
        accepted = self.spin_action.send_goal_async(goal)
        self.pending_action = accepted
        abandoned = [False]
        def cancel_late(future):
            if abandoned[0]:
                handle = future.result()
                if handle is not None and handle.accepted:
                    handle.cancel_goal_async()
        accepted.add_done_callback(cancel_late)
        try:
            if not self.wait(accepted.done,self.config['goal_response_timeout'],check_task=True,check_sensors=True):
                raise RuntimeError('Active scan goal response timeout; simulation stack must be stopped')
        except BaseException:
            # Health exceptions and operator interruption also abandon this request.
            # cancel_active keeps spinning a bounded grace period for its response.
            abandoned[0] = True
            if accepted.done():
                cancel_late(accepted)
            raise
        handle = accepted.result()
        self.pending_action = None
        if handle is None or not handle.accepted:
            return False,'active_scan_rejected'
        self.active_goal = handle
        self.active_result = handle.get_result_async()
        event['motion_requested'] = True
        start_time = self.ros_seconds()
        previous = fresh_pose
        travelled = 0.
        reason = ''
        while rclpy.ok() and not self.active_result.done():
            rclpy.spin_once(self,timeout_sec=.05)
            self.require_health()
            current = self.position()
            if current is None:
                reason = 'active_scan_tf_unavailable'
                break
            travelled += math.atan2(math.sin(current[2]-previous[2]),math.cos(current[2]-previous[2]))
            previous = current
            if not assumed and not rotation_clearance(self.grid(),current,self.config['robot_radius'])['safe']:
                reason = 'active_scan_clearance_lost'
                break
            if self.ros_seconds()-start_time >= self.config['active_scan_timeout']:
                reason = 'active_scan_timeout'
                break
            if self.ros_seconds()-self.started_ros >= self.config['task_timeout']:
                reason = 'task_timeout'
                break
        event.update(observed_rotation_rad=travelled,elapsed_ros=self.ros_seconds()-start_time)
        if reason or not rclpy.ok():
            if not self.cancel_active():
                raise RuntimeError('Active scan cancellation not confirmed')
            event.update(success=False,reason=reason or 'shutdown')
            return False,reason or 'shutdown'
        result = self.active_result.result()
        self.active_goal = None
        self.active_result = None
        success = result is not None and result.status == GoalStatus.STATUS_SUCCEEDED
        event.update(success=success,reason='succeeded' if success else 'active_scan_failed')
        revision = self.map_updates
        if success and not self.wait(lambda:self.map_updates>revision,self.config['map_update_timeout'],check_task=True,check_sensors=True):
            return False,self.wait_reason or 'map_update_timeout'
        return success,event['reason']

    def save_map(self):
        self.status('saving','Saving occupancy grid and SLAM pose graph')
        if not self.wait(lambda:self.save.service_is_ready() and self.serialize.service_is_ready(),
                         self.config['goal_response_timeout'],check_sensors=True):
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
        if not self.wait(future.done,self.config['map_save_timeout'],check_sensors=True) or future.result() is None or not future.result().result:
            raise RuntimeError('Map saver could not write the occupancy map')
        request = SerializePoseGraph.Request(filename=str(self.output))
        future = self.serialize.call_async(request)
        if not self.wait(future.done,self.config['map_save_timeout'],check_sensors=True) or future.result() is None or future.result().result!=0:
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

    def wait_status_observers(self):
        expected = self.config['expected_status_observers']
        if not isinstance(expected,int) or expected < 0:
            raise ValueError('Nonnegative status observer count required')
        if expected == 0:
            return True
        return self.wait(lambda:self.status_publisher.get_subscription_count()>=expected,
                         self.config['initialization_timeout'])

    def check_vendor_full_map(self, pose, locally_observed_targets, deferred):
        """Determine task-wide exhaustion independently of a sampled batch."""
        result = self.plan_frontiers(pose)
        if not result.goals:
            return result, ''
        eligible = [g for g in result.goals if not any(
            math.dist((g.x,g.y),point) <= self.config['retry_radius'] for point in locally_observed_targets)]
        if not eligible:
            return result, 'local_observation_residuals'
        if all(self.retry.exhausted((g.x,g.y)) for g in eligible):
            return result, 'frontier_retries_exhausted'
        return result, 'wait_vendor'

    def plan_frontiers(self, pose):
        # Keep subscription, TF and health callbacks running during CPU work.
        # The worker uses an immutable input snapshot and never accesses ROS.
        grid = self.grid()
        grid.data = tuple(grid.data)
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='frontiers') as worker:
            future = worker.submit(select_frontiers,grid,pose[:2],self.config['robot_radius'],
                                              self.config['min_frontier_size'],visited=tuple(self.visited),observations=tuple(self.observations),
                                              **{key:self.config[key] for key in (
                                                  'min_goal_distance','visited_radius','observation_min_separation',
                                                  'frontier_approach_radius','start_snap_distance',
                                                  'distance_score_bias','score_distance_offset','frontier_viewpoint_strategy',
                                                  'viewpoint_candidate_budget','viewpoint_frontier_budget','footprint_exclusion_radius')})
            if not self.wait(future.done, self.config['task_timeout'],
                             check_task=True, check_sensors=True):
                future.cancel()
                raise RuntimeError('Frontier computation stopped: '+self.wait_reason)
            result = future.result()
        self.require_health()
        return result

    def run(self):
        self.status('starting','Waiting for SLAM map, robot transform and Nav2')
        if not self.wait_status_observers():
            raise RuntimeError('Required status observers did not match; no exploration started')
        if not self.wait(lambda:self.latest_map is not None and self.position() is not None
                         and observation_fresh(self.last_scan_ros,self.ros_seconds(),self.config['scan_max_age'])
                         and self.health_tick()['healthy'],self.config['initialization_timeout']):
            raise RuntimeError('Timed out waiting for SLAM map and map-to-base transform')
        if not self.wait(self.nav.server_is_ready,self.config['nav_server_timeout']):
            raise RuntimeError('Nav2 NavigateToPose action server is unavailable')
        self.health_active = True
        self.require_health()
        start = self.position()
        self.report['start_pose'] = list(start)
        if self.config['frontier_backend'] == 'vendor' and not self.vendor_initialized:
            if self.config['vendor_managed']:
                self.prepare_managed_vendor(start)
            else:
                self.initialize_vendor(start)
        if self.config['initial_rotation_assumed_safe'] and self.spin_action is not None:
            success, reason = self.active_observe(start,initial=True)
            if not success:
                self.status('incomplete',reason,map_saved=False,returned=False,
                            manual_intervention_required=True)
                return 2
        self.status('exploring','Selecting reachable frontiers')
        stable_empty, attempts, latest_result = 0,0,None
        forced_reason = ''
        locally_observed_targets = []
        deferred = None
        while rclpy.ok():
            self.require_health()
            if self.started_ros is not None and self.ros_seconds()-self.started_ros>=self.config['task_timeout']:
                forced_reason = 'task_timeout'
                break
            if attempts>=self.config['max_goals']:
                forced_reason = 'goal_limit'
                break
            pose = self.position()
            if pose is None:
                if not self.wait(lambda:self.position() is not None,self.config['map_update_timeout'],check_sensors=True):
                    raise RuntimeError('Robot localization transform was lost')
                continue
            if self.config['frontier_backend'] == 'vendor':
                if self.config['vendor_managed']:
                    self.prepare_managed_vendor(pose)
                latest_result = self.plan_vendor_frontiers(pose)
                if not latest_result.goals:
                    # Sampling silence is not completion: independently assess the map.
                    latest_result, full_reason = self.check_vendor_full_map(pose,locally_observed_targets,deferred)
                    if full_reason == 'wait_vendor':
                        self.status('exploring','Waiting for a fresh vendor frontier')
                        revision=self.vendor_revision
                        self.wait(lambda:self.vendor_revision != revision,self.config['retry_map_wait'],check_task=True,check_sensors=True)
                        continue
                    if full_reason:
                        forced_reason = full_reason
                        break
            else:
                latest_result = self.plan_frontiers(pose)
            self.report.update(known_free_area_m2=round(latest_result.known_free_area,3),
                               frontier_clusters=latest_result.frontier_clusters,
                               unreachable_clusters=latest_result.unreachable_clusters,
                               ignored_small_clusters=latest_result.ignored_small_clusters,
                               residual_counts=latest_result.residual_counts,
                               residual_frontiers=latest_result.residual_frontiers,
                               viewpoint_diagnostics=latest_result.viewpoint_diagnostics)
            eligible = [g for g in latest_result.goals if not any(
                math.dist((g.x,g.y),point) <= self.config['retry_radius'] for point in locally_observed_targets)]
            candidates = [g for g in eligible
                          if self.retry.available((g.x,g.y),self.ros_seconds())]
            if not candidates:
                if self.config['frontier_backend'] == 'vendor' and latest_result.goals:
                    # A filtered sample batch is not a complete frontier census.
                    # Inspect the whole map before inferring any terminal state.
                    latest_result, full_reason = self.check_vendor_full_map(pose,locally_observed_targets,deferred)
                    self.report.update(known_free_area_m2=round(latest_result.known_free_area,3),
                                       frontier_clusters=latest_result.frontier_clusters,
                                       unreachable_clusters=latest_result.unreachable_clusters,
                                       ignored_small_clusters=latest_result.ignored_small_clusters,
                                       residual_counts=latest_result.residual_counts,
                                       residual_frontiers=latest_result.residual_frontiers,
                                       viewpoint_diagnostics=latest_result.viewpoint_diagnostics)
                    if full_reason == 'wait_vendor':
                        self.status('exploring','Waiting for another vendor frontier')
                        revision=self.vendor_revision
                        self.wait(lambda:self.vendor_revision != revision,self.config['retry_map_wait'],check_task=True,check_sensors=True)
                        continue
                    if full_reason:
                        forced_reason = full_reason
                        break
                if (not latest_result.goals and self.spin_action is not None
                        and self.scan_budget.take()):
                    success, reason = self.active_observe(pose,initial=attempts==0)
                    if not success:
                        forced_reason = reason
                        self.report['manual_intervention_required'] = 'clearance' in reason
                        break
                    stable_empty = 0
                    continue
                if latest_result.goals:
                    if not eligible:
                        forced_reason = 'local_observation_residuals'
                        break
                    if all(self.retry.exhausted((g.x,g.y)) for g in eligible):
                        forced_reason = 'frontier_retries_exhausted'
                        break
                    self.status('exploring','Waiting before retrying blocked frontiers')
                    old_revision = self.map_updates
                    self.wait(lambda:self.map_updates>old_revision,self.config['retry_map_wait'],check_task=True,check_sensors=True)
                    continue
                stable_empty += 1
                if stable_empty>=self.config['stable_empty_maps']:
                    break
                old_revision = self.map_updates
                # Require fresh observations before concluding there is no target.
                if not self.wait(lambda:self.map_updates>old_revision,self.config['map_update_timeout'],check_task=True,check_sensors=True):
                    if self.wait_reason == 'task_timeout':
                        forced_reason = 'task_timeout'
                        break
                    raise MapUnstableError('map_update_timeout')
                continue
            stable_empty = 0
            target = candidates[0]
            self.status('exploring','Navigating to a frontier approach',target=[target.x,target.y])
            attempts += 1
            success,reason = self.navigate(target.x,target.y,target.yaw)
            self.report['goals'].append({'target':[target.x,target.y], 'success':success, 'result':reason})
            if success or reason == 'locally_observed':
                if success:
                    self.visited.append((target.x,target.y))
                else:
                    locally_observed_targets.append((target.x,target.y))
                observed = self.position()
                if observed is not None:
                    self.visited.append(observed[:2])
                    if observation_fresh(self.last_scan_ros,self.ros_seconds(),self.config['scan_max_age']):
                        self.observations.append((*observed[:2],self.map_updates))
            else:
                self.retry.failed((target.x,target.y),self.ros_seconds())
            old_revision = self.map_updates
            if not self.wait(lambda:self.map_updates>old_revision,self.config['map_update_timeout'],check_task=True,check_sensors=True):
                if self.wait_reason == 'task_timeout':
                    forced_reason = 'task_timeout'
                    break
                raise MapUnstableError('map_update_timeout')
        if latest_result is None:
            raise RuntimeError('No valid occupancy grid was processed')
        self.require_health()
        saved = self.save_map()
        self.status('returning','Returning to the exploration start position')
        current = self.position()
        if current is not None and math.dist(current[:2],start[:2])<=self.config['return_tolerance']:
            returned = True
        else:
            returned,_ = self.navigate(*start,returning=True)
        self.require_health()
        unresolved = 1 if forced_reason else 0
        final = completion_state(latest_result.known_free_area,latest_result.unreachable_clusters,
                                 unresolved,saved,returned,self.config['minimum_free_area'],
                                 residual_clusters=sum(latest_result.residual_counts.get(k, 0) for k in
                                                       ('footprint_excluded','multiview_observed')))
        reason = (forced_reason or ('no_reachable_frontiers' if final in ('completed','completed_with_residual_frontiers') else
                                   'remaining_unreachable_frontiers_or_insufficient_observed_area'))
        if not returned:
            reason = 'return_to_start_failed'
        self.status(final,reason,map_saved=saved,returned=returned,
                    completion_criteria={'stable_empty_maps':stable_empty,
                    'minimum_free_area_m2':self.config['minimum_free_area'],
                    'no_unreachable_clusters':(None if latest_result.unreachable_clusters is None else latest_result.unreachable_clusters==0)},history=self.history[:])
        self.wait(lambda:False,0.5)
        return 0 if final in ('completed','completed_with_residual_frontiers') else 2

    def cancel_active(self):
        pending = getattr(self,'pending_action',None)
        if pending is not None:
            if not self.wait(pending.done,self.config['cancel_response_timeout']):
                self.get_logger().error('Pending Spin response not confirmed; simulation stack must be stopped')
                return False
            handle = pending.result()
            self.pending_action = None
            if handle is not None and handle.accepted:
                self.active_goal = handle
                self.active_result = handle.get_result_async()
        if self.active_goal is not None:
            future = self.active_goal.cancel_goal_async()
            acknowledged = self.wait(future.done,self.config['cancel_response_timeout'])
            terminal = self.active_result is not None and self.wait(self.active_result.done,self.config['cancel_result_timeout'])
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
        if os.environ.get('WHEELTEC_CONSOLE_START_GATE'):
            # Warm subscriptions/action discovery while the console holds stop.
            if not node.wait(lambda: node.latest_map is not None and node.position() is not None
                             and observation_fresh(node.last_scan_ros, node.ros_seconds(), node.config['scan_max_age'])
                             and node.nav.server_is_ready(), node.config['initialization_timeout']):
                raise RuntimeError('Console preparation timed out; no navigation released')
            if node.config['frontier_backend'] == 'vendor' and node.config['vendor_managed']:
                node.prepare_managed_vendor(node.position())
            wait_for_console_start(lambda: rclpy.spin_once(node, timeout_sec=.02))
        code = node.run()
    except KeyboardInterrupt:
        node.cancel_active()
        node.status('failed','operator_interrupted')
        code = 130
    except MapUnstableError as error:
        node.cancel_active()
        node.status('map_unstable',str(error),map_saved=False,returned=False)
        code = 2
    except Exception as error:
        node.cancel_active()
        node.status('failed',str(error))
    finally:
        if node.vendor_runtime is not None:
            node.vendor_runtime.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__=='__main__':
    raise SystemExit(main())