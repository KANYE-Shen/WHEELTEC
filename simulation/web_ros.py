"""ROS subscribers and Nav2 actions for the isolated browser simulator."""
from collections import deque
import math
from pathlib import Path
import sys
import time

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import ComputePathToPose, NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
import rclpy
from rclpy.action import ActionClient
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformException, TransformListener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'console/target'))
from data import finite_ranges, fresh_measurement, grid_payload


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def stamp_of(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9


class RosSession:
    def __init__(self, mode, check_goal_cell):
        self.context = Context()
        rclpy.init(args=[], context=self.context)
        self.node = rclpy.create_node('wheeltec_web_simulation', context=self.context,
                                      parameter_overrides=[Parameter('use_sim_time', value=True)])
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.node)
        self.tf = Buffer(node=self.node)
        self.listener = TransformListener(self.tf, self.node)
        self.mode = mode
        self.check_goal_cell = check_goal_cell
        self.map = None
        self.map_time = None
        self.geometry = None
        self.geometry_revision = 0
        self.scans = deque(maxlen=8)
        self.costmap = None
        self.costmap_time = 0.
        self.odom = None
        self.odom_time = 0.
        self.goal = None
        self.future = None
        self.handle = None
        self.goal_revision = None
        self.stage = ''
        self.deadline = 0.
        self.failure = None
        self.waiting_for = ['ROS discovery']
        self.last_state = {}
        self.checks = {}
        self.next_check = 0.
        self.initial_pose_attempts = 0
        self.next_initial_pose = 0.
        self.node.create_subscription(OccupancyGrid, '/map', self.read_map,
                                      QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.node.create_subscription(LaserScan, '/scan', self.read_scan, qos_profile_sensor_data)
        self.node.create_subscription(Odometry, '/odom', self.read_odom, qos_profile_sensor_data)
        self.node.create_subscription(OccupancyGrid, '/global_costmap/costmap', self.read_costmap,
                                      QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.initial_pose = self.node.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
        self.nav_nodes = ('bt_navigator', 'planner_server', 'controller_server')
        observed = (*self.nav_nodes, 'amcl') if mode == 'localization' else self.nav_nodes
        self.lifecycle = {name: self.node.create_client(GetState, f'/{name}/get_state') for name in observed}
        self.plan = ActionClient(self.node, ComputePathToPose, 'compute_path_to_pose')
        self.navigate = ActionClient(self.node, NavigateToPose, 'navigate_to_pose')

    def read_map(self, msg):
        meta = msg.info
        origin = [meta.origin.position.x, meta.origin.position.y, yaw_of(meta.origin.orientation)]
        if msg.header.frame_id != 'map' or meta.resolution <= 0 or not all(map(math.isfinite, origin)):
            return
        try:
            data = grid_payload(meta.width, meta.height, msg.data)
        except ValueError:
            return
        revision = 1 if self.map is None else self.map['revision'] + 1
        geometry = (msg.header.frame_id, meta.width, meta.height, meta.resolution, *origin)
        if geometry != self.geometry:
            self.geometry, self.geometry_revision = geometry, revision
        self.map = {'revision': revision, 'frame': msg.header.frame_id, 'width': meta.width,
                    'height': meta.height, 'resolution': meta.resolution, 'origin': origin, 'data': data}
        self.map_time = (stamp_of(msg), time.monotonic())

    def read_scan(self, msg):
        self.scans.append((msg, time.monotonic()))

    def read_odom(self, msg):
        self.odom = msg
        self.odom_time = time.monotonic()

    def read_costmap(self, msg):
        self.costmap = msg
        self.costmap_time = time.monotonic()

    def transform(self, frame, stamp=Time()):
        try:
            msg = self.tf.lookup_transform('map', frame, stamp)
        except TransformException:
            return None
        p, q = msg.transform.translation, msg.transform.rotation
        return {'frame': 'map', 'x': p.x, 'y': p.y, 'yaw': yaw_of(q), 'stamp': stamp_of(msg)}

    def telemetry(self, now, wall):
        pose = self.transform('base_link')
        # SLAM and AMCL can both future-date map → odom, while this composed
        # transform is bounded by the latest odom sample.
        if pose and not (-1 <= now - pose['stamp'] <= 1):
            pose = None
        for msg, received in reversed(self.scans):
            if not fresh_measurement(stamp_of(msg), now, received, wall, 1.):
                continue
            laser_pose = self.transform(msg.header.frame_id, Time.from_msg(msg.header.stamp))
            if laser_pose is not None:
                return pose, laser_pose, {
                    'frame': msg.header.frame_id, 'angle_min': msg.angle_min,
                    'angle_increment': msg.angle_increment, 'range_min': msg.range_min,
                    'range_max': msg.range_max,
                    'ranges': finite_ranges(msg.ranges, msg.range_min, msg.range_max),
                }
        return pose, None, None

    def nav_active(self, wall):
        for name, (future, started) in list(self.checks.items()):
            if future.done():
                state = future.result()
                self.last_state[name] = (state is not None and state.current_state.label == 'active', wall)
                del self.checks[name]
            elif wall - started > 2:
                self.lifecycle[name].remove_pending_request(future)
                del self.checks[name]
        if wall >= self.next_check:
            self.next_check = wall + .5
            for name, client in self.lifecycle.items():
                if name not in self.checks and client.service_is_ready():
                    self.checks[name] = (client.call_async(GetState.Request()), wall)
        return all(self.node_active(name, wall) for name in self.nav_nodes)

    def node_active(self, name, wall):
        active, checked = self.last_state.get(name, (False, 0.))
        return active and wall - checked <= 2

    def tick(self):
        # /clock, /tf, scan, and odometry can each arrive before the next
        # stdio request. Drain a bounded batch to keep the ROS clocks aligned.
        for _ in range(32):
            self.executor.spin_once(timeout_sec=0.)
        wall = time.monotonic()
        now = self.node.get_clock().now().nanoseconds / 1e9
        active = self.nav_active(wall)
        if (self.mode == 'localization' and self.node_active('amcl', wall) and self.map and now > 0
                and self.initial_pose_attempts < 5 and wall >= self.next_initial_pose
                and self.initial_pose.get_subscription_count() > 0):
            try:
                odom_stamp = self.tf.lookup_transform('odom', 'base_link', Time()).header.stamp
            except TransformException:
                odom_stamp = None
            if odom_stamp and self.transform('base_link') is None:
                # Map origin is the original SLAM start. The associated scene
                # and spawn were restored by room_session; initialize AMCL there.
                msg = PoseWithCovarianceStamped()
                msg.header.frame_id = 'map'
                msg.header.stamp = odom_stamp
                msg.pose.pose.orientation.w = 1.
                msg.pose.covariance[0] = msg.pose.covariance[7] = .1
                msg.pose.covariance[35] = .05
                self.initial_pose.publish(msg)
                self.initial_pose_attempts += 1
                self.next_initial_pose = wall + .5
        pose, laser_pose, scan = self.telemetry(now, wall)
        map_fresh = bool(self.map_time) and (self.mode == 'localization' or
                                            fresh_measurement(self.map_time[0], now, self.map_time[1], wall, 15.))
        self.waiting_for = [name for name, available in (
            ('active Nav2 nodes', active), ('map', map_fresh), ('map pose', pose),
            ('time-aligned scan', scan), ('navigation action', self.navigate.server_is_ready()),
            ('planner action', self.plan.server_is_ready())) if not available]
        self.ready = not self.waiting_for
        self.latest = {'map': self.map, 'pose': pose, 'laser_pose': laser_pose, 'scan': scan,
                       'navigation_ready': self.ready, 'odom': self.odometry(now, wall)}
        self.advance_goal(wall)

    def snapshot(self):
        return dict(getattr(self, 'latest', {'navigation_ready': False}), goal=self.goal)

    def stationary(self):
        if not getattr(self, 'ready', False):
            return False
        if self.goal and self.goal['status'] in ('pending', 'active', 'canceling'):
            return False
        odom = self.latest.get('odom')
        return bool(odom and abs(odom['linear']) < .02 and abs(odom['angular']) < .05)

    def odometry(self, now, wall):
        if self.odom is None or not fresh_measurement(stamp_of(self.odom), now, self.odom_time, wall, 1.):
            return None
        twist = self.odom.twist.twist
        return {'linear': math.hypot(twist.linear.x, twist.linear.y), 'angular': twist.angular.z,
                'frame': self.odom.header.frame_id}

    def goal_pose(self):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.node.get_clock().now().to_msg()
        pose.pose.position.x, pose.pose.position.y = self.goal['x'], self.goal['y']
        pose.pose.orientation.z = math.sin(self.goal['yaw'] / 2)
        pose.pose.orientation.w = math.cos(self.goal['yaw'] / 2)
        return pose

    def start_goal(self, x, y, yaw, revision):
        self.goal = {'x': x, 'y': y, 'yaw': yaw, 'status': 'pending',
                     'message': 'Checking route with Nav2'}
        self.goal_revision = revision
        request = ComputePathToPose.Goal()
        request.goal = self.goal_pose()
        self.stage = 'plan_accept'
        self.future = self.plan.send_goal_async(request)
        self.deadline = time.monotonic() + 10
        return self.goal

    def cancel_goal(self):
        if self.goal['status'] != 'canceling':
            self.goal.update(status='canceling', message='Waiting for Nav2 to confirm cancellation')
            self.deadline = time.monotonic() + 8
            if self.handle is not None:
                self.handle.cancel_goal_async()
        return self.goal

    def finish(self, status, message):
        self.goal.update(status=status, message=message)
        self.future = self.handle = None
        self.stage = ''

    def plan_rejection(self, wall):
        pose, costmap = self.latest['pose'], self.costmap
        if (pose and costmap and costmap.header.frame_id == 'map'
                and costmap.info.resolution > 0 and wall - self.costmap_time <= 2.):
            info = costmap.info
            origin = info.origin.position
            for point, label in ((pose, 'Robot start'), (self.goal, 'Goal')):
                ix = math.floor((point['x'] - origin.x) / info.resolution)
                iy = math.floor((point['y'] - origin.y) / info.resolution)
                if (0 <= ix < info.width and 0 <= iy < info.height
                        and costmap.data[iy * info.width + ix] >= 99):
                    return label + ' is too close to an obstacle in the Nav2 costmap'
        return 'Nav2 found no path through known free space'

    def advance_goal(self, wall):
        if self.future is None:
            return
        canceling = self.goal['status'] == 'canceling'
        if not self.future.done():
            if wall >= self.deadline:
                if canceling:
                    self.failure = 'Navigation cancellation did not reach a terminal state'
                else:
                    self.cancel_goal()
            return
        result = self.future.result()
        if self.stage in ('plan_accept', 'nav_accept'):
            if result is None or not result.accepted:
                self.finish('canceled' if canceling else 'rejected',
                            'Goal canceled' if canceling else 'Nav2 did not accept the request')
                return
            self.handle = result
            self.future = result.get_result_async()
            planning = self.stage == 'plan_accept'
            self.stage = 'plan_result' if planning else 'nav_result'
            if canceling:
                self.handle.cancel_goal_async()
            elif not planning:
                self.goal.update(status='active', message='Navigating in Gazebo')
                self.deadline = wall + 360
            return
        code = result.status
        if self.stage == 'plan_result':
            if canceling:
                self.finish('canceled', 'Goal canceled before navigation')
            elif code != GoalStatus.STATUS_SUCCEEDED or not result.result.path.poses:
                self.finish('rejected', self.plan_rejection(wall))
            elif not self.ready or self.goal_revision < self.geometry_revision:
                self.finish('rejected', 'Simulation map geometry or readiness changed; select the goal again')
            else:
                x, y = self.goal['x'], self.goal['y']
                try:
                    self.check_goal_cell(self.map, x, y)
                except ValueError as exc:
                    self.finish('rejected', str(exc))
                    return
                endpoint = result.result.path.poses[-1].pose.position
                if math.hypot(endpoint.x - x, endpoint.y - y) > self.map['resolution'] * math.sqrt(2):
                    self.finish('rejected', 'Nav2 planned to a different cell')
                    return
                request = NavigateToPose.Goal()
                request.pose = self.goal_pose()
                self.future = self.navigate.send_goal_async(request)
                self.stage, self.handle, self.deadline = 'nav_accept', None, wall + 10
            return
        if code == GoalStatus.STATUS_SUCCEEDED:
            self.finish('succeeded', 'Nav2 reached the goal')
        elif code == GoalStatus.STATUS_CANCELED:
            self.finish('canceled', 'Nav2 confirmed cancellation')
        else:
            self.finish('aborted', 'Nav2 ended navigation without reaching the goal')

    def close(self):
        self.executor.shutdown()
        self.plan.destroy()
        self.navigate.destroy()
        self.listener.unregister()
        self.node.destroy_node()
        self.context.try_shutdown()
