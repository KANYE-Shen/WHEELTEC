"""Verify the installed simulation environment, without connecting to a robot."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

log_dir = Path.home() / 'simulation-checks' / time.strftime('%Y%m%d-%H%M%S')
log_dir.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID='77',
           IGN_PARTITION=f'wheeltec-setup-check-{os.getpid()}')
os.environ.update(env)
processes = []
handles = []
results = {'log_dir': str(log_dir)}


def run(args, name, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, env=env, timeout=timeout)
    (log_dir / name).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}; see {log_dir}')
    return result.stdout


def start(args, name):
    handle = (log_dir / name).open('w')
    handles.append(handle)
    process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT,
                               env=env, start_new_session=True)
    processes.append(process)
    return process


try:
    results['packages'] = run([
        'dpkg-query', '-W', '-f=${Package}\t${Version}\t${db:Status-Status}\n',
        'ros-humble-desktop', 'ros-humble-ros-gz', 'ros-humble-navigation2',
        'ros-humble-nav2-bringup', 'ros-humble-slam-toolbox'], 'packages.log')
    results['graphics'] = run(['glxinfo', '-B'], 'graphics.log')
    results['gazebo_version'] = run(['ign', 'gazebo', '--versions'], 'gazebo-version.log')

    print('Checking ROS C++ to Python message delivery...', flush=True)
    talker = start(['ros2', 'run', 'demo_nodes_cpp', 'talker'], 'talker.log')
    listener = start(['ros2', 'run', 'demo_nodes_py', 'listener'], 'listener.log')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        content = (log_dir / 'listener.log').read_text()
        if content.count('I heard:') >= 3:
            break
        if talker.poll() is not None or listener.poll() is not None:
            raise RuntimeError('A ROS demo process exited before successful communication.')
        time.sleep(0.25)
    else:
        raise RuntimeError('ROS listener did not receive three messages in 15 seconds.')
    results['ros_message_delivery'] = True

    print('Checking Gazebo server and Gazebo-to-ROS clock bridge...', flush=True)
    server = start(['ign', 'gazebo', '-s', '-r', '-v', '3', 'empty.sdf'], 'gazebo-server.log')
    bridge = start(['ros2', 'run', 'ros_gz_bridge', 'parameter_bridge',
                    '/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock'], 'clock-bridge.log')
    import rclpy
    from rosgraph_msgs.msg import Clock
    from rclpy.qos import qos_profile_sensor_data
    rclpy.init()
    node = rclpy.create_node('wheeltec_environment_clock_check')
    values = []
    subscription = node.create_subscription(
        Clock, '/clock', lambda msg: values.append(msg.clock.sec + msg.clock.nanosec / 1e9),
        qos_profile_sensor_data)
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
            if len(values) >= 3 and values[-1] > values[0]:
                break
            if server.poll() is not None or bridge.poll() is not None:
                raise RuntimeError('Gazebo server or ROS bridge exited unexpectedly.')
        else:
            raise RuntimeError('No advancing Gazebo /clock received through the ROS bridge.')
        results['gazebo_clock_bridge'] = {'samples': len(values), 'first': values[0], 'last': values[-1]}
    finally:
        node.destroy_node()
        rclpy.shutdown()
    results['success'] = True
except Exception as error:
    results['success'] = False
    results['error'] = str(error)
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
