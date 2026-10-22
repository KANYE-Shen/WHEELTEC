"""Check the simulated room's ROS sensor and motion interfaces."""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
run_dir = Path.home() / 'wheeltec_sim_ws/data/runs' / (time.strftime('%Y%m%d-%H%M%S') + '_room_interfaces')
run_dir.mkdir(parents=True, exist_ok=False)
result = {'run_dir': str(run_dir), 'success': False}
process = None
node = None
log = None
publisher = None

try:
    if not (ROOT / 'simulation/launch/room.launch.py').is_file():
        raise RuntimeError('Room launch file is not implemented yet.')
    os.environ.update(ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID='79')
    log = (run_dir / 'launch.log').open('w')
    process = subprocess.Popen(
        ['python3', str(ROOT / 'simulation/run_room.py'), 'gui:=false', 'rviz:=false', 'mode:=interfaces', 'ros_domain_id:=79',
         f'partition:=wheeltec-room-check-{os.getpid()}'],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import LaserScan
    from tf2_msgs.msg import TFMessage
    from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy

    rclpy.init()
    node = rclpy.create_node('wheeltec_room_interface_check')
    latest = {}
    counts = {'scan': 0, 'odom': 0, 'clock': 0}
    edges = set()

    def receive(name, message):
        latest[name] = message
        counts[name] += 1

    def receive_tf(message):
        edges.update((t.header.frame_id, t.child_frame_id) for t in message.transforms)

    subscriptions = [
        node.create_subscription(LaserScan, '/scan', lambda m: receive('scan', m), qos_profile_sensor_data),
        node.create_subscription(Odometry, '/odom', lambda m: receive('odom', m), qos_profile_sensor_data),
        node.create_subscription(Clock, '/clock', lambda m: receive('clock', m), qos_profile_sensor_data),
        node.create_subscription(TFMessage, '/tf', receive_tf, 50),
        node.create_subscription(TFMessage, '/tf_static', receive_tf,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)),
    ]
    publisher = node.create_publisher(Twist, '/cmd_vel', 10)

    def wait_for(predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if process.poll() is not None:
                raise RuntimeError('Simulation exited early; see launch.log.')
            if predicate():
                return
        raise RuntimeError('Timed out waiting for simulation data or motion.')

    def sim_time():
        stamp = latest['clock'].clock
        return stamp.sec + stamp.nanosec / 1e9

    def yaw():
        q = latest['odom'].pose.pose.orientation
        return math.atan2(2 * (q.w*q.z + q.x*q.y), 1 - 2 * (q.y*q.y + q.z*q.z))

    def front_distance():
        scan = latest['scan']
        index = round(-scan.angle_min / scan.angle_increment)
        return scan.ranges[index]

    def drive(linear, angular, seconds):
        start = sim_time()
        message = Twist()
        message.linear.x = linear
        message.angular.z = angular
        deadline = time.monotonic() + max(25, seconds * 8)
        while sim_time() - start < seconds:
            if time.monotonic() > deadline:
                raise RuntimeError('Simulation clock stalled during motion.')
            if process.poll() is not None:
                raise RuntimeError('Simulation exited during motion.')
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.05)

    wait_for(lambda: min(counts.values()) >= 5 and
             ('odom', 'base_link') in edges and
             ('base_link', 'wheeltec_reference/base_link/laser') in edges, 60)
    scan = latest['scan']
    assert len(scan.ranges) == 720, f'Unexpected beam count: {len(scan.ranges)}'
    assert scan.angle_max - scan.angle_min > 6.28, 'Expected full-circle scan'
    assert scan.header.frame_id == 'wheeltec_reference/base_link/laser', scan.header.frame_id
    assert latest['odom'].header.frame_id == 'odom'
    assert latest['odom'].child_frame_id == 'base_link'
    first_time = sim_time()
    x0 = latest['odom'].pose.pose.position.x
    y0 = latest['odom'].pose.pose.position.y
    d0 = front_distance()
    assert 3.9 < d0 < 4.5, f'Unexpected initial front wall distance: {d0}'
    drive(0.15, 0.0, 3.0)
    drive(0.0, 0.0, 1.0)
    dx = latest['odom'].pose.pose.position.x - x0
    dy = latest['odom'].pose.pose.position.y - y0
    wall_change = d0 - front_distance()
    assert 0.30 < dx < 0.62 and abs(dy) < 0.08, (dx, dy)
    assert abs(wall_change - dx) < 0.12, (wall_change, dx)
    assert abs(latest['odom'].twist.twist.linear.x) < 0.03
    angle0 = yaw()
    drive(0.0, 0.35, 2.0)
    drive(0.0, 0.0, 1.0)
    angle = math.atan2(math.sin(yaw() - angle0), math.cos(yaw() - angle0))
    assert 0.45 < angle < 0.95, angle
    assert abs(latest['odom'].twist.twist.angular.z) < 0.04
    assert sim_time() > first_time + 6
    result.update(success=True, beam_count=len(scan.ranges), scan_frame=scan.header.frame_id,
                  messages=counts, tf_edges=sorted(edges), displacement_m=dx,
                  lateral_drift_m=dy, front_wall_distance_change_m=wall_change,
                  turn_radians=angle, elapsed_sim_seconds=sim_time()-first_time)
except Exception as error:
    result['error'] = str(error)
finally:
    if publisher is not None:
        try:
            for _ in range(3):
                publisher.publish(Twist())
                rclpy.spin_once(node, timeout_sec=0.05)
        except Exception:
            pass
    if node is not None:
        node.destroy_node()
        rclpy.shutdown()
    if process is not None:
        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=20)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    if log is not None:
        log.close()
    (run_dir / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)

raise SystemExit(0 if result['success'] else 1)
