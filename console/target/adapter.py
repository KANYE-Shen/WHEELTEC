"""Target-side ROS adapter. No drivers, SLAM or navigation are started here.
Run from repository root: python3 -m console.target.adapter --help
"""
import argparse
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
from console.backend.policy import Lease, simulation_authorized, ArmHandshake
from .data import finite_ranges, grid_payload, jpeg_from_image, fresh_measurement, tf_chain_fresh


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
    parser.add_argument('--gate', type=int, choices=[1, 2, 3, 4, 5], default=1)
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
        from preflight import validate
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
    from tf2_msgs.msg import TFMessage
    from geometry_msgs.msg import Twist
    from std_msgs.msg import Empty, String, Bool
    from std_srvs.srv import SetBool
    from rcl_interfaces.msg import Log
    from tf2_ros import Buffer, TransformListener
    rclpy.init(args=ros_args)

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
            self.robot_status = None
            self.robot_status_time = 0
            self.robot_status_revision = 0
            self.block = 'read_only'
            self.requested = (0., 0.)
            self.actual = (0., 0.)
            self.last_image = 0.
            self.last_tf = 0.
            self.map_revision = 0
            self.tf_edges = {}
            self.tf = Buffer()
            self.listener = TransformListener(self.tf, self)
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
                         self.create_subscription(String, '/safety/status', self.safety, 10)]
            self.subs += [self.create_subscription(TFMessage, '/tf', lambda m: self.tf_received(m, False), qos_profile_sensor_data),
                          self.create_subscription(TFMessage, '/tf_static', lambda m: self.tf_received(m, True), QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE))]
            self.allowed = args.enable_simulation_control or real_config is not None
            if self.allowed:
                topic = '/cmd_vel' if args.kind == 'simulation' else '/safety/nav_cmd_vel'
                self.command_topic = topic
                self.pub = self.create_publisher(Twist, topic, 1)
                if real_config:
                    self.heartbeat = self.create_publisher(
                        Empty, '/safety/operator_heartbeat', 1)
                    self.arm = self.create_client(SetBool, '/safety/arm')
            self.timer = self.create_timer(
                CONTROL['tick_s'], self.tick, clock=self.steady)

        def stamp(self, msg): return msg.header.stamp.sec + \
            msg.header.stamp.nanosec/1e9

        def record(self, key, msg):
            now = time.monotonic()
            stamp = self.stamp(msg)
            if key in self.stamps and stamp < self.stamps[key]:
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

        def tf_received(self, message, static):
            with self.lock:
                for item in message.transforms:
                    key = (item.header.frame_id, item.child_frame_id)
                    if key in self.tf_edges or len(self.tf_edges) < 1024:
                        self.tf_edges[key] = (time.monotonic(), static)

        def transform(self, target, source, at=None):
            try:
                if not tf_chain_fresh(self.tf_edges, target, source, time.monotonic()):
                    return None
                t = self.tf.lookup_transform(target, source, rclpy.time.Time(
                    seconds=at) if at is not None else rclpy.time.Time())
                stamp = t.header.stamp.sec+t.header.stamp.nanosec/1e9
                age = self.get_clock().now().nanoseconds/1e9-stamp
                if stamp == 0.:
                    age = 0.  # Static TF carries a zero source stamp.
                if not -.3 <= age <= 1.:
                    return None
                q = t.transform.rotation
                p = t.transform.translation
                return {'x': p.x, 'y': p.y, 'yaw': math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z)), 'age': age, 'frame': target}
            except Exception:
                return None

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
            if real_config and self.arm.service_is_ready():
                req = SetBool.Request()
                req.data = False
                self.arm.call_async(req)

        def blockers(self):
            if not self.allowed:
                return 'read_only'
            if not self.fresh('scan') or not self.fresh('odom'):
                return 'sensor_stale'
            if not self.transform('odom', args.base_frame) or not self.transform(args.base_frame, self.scan_frame):
                return 'tf_stale'
            if len(self.get_publishers_info_by_topic(self.command_topic)) != 1:
                return 'autonomous_or_other_publisher_active'
            if real_config and (time.monotonic()-self.robot_status_time > .5 or not self.arm.service_is_ready()):
                return 'watchdog_unavailable'
            if real_config:
                final = self.get_publishers_info_by_topic(
                    real_config['driver_command_topic'])
                if len(final) != 1 or final[0].node_name != 'wheeltec_watchdog':
                    return 'driver_output_not_exclusive'
            return None

        def control(self, d):
            with self.lock:
                action = d.get('action')
                owner = d.get('owner', '')
                now = time.monotonic()
                if action == 'stop':
                    self.hold('software_stop')
                    return {'accepted': True, 'scope': 'manual_pipeline' if self.allowed else 'local_lease_only'}
                if action == 'release':
                    if self.lease.owner == owner:
                        self.hold('operator_release')
                    return {'accepted': True}
                reason = self.blockers()
                if reason:
                    self.hold(reason)
                    raise ValueError(reason)
                if action == 'claim':
                    self.lease.claim(owner, now)
                    self.motion.command((0., 0.), now)
                    self.motion.heartbeat(now)
                    self.motion.arm(now)
                    if real_config:
                        self.handshake.start(now)
                        self.heartbeat.publish(Empty())
                        self.pub.publish(Twist())
                        request = SetBool.Request()
                        request.data = True
                        self.arm.call_async(request)
                elif action == 'command':
                    if real_config and not self.handshake.ready and (d.get('linear', 0) or d.get('angular', 0)):
                        raise ValueError(
                            'Final watchdog not armed; keep zero until acknowledged')
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
                reason = self.blockers()
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
                # Conservative bidirectional software obstacle hold; no footprint or braking claim.
                scan = self.latest.get('scan')
                blocked = False
                if scan and (v or w):
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
                result = dict(self.latest)
                # The original source timestamp is always retained; stale poses are omitted.
                result.update(kind=args.kind, clock=now, streams=streams, pose=self.transform(args.map_frame, args.base_frame),
                              laser_pose=self.transform(args.map_frame, self.scan_frame, self.stamps.get(
                                  'scan')) if self.scan_frame else None,
                              logs=list(self.logs), control={'owner': self.lease.owner, 'reason': self.block or self.lease.reason, 'target': self.requested,
                                                             'output': self.actual, 'ready': bool(self.lease.owner) and (not real_config or self.handshake.ready), 'enabled': self.allowed, 'watchdog': self.robot_status, 'watchdog_fresh': time.monotonic()-self.robot_status_time <= .5, 'watchdog_revision': self.robot_status_revision, 'command_timeout': CONTROL['command_timeout_s'], 'heartbeat_timeout': CONTROL['operator_timeout_s'], 'limits': [CONTROL['max_linear_m_s'], CONTROL['max_yaw_rad_s']]})
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
                    if not node.fresh('camera') or node.image is None:
                        self.send_error(503)
                        return
                    data = node.image
                    mime = 'image/jpeg'
                elif post and self.path == '/control':
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 4096 or self.headers.get('Transfer-Encoding'):
                        self.send_error(413)
                        return
                    data = json.dumps(node.control(
                        json.loads(self.rfile.read(size)))).encode()
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
            except (ValueError, TypeError, KeyError):
                self.send_error(400)
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
        with node.lock:
            node.hold('adapter_shutdown')
            if node.allowed and not node.blockers():
                node.pub.publish(Twist())
        server.shutdown()
        server.server_close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
