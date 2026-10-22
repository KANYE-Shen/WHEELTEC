"""Check the stock Gazebo lidar example with the WSL-compatible rendering engine."""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

os.environ.update(ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID='77',
                  IGN_PARTITION=f'wheeltec-lidar-check-{os.getpid()}')
log_dir = Path.home() / 'simulation-checks' / ('lidar-' + time.strftime('%Y%m%d-%H%M%S'))
log_dir.mkdir(parents=True, exist_ok=False)
results = {'log_dir': str(log_dir), 'render_engine': 'ogre'}
processes = []
handles = []

try:
    commands = [
        ('server.log', ['ign', 'gazebo', '-s', '-r', '-v', '4', '--render-engine-server', 'ogre',
                        'gpu_lidar_sensor.sdf']),
        ('bridge.log', ['ros2', 'run', 'ros_gz_bridge', 'parameter_bridge',
                        '/lidar@sensor_msgs/msg/LaserScan[ignition.msgs.LaserScan'])]
    for name, args in commands:
        handle = (log_dir / name).open('w')
        handles.append(handle)
        processes.append(subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT,
                                          start_new_session=True))
    import rclpy
    from sensor_msgs.msg import LaserScan
    from rclpy.qos import qos_profile_sensor_data
    rclpy.init()
    node = rclpy.create_node('wheeltec_environment_lidar_check')
    scans = []
    subscription = node.create_subscription(LaserScan, '/lidar', scans.append, qos_profile_sensor_data)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
            if len(scans) >= 2 and scans[-1].ranges:
                finite = [x for x in scans[-1].ranges if math.isfinite(x)]
                if finite:
                    results.update(messages=len(scans), ranges=len(scans[-1].ranges),
                                   finite_ranges=len(finite), minimum_range=min(finite),
                                   frame_id=scans[-1].header.frame_id)
                    break
            if any(p.poll() is not None for p in processes):
                raise RuntimeError('Lidar server or bridge exited unexpectedly.')
        else:
            raise RuntimeError('No valid lidar scans received within 30 seconds.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
    results['success'] = True
except Exception as error:
    results.update(success=False, error=str(error))
finally:
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    for handle in handles:
        handle.close()
    (log_dir / 'result.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2), flush=True)

raise SystemExit(0 if results['success'] else 1)
