"""Target-side ROS adapter. Uses an existing ROS stack; explicit task requests may start the existing explorer.
Run from repository root: python3 -m console.target.adapter --help
"""
import argparse
import subprocess
import json
import math
import os
import secrets
import sys
import threading
import time
from collections import deque
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from console.settings import CONTROL
from console.backend.policy import Lease, simulation_authorized, ArmHandshake, takeover_blocker, manual_command_blocker, require_control_epoch
from .tasks import TaskController, wait_for_stable_readiness
from .tf_buffer import TransformReceiptTracking
from .diagnostics import tf_failure_context, write_task_stop
from .data import finite_ranges, grid_payload, jpeg_from_image, fresh_measurement, tf_chain_fresh, camera_reception, distinct_receive_hz


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--kind', choices=['robot', 'simulation'], required=True)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--scan-topic', default='/scan')
    parser.add_argument('--camera-topic', default='/image_raw')
    parser.add_argument('--map-topic', default='/map')
    parser.add_argument('--odom-topic', default='/odom')
    parser.add_argument('--base-frame', default='base_link')
    parser.add_argument('--map-frame', default='map')
    parser.add_argument('--enable-simulation-control', action='store_true')
    parser.add_argument('--robot-config', type=Path)
    parser.add_argument('--mapping-runtime', type=Path, help='Owned mapper receipt for stopped-only map Reset')
    parser.add_argument('--gate', type=int, choices=[1, 2, 3], default=1)
    args, ros_args = parser.parse_known_args()
    import platform
    if args.enable_simulation_control and not simulation_authorized(os.environ, platform.machine()):
        parser.error(
            'Simulation control is restricted to the named x86 WSL distro with localhost-only ROS')
    if args.kind == 'robot' and args.enable_simulation_control:
        parser.error('Simulation control cannot target a robot')
    if not args.token_file.exists():
        args.token_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.token_file, os.O_CREAT |
                     os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_urlsafe(32))
    if args.token_file.stat().st_mode & 0o077:
        parser.error('Token file must have permissions 0600')
    token = args.token_file.read_text().strip()
    if len(token) < 32:
        parser.error('Token must contain at least 32 characters')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'robot'))
    from safety import MotionGate
    real_config = None
    if args.robot_config:
        if args.kind != 'robot':
            parser.error('Robot configuration is for robot mode only')
        from preflight import validate_runtime as validate
        real_config = validate(json.loads(
            args.robot_config.read_text()), required_gate=args.gate)
    if real_config:
        args.scan_topic = real_config['scan_topic']
        args.odom_topic = real_config['odom_topic']
        args.base_frame = real_config['base_frame']
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from rclpy.clock import Clock, ClockType
    from sensor_msgs.msg import LaserScan, Image, CompressedImage
    from nav_msgs.msg import OccupancyGrid, Odometry
    if real_config:
        from slam_toolbox.srv import SerializePoseGraph
        from nav2_msgs.srv import ClearEntireCostmap
    from geometry_msgs.msg import Twist
    from std_msgs.msg import Empty, String, Bool, Int8
    from std_srvs.srv import SetBool
    from rcl_interfaces.msg import Log
    from tf2_ros import Buffer, TransformListener
    rclpy.init(args=ros_args)

    class TrackedBuffer(TransformReceiptTracking, Buffer):
        pass

    class Adapter(Node):
        def __init__(self):
            super().__init__('wheeltec_console_adapter')
            self.lock = threading.RLock()
            self.lease = Lease()
            self.handshake = ArmHandshake()
            self.last_arm_attempt = 0.
            self.motion = MotionGate(
                CONTROL['command_timeout_s'], CONTROL['operator_timeout_s'], CONTROL['max_linear_m_s'], CONTROL['max_yaw_rad_s'])
            self.steady = Clock(clock_type=ClockType.STEADY_TIME)
            self.latest = {}
            self.received = {}
            self.stamps = {}
            self.history = {}
            self.logs = deque([{'id': 0, 'stamp': time.time(), 'level': 20, 'name': 'console.adapter', 'message': 'Adapter started; control requires explicit ownership'}], maxlen=400)
            self.image = None
            self.seq = 0
            self.frame = ''
            self.scan_frame = ''
            self.gear = 1
            self.manual_epoch = None
            self.remote_barrier = None
            self.nav_busy = False
            self.selection_mode = None
            self.selection_time = 0.
            self.robot_status = None
            self.robot_status_time = 0
            self.robot_status_revision = 0
            self.block = 'read_only'
            self.requested = (0., 0.)
            self.actual = (0., 0.)
            self.last_image = 0.
            self.last_tf = 0.
            self.map_revision = 0
            self.map_min_stamp = 0.
            self.tf_edges = {}
            self.tf_history = {}
            self.task_run_dir = None
            self.tf_error = None
            self.tf = TrackedBuffer(on_transform=self.tf_received, receipt_lock=self.lock)
            # Keep a short dynamic queue: display work must not drain seconds of old TF.
            # Ten messages retain interleaved map/odom updates; static TF stays latched.
            self.listener = TransformListener(self.tf, self, qos=QoSProfile(
                depth=10, durability=DurabilityPolicy.VOLATILE,
                reliability=ReliabilityPolicy.RELIABLE))
            self.subs = [self.create_subscription(LaserScan, args.scan_topic, self.scan, qos_profile_sensor_data),
                         self.create_subscription(OccupancyGrid, args.map_topic, self.map, QoSProfile(
                             depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)),
                         self.create_subscription(
                             Odometry, args.odom_topic, self.odom, qos_profile_sensor_data),
                         self.create_subscription(
                             Image, args.camera_topic, self.camera, qos_profile_sensor_data),
                         self.create_subscription(
                             CompressedImage, args.camera_topic+'/compressed', self.compressed, qos_profile_sensor_data),
                         self.create_subscription(
                             Log, '/rosout', self.log, 50),
                         self.create_subscription(String, '/safety/status', self.safety, 1)]
            self.allowed = args.enable_simulation_control or real_config is not None
            if self.allowed:
                topic = '/cmd_vel' if args.kind == 'simulation' else '/safety/manual_cmd_vel'
                self.command_topic = topic
                self.pub = self.create_publisher(Twist, topic, 1)
                if real_config:
                    self.heartbeat = self.create_publisher(
                        Empty, '/safety/operator_heartbeat', 1)
                    self.arm = self.create_client(SetBool, '/safety/arm')
                    self.selection = self.create_publisher(String, '/safety/command_source', 10)
                    self.selection_sub = self.create_subscription(String, '/safety/selected_source', self.selected, 1)
                    self.gear_pub = self.create_publisher(Int8, '/safety/gear', 10)
                    self.autonomy_source = self.create_client(SetBool, '/safety/select_autonomy')
                    from action_msgs.srv import CancelGoal
                    from rclpy.action import ActionClient
                    from nav2_msgs.action import NavigateToPose
                    self.nav = ActionClient(self, NavigateToPose, '/navigate_to_pose')
                    self.cancel_nav = self.create_client(CancelGoal, '/navigate_to_pose/_action/cancel_goal')
                    from action_msgs.msg import GoalStatusArray
                    self.nav_status_sub = self.create_subscription(GoalStatusArray, '/navigate_to_pose/_action/status',
                        lambda m: setattr(self, 'nav_busy', any(x.status in (1, 2, 3) for x in m.status_list)),
                        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE))
            self.tasks = TaskController(self.explore_preflight, self.activate_exploration, self.spawn_exploration, self.stop_exploration)
            from .mapping import MapReset
            self.map_reset = MapReset(self.tasks.remote, self.perform_map_reset)
            self.map_serializer = self.create_client(SerializePoseGraph, '/slam_toolbox/serialize_map') if real_config else None
            self.clear_costmaps = [self.create_client(ClearEntireCostmap, path) for path in
                ('/global_costmap/clear_entirely_global_costmap', '/local_costmap/clear_entirely_local_costmap')] if real_config else []
            self.timer = self.create_timer(
                CONTROL['tick_s'], self.tick, clock=self.steady)

        def explore_preflight(self):
            if self.map_reset.busy:
                raise ValueError('地图正在重置，请等待完成')
            if real_config is None:
                raise ValueError('实车控制链尚未配置，未执行探索启动；需要可用的最终看门狗和真实硬件配置')
            from preflight import validate_runtime as validate
            validate(json.loads(args.robot_config.read_text()), required_gate=3)
            if not (Path(__file__).resolve().parents[2]/'src/wheeltec_explore/wheeltec_explore/node.py').is_file():
                raise ValueError('车端缺少现有 wheeltec_explore 算法包')
            # Live readiness is checked continuously by the startup worker while
            # the source is held and the final watchdog is still disarmed.

        def exploration_readiness(self):
            with self.lock:
                reason = self.blockers()
                if reason:
                    if reason == 'tf_stale' and self.tf_error:
                        return reason+': '+json.dumps(self.tf_error, ensure_ascii=False)
                    return reason
                if not self.nav.server_is_ready():
                    return '车端 Nav2 未就绪'
                if not self.fresh('map', 15.):
                    return '实时地图未就绪'
                if not self.transform(args.map_frame, args.base_frame):
                    return '定位 TF 未就绪：'+json.dumps(self.tf_error, ensure_ascii=False)
                return None

        def select_gear(self, gear):
            if type(gear) is not int or gear not in (0, 1, 2):
                raise ValueError('挡位只能为低、中、高三挡')
            self.gear = gear
            if real_config:
                self.gear_pub.publish(Int8(data=gear))

        def stop_exploration(self):
            with self.lock:
                self.hold('software_stop')
                if real_config and self.autonomy_source.service_is_ready():
                    request = SetBool.Request(); request.data = False
                    self.remote_barrier = self.autonomy_source.call_async(request)
                if real_config and self.cancel_nav.service_is_ready():
                    from action_msgs.srv import CancelGoal
                    self.cancel_nav.call_async(CancelGoal.Request())

        def activate_exploration(self, current):
            def wait(predicate, message, seconds=1.5):
                deadline = time.monotonic()+seconds
                while current() and time.monotonic()<deadline:
                    if predicate():
                        return
                    time.sleep(.02)
                raise ValueError(message if current() else '启动已取消')
            with self.lock:
                if not current():
                    return
                self.hold('mode_transition')
                self.select_gear(1)
                self.heartbeat.publish(Empty())
            if self.cancel_nav.service_is_ready():
                from action_msgs.srv import CancelGoal
                self.nav_busy = True
                future = self.cancel_nav.call_async(CancelGoal.Request())
                wait(future.done, '取消旧导航目标未应答')
                response = future.result()
                if response is None or response.return_code != 0:
                    raise ValueError('旧导航目标取消失败，未启动探索')
                if response.goals_canceling:
                    wait(lambda: not self.nav_busy, '旧导航目标仍在停止')
            wait(lambda: self.selection_mode == 'hold' and self.robot_status is not None
                 and self.robot_status.get('armed') is False, '未收到最终停车确认')
            wait_for_stable_readiness(current, self.exploration_readiness)
            with self.lock:
                if not current():
                    return
                request = SetBool.Request(); request.data = True
                future = self.autonomy_source.call_async(request)
            wait(future.done, '自主速度通道未应答')
            if not future.result().success:
                raise ValueError('自主速度通道拒绝切换')
            wait(lambda: self.selection_mode == 'autonomy', '未收到自主速度源确认')
            with self.lock:
                if not current():
                    return
                self.heartbeat.publish(Empty())
                request = SetBool.Request(); request.data = True
                self.arm.call_async(request)
            wait(lambda: self.robot_status is not None and self.robot_status.get('armed') is True,
                 '最终看门狗未解锁，未启动探索')

        def spawn_exploration(self):
            from preflight import planning_geometry, calibrated_geometry
            root = Path(__file__).resolve().parents[2]
            profile = json.loads(Path(real_config['calibration_file']).read_text())
            _, _, radius = planning_geometry(profile, real_config)
            _, exclusion_radius = calibrated_geometry(profile)
            run = args.token_file.parent/'tasks'/str(time.time_ns())
            run.mkdir(parents=True, mode=0o700)
            env = os.environ.copy()
            env['PYTHONPATH'] = str(root/'src/wheeltec_explore')+os.pathsep+env.get('PYTHONPATH', '')
            command = [sys.executable, '-m', 'wheeltec_explore.node', '--ros-args',
                '-p', 'use_sim_time:=false', '-p', 'base_frame:='+args.base_frame,
                '-p', 'odom_frame:='+real_config['odom_frame'], '-p', 'robot_radius:='+str(radius),
                '-p', 'footprint_exclusion_radius:='+str(exclusion_radius),
                '-p', 'map_output:='+str(run/'room'), '-p', 'update_latest:=false']
            with (run/'explore.log').open('wb') as log:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                    stderr=subprocess.STDOUT, env=env, start_new_session=True)
                self.task_run_dir = run
                return process

        def reset_map_guard(self):
            with self.lock:
                process = self.tasks.process
                odom = self.latest.get('odom', {})
                if (self.tasks.mode != 'remote' or self.lease.owner is not None or
                        time.monotonic()-self.robot_status_time > .5 or
                        (self.robot_status or {}).get('armed', True) or
                        self.selection_mode != 'hold' or time.monotonic()-self.selection_time > .5 or
                        any(abs(v) > 1e-6 for v in self.actual) or not self.fresh('odom') or
                        abs(odom.get('linear', 1.)) > .001 or abs(odom.get('angular', 1.)) > .001 or
                        self.nav_busy or (process is not None and process.poll() is None)):
                    raise ValueError('地图重置等待新鲜停车确认、导航和探索完全退出')

        def perform_map_reset(self):
            from .mapping import owned_mapper, restart_mapper
            import hashlib
            receipt = args.mapping_runtime
            if receipt is None or not receipt.is_file():
                raise ValueError('未配置独立建图进程，地图未清空')
            deadline = time.monotonic()+8.
            while True:
                try:
                    self.reset_map_guard()
                    break
                except ValueError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.05)
            owned_mapper(receipt)
            archive = receipt.parent/'map-resets'/str(time.time_ns())
            archive.mkdir(parents=True)
            with self.lock:
                (archive/'map-before.json').write_text(json.dumps(self.latest.get('map')))
            if not self.map_serializer.wait_for_service(timeout_sec=5.):
                raise ValueError('旧图备份服务不可用，保留原地图')
            req = SerializePoseGraph.Request()
            req.filename = str(archive/'previous-map')
            future = self.map_serializer.call_async(req)
            deadline = time.monotonic()+35.
            while not future.done():
                self.reset_map_guard()
                if time.monotonic() >= deadline:
                    raise ValueError('旧图备份超时，保留原地图')
                time.sleep(.05)
            if future.exception() or future.result() is None or future.result().result != 0:
                raise ValueError('旧图备份失败，保留原地图')
            files = [archive/'previous-map.posegraph', archive/'previous-map.data']
            if not all(p.is_file() and p.stat().st_size > 0 for p in files):
                raise ValueError('旧图备份不完整，保留原地图')
            (archive/'manifest.json').write_text(json.dumps({
                p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in files}, indent=2))
            import yaml
            config = yaml.safe_load((Path(__file__).resolve().parents[2]/'robot/config/slam.yaml').read_text())
            config['slam_toolbox']['ros__parameters'].update(base_frame=real_config['base_frame'],
                odom_frame=real_config['odom_frame'], scan_topic=real_config['scan_topic'])
            restart_mapper(receipt, archive, self.reset_map_guard, config)
            with self.lock:
                self.map_min_stamp = time.time()
                for store in (self.latest, self.stamps, self.received, self.history):
                    store.pop('map', None)
                self.tf.clear()
                self.tf_edges = {edge: value for edge, value in self.tf_edges.items() if edge[0] != args.map_frame}
                self.map_revision += 1
            deadline = time.monotonic()+25.
            while True:
                self.reset_map_guard()
                with self.lock:
                    ready = self.fresh('map', 15.) and self.transform(args.map_frame, args.base_frame) is not None
                if ready:
                    break
                if time.monotonic() >= deadline:
                    raise ValueError('旧图已备份并清空，新图或定位尚未就绪；保持停车')
                time.sleep(.05)
            for client in self.clear_costmaps:
                if not client.wait_for_service(timeout_sec=3.):
                    raise ValueError('新图已生成，但导航代价图清理服务未就绪')
                future = client.call_async(ClearEntireCostmap.Request())
                deadline = time.monotonic()+5.
                while not future.done() and time.monotonic() < deadline:
                    self.reset_map_guard()
                    time.sleep(.05)
                if not future.done() or future.exception() or future.result() is None:
                    raise ValueError('新图已生成，但导航代价图清理未确认')
            self.reset_map_guard()

        def task_control(self, request):
            action = request.get('action')
            if action == 'reset_map':
                if real_config is None or args.mapping_runtime is None:
                    raise ValueError('当前对象未配置车端地图 Reset')
                return self.map_reset.start()
            if action == 'explore':
                return self.tasks.start()
            if action in ('remote', 'stop'):
                return self.tasks.remote()
            raise ValueError('未知任务操作')

        def selected(self, msg):
            with self.lock:
                if msg.data in ('hold', 'manual', 'autonomy'):
                    self.selection_mode = msg.data
                    self.selection_time = time.monotonic()

        def stamp(self, msg): return msg.header.stamp.sec + \
            msg.header.stamp.nanosec/1e9

        def record(self, key, msg):
            now = time.monotonic()
            stamp = self.stamp(msg)
            if key != 'camera' and key in self.stamps and stamp < self.stamps[key]:
                self.hold('timestamp_backwards')
            self.received[key] = now
            self.stamps[key] = stamp
            self.history.setdefault(key, deque(
                maxlen=100)).append((now, stamp))

        def scan(self, m):
            with self.lock:
                self.record('scan', m)
                self.scan_frame = m.header.frame_id
                self.latest['scan'] = {'frame': m.header.frame_id, 'angle_min': m.angle_min, 'angle_increment': m.angle_increment,
                                       'range_min': m.range_min, 'range_max': m.range_max, 'ranges': finite_ranges(m.ranges, m.range_min, m.range_max)}

        def map(self, m):
            if self.stamp(m) < self.map_min_stamp:
                return
            try:
                data = grid_payload(m.info.width, m.info.height, m.data)
            except ValueError:
                return
            with self.lock:
                self.record('map', m)
                self.frame = m.header.frame_id
                self.map_revision += 1
                q = m.info.origin.orientation
                self.latest['map'] = {'revision': self.map_revision, 'frame': m.header.frame_id, 'width': m.info.width, 'height': m.info.height, 'resolution': m.info.resolution,
                                      'origin': [m.info.origin.position.x, m.info.origin.position.y, math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))], 'data': data}

        def odom(self, m):
            with self.lock:
                self.record('odom', m)
                self.latest['odom'] = {'linear': m.twist.twist.linear.x,
                                       'angular': m.twist.twist.angular.z, 'frame': m.header.frame_id}

        def camera(self, m):
            if time.monotonic()-self.last_image < .12:
                return
            try:
                image = jpeg_from_image(m)
            except Exception:
                with self.lock:
                    self.latest['camera_error'] = 'Unsupported or invalid image; check image encoding/OpenCV'
                return
            with self.lock:
                self.image = image
                self.last_image = time.monotonic()
                self.record('camera', m)
                self.latest.pop('camera_error', None)

        def compressed(self, m):
            if 'jpeg' not in m.format.lower() and 'jpg' not in m.format.lower():
                return
            with self.lock:
                self.image = bytes(m.data)
                self.last_image = time.monotonic()
                self.record('camera', m)

        def log(self, m):
            with self.lock:
                self.seq += 1
                self.logs.append({'id': self.seq, 'stamp': m.stamp.sec+m.stamp.nanosec /
                                 1e9, 'level': m.level, 'name': m.name, 'message': m.msg[:8192]})

        def safety(self, m):
            try:
                status = json.loads(m.data)
            except ValueError:
                return
            with self.lock:
                self.robot_status = status
                self.robot_status_revision += 1
                self.robot_status_time = time.monotonic()

        def tf_received(self, transform, static):
            with self.lock:
                key = (transform.header.frame_id, transform.child_frame_id)
                if key in self.tf_edges or len(self.tf_edges) < 1024:
                    received = time.monotonic()
                    self.tf_edges[key] = (received, static)
                    self.tf_history.setdefault(key, deque(maxlen=4)).append((received, self.stamp(transform)))

        def tf_failure(self, target, source, reason, ros_now=None, **details):
            if ros_now is None:
                ros_now = self.get_clock().now().nanoseconds/1e9
            self.tf_error = dict(target=target, source=source, reason=reason,
                at=time.time(), ros_now=ros_now, **details,
                **tf_failure_context(self.tf_edges, self.tf_history, target, source,
                                     ros_now, time.monotonic()))
            return None

        def record_task_stop(self, details):
            try:
                write_task_stop(self.task_run_dir, details)
            except (OSError, ValueError) as exc:
                self.get_logger().warning('Task stop evidence could not be saved: '+str(exc))

        def transform(self, target, source, at=None):
            try:
                if not tf_chain_fresh(self.tf_edges, target, source, time.monotonic()):
                    return self.tf_failure(target, source, 'receipt_stale_or_missing')
                t = self.tf.lookup_transform(target, source, rclpy.time.Time(
                    seconds=at) if at is not None else rclpy.time.Time())
                stamp = t.header.stamp.sec+t.header.stamp.nanosec/1e9
                ros_now = self.get_clock().now().nanoseconds/1e9
                age = ros_now-stamp
                if stamp == 0.:
                    age = 0.  # Static TF carries a zero source stamp.
                if not -.3 <= age <= 1.:
                    return self.tf_failure(target, source, 'source_age', ros_now=ros_now,
                                           age=age, source_stamp=stamp)
                q = t.transform.rotation
                p = t.transform.translation
                return {'x': p.x, 'y': p.y, 'yaw': math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z)), 'age': age, 'frame': target}
            except Exception as exc:
                return self.tf_failure(target, source, str(exc))

        def fresh(self, key, limit=1.):
            return fresh_measurement(self.stamps.get(key), self.get_clock().now().nanoseconds/1e9, self.received.get(key), time.monotonic(), limit)

        def hold(self, reason):
            owned = self.lease.owner is not None
            self.lease.release(reason)
            self.handshake.reset()
            self.motion.stop(reason)
            self.requested = (0., 0.)
            if self.allowed and (owned or reason == 'software_stop'):
                self.pub.publish(Twist())
            if real_config:
                self.selection.publish(String(data='hold'))
            if real_config and self.arm.service_is_ready():
                req = SetBool.Request()
                req.data = False
                self.arm.call_async(req)

        def blockers(self):
            if not self.allowed:
                return 'read_only'
            if not self.fresh('scan') or not self.fresh('odom'):
                return 'sensor_stale'
            odom_frame = real_config['odom_frame'] if real_config else 'odom'
            if not self.transform(odom_frame, args.base_frame) or not self.transform(args.base_frame, self.scan_frame):
                return 'tf_stale'
            if len(self.get_publishers_info_by_topic(self.command_topic)) != 1:
                return 'autonomous_or_other_publisher_active'
            if real_config and (time.monotonic()-self.selection_time > .5 or not self.autonomy_source.service_is_ready()):
                return 'command_selector_unavailable'
            if real_config:
                selected_output = self.get_publishers_info_by_topic('/safety/nav_cmd_vel')
                if len(selected_output) != 1 or selected_output[0].node_name != 'wheeltec_command_selector':
                    return 'command_selector_output_not_exclusive'
            if real_config and (time.monotonic()-self.robot_status_time > .5 or not self.arm.service_is_ready()):
                return 'watchdog_unavailable'
            if real_config:
                final = self.get_publishers_info_by_topic(
                    real_config['driver_command_topic'])
                if len(final) != 1 or final[0].node_name != 'wheeltec_watchdog':
                    return 'driver_output_not_exclusive'
            return None

        def control(self, d):
            if d.get('action') == 'stop':
                self.tasks.remote()
                return {'accepted': True, 'mode': 'remote', 'scope': 'manual_pipeline' if self.allowed else 'local_lease_only'}
            with self.lock:
                action = d.get('action')
                owner = d.get('owner', '')
                now = time.monotonic()
                if action == 'heartbeat':
                    if not real_config:
                        raise ValueError('Robot safety configuration required')
                    self.heartbeat.publish(Empty())
                    return {'accepted': True}
                if action == 'gear':
                    delta = d.get('delta')
                    if type(delta) is not int or delta not in (-1, 1):
                        raise ValueError('换挡方向只能为 +1 或 -1')
                    self.select_gear(max(0, min(2, self.gear+delta)))
                    return {'accepted': True, 'gear': self.gear}
                if action == 'release':
                    if self.lease.owner == owner:
                        self.hold('operator_release')
                    return {'accepted': True}
                if action in ('claim', 'command') and self.map_reset.busy:
                    raise ValueError('地图正在重置，请等待完成')
                if action in ('claim', 'command') and self.tasks.mode != 'remote':
                    raise ValueError('请先切换到远程接管')
                if real_config and action in ('claim', 'command'):
                    require_control_epoch(d.get('epoch'), self.tasks.generation)
                reason = self.blockers()
                if reason:
                    self.hold(reason)
                    raise ValueError(reason)
                if action == 'claim':
                    if real_config and self.remote_barrier is not None:
                        if not self.remote_barrier.done() or self.remote_barrier.exception() is not None or self.remote_barrier.result() is None or not self.remote_barrier.result().success:
                            raise ValueError('正在切换远程接管，请稍后按键')
                    if real_config:
                        reason = takeover_blocker(self.selection_mode, time.monotonic()-self.selection_time <= .5,
                            self.robot_status.get('armed') if self.robot_status else None)
                        if reason:
                            raise ValueError(reason)
                    self.lease.claim(owner, now)
                    self.manual_epoch = self.tasks.generation
                    self.motion.command((0., 0.), now)
                    self.motion.heartbeat(now)
                    self.motion.arm(now)
                    if real_config:
                        self.selection.publish(String(data='manual'))
                        self.handshake.start(now)
                        self.heartbeat.publish(Empty())
                        self.pub.publish(Twist())
                        request = SetBool.Request()
                        request.data = True
                        self.arm.call_async(request)
                elif action == 'command':
                    if real_config:
                        reason = manual_command_blocker(self.selection_mode, self.handshake.ready,
                            d.get('linear', 0), d.get('angular', 0))
                        if reason:
                            raise ValueError(reason)
                    self.lease.command(owner, d.get(
                        'linear', 0), d.get('angular', 0), now)
                    self.motion.command(self.lease.target, now)
                    self.motion.heartbeat(now)
                    if real_config:
                        self.heartbeat.publish(Empty())
                else:
                    raise ValueError('Unknown control action')
                return {'accepted': True}

        def tick(self):
            with self.lock:
                if not self.allowed:
                    return
                if real_config and self.lease.owner and self.manual_epoch != self.tasks.generation:
                    self.hold('software_stop')
                reason = self.blockers()
                if real_config and self.tasks.mode == 'autonomous' and (reason or not (self.robot_status or {}).get('armed')):
                    stopped = reason or (self.robot_status or {}).get('reason', 'watchdog_disarmed')
                    if reason == 'tf_stale' and self.tf_error:
                        stopped += ': '+json.dumps(self.tf_error, ensure_ascii=False)
                    if stopped == 'command_or_operator_timeout' and (self.robot_status or {}).get('timeout_detail'):
                        stopped += ': '+json.dumps(self.robot_status['timeout_detail'], ensure_ascii=False)
                    message = '自主探索已停止：'+stopped
                    self.seq += 1
                    self.logs.append({'id': self.seq, 'stamp': time.time(), 'level': 40,
                                      'name': 'console.task', 'message': message})
                    details = dict(stamp=time.time(), monotonic=time.monotonic(), message=message,
                        tf_error=self.tf_error, watchdog=self.robot_status,
                        selection_mode=self.selection_mode, source_stamps=dict(self.stamps),
                        received_monotonic=dict(self.received))
                    try:
                        self.tasks.remote(message)
                    finally:
                        self.record_task_stop(details)
                if reason:
                    if self.lease.owner:
                        self.hold(reason)
                    self.block = reason
                else:
                    self.block = None
                was_owned = self.lease.owner is not None
                target = self.lease.output(time.monotonic())
                if was_owned and not self.lease.owner:
                    self.pub.publish(Twist())
                if not self.lease.owner:
                    self.motion.stop(self.lease.reason)
                if real_config and self.lease.owner:
                    problem = self.handshake.observe(
                        bool(self.robot_status and self.robot_status.get('armed')), time.monotonic())
                    if problem:
                        self.hold(problem)
                    elif self.handshake.pending and time.monotonic()-self.last_arm_attempt > .2:
                        self.pub.publish(Twist())
                        request = SetBool.Request()
                        request.data = True
                        self.arm.call_async(request)
                        self.last_arm_attempt = time.monotonic()
                v, w = self.motion.output(time.monotonic())
                if real_config and not self.handshake.ready:
                    v = w = 0.
                self.requested = target
                # Simulation template hold; real commands use the configured footprint collision monitor.
                scan = self.latest.get('scan')
                blocked = False
                if scan and (v or w) and not real_config:
                    blocked = any(
                        x is not None and x < CONTROL['laser_hold_m'] for x in scan['ranges'])
                if blocked:
                    self.hold('laser_obstacle_hold')
                    v = w = 0.
                # Simulation acceleration limit. Robot commands pass existing smoother/collision/watchdog.
                if args.kind == 'simulation' and (v or w):
                    v = max(self.actual[0]-CONTROL['simulation_linear_accel_m_s2']*CONTROL['tick_s'], min(
                        self.actual[0]+CONTROL['simulation_linear_accel_m_s2']*CONTROL['tick_s'], v))
                    w = max(self.actual[1]-CONTROL['simulation_yaw_accel_rad_s2']*CONTROL['tick_s'], min(
                        self.actual[1]+CONTROL['simulation_yaw_accel_rad_s2']*CONTROL['tick_s'], w))
                self.actual = (v, w)
                m = Twist()
                m.linear.x = v
                m.angular.z = w
                # Never publish zeros into an active autonomous source; refuse manual ownership instead.
                if self.lease.owner:
                    self.pub.publish(m)
                elif self.actual != (0., 0.):
                    self.pub.publish(Twist())
                    self.actual = (0., 0.)

        def snapshot(self):
            with self.lock:
                streams = {}
                now = self.get_clock().now().nanoseconds/1e9
                for key in ('scan', 'map', 'odom', 'camera'):
                    history = list(self.history.get(key, []))
                    hz = 0.
                    if len(history) > 1 and history[-1][1] > history[0][1]:
                        hz = (len(history)-1)/(history[-1][1]-history[0][1])
                    age = now-self.stamps[key] if key in self.stamps else None
                    streams[key] = {'stamp': self.stamps.get(
                        key), 'age': age, 'hz': hz, 'fresh': self.fresh(key, 15. if key == 'map' else 1.)}
                streams['camera']['receive_hz'] = distinct_receive_hz(self.history.get('camera', []))
                streams['camera'].update(camera_reception(self.received.get('camera'), time.monotonic()))
                result = dict(self.latest)
                # The original source timestamp is always retained; stale poses are omitted.
                result.update(task=self.tasks.snapshot(), map_reset=self.map_reset.snapshot(), kind=args.kind, clock=now, streams=streams, pose=self.transform(args.map_frame, args.base_frame),
                              laser_pose=self.transform(args.map_frame, self.scan_frame, self.stamps.get(
                                  'scan')) if self.scan_frame else None,
                              logs=list(self.logs), control={'owner': self.lease.owner, 'reason': self.block or self.lease.reason, 'tf_error': self.tf_error, 'target': self.requested,
                                                             'output': self.actual, 'ready': bool(self.lease.owner) and (not real_config or self.handshake.ready), 'enabled': self.allowed, 'watchdog': self.robot_status, 'watchdog_fresh': time.monotonic()-self.robot_status_time <= .5, 'watchdog_revision': self.robot_status_revision, 'command_timeout': CONTROL['command_timeout_s'], 'heartbeat_timeout': CONTROL['operator_timeout_s'], 'gear': self.gear, 'epoch': self.tasks.generation, 'selection_mode': self.selection_mode if self.remote_barrier is None or self.remote_barrier.done() else None, 'limits': [real_config['safety']['max_linear_m_s'], real_config['safety']['max_yaw_rad_s']] if real_config else [CONTROL['max_linear_m_s'], CONTROL['max_yaw_rad_s']]})
                return result
    node = Adapter()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def handle_request(self, post=False):
            if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token):
                self.send_error(401)
                return
            try:
                if not post and self.path == '/state':
                    data = json.dumps(
                        node.snapshot(), allow_nan=False).encode()
                    mime = 'application/json'
                elif not post and self.path == '/camera':
                    if not camera_reception(node.received.get('camera'), time.monotonic())['receiving'] or node.image is None:
                        self.send_error(503)
                        return
                    data = node.image
                    mime = 'image/jpeg'
                elif post and self.path in ('/control', '/task'):
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 4096 or self.headers.get('Transfer-Encoding'):
                        self.send_error(413)
                        return
                    operation = node.control if self.path == '/control' else node.task_control
                    data = json.dumps(operation(json.loads(self.rfile.read(size)))).encode()
                    mime = 'application/json'
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (ValueError, TypeError, KeyError) as exc:
                data = json.dumps({'detail': str(exc)}, ensure_ascii=False).encode()
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self): self.handle_request()
        def do_POST(self): self.handle_request(True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print('Adapter ready on loopback; '+args.kind +
          '; control='+str(node.allowed), flush=True)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.tasks.remote()
        with node.lock:
            node.hold('adapter_shutdown')
            if node.allowed and not node.blockers():
                node.pub.publish(Twist())
        server.shutdown()
        server.server_close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
