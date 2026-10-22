"""Exercise real SLAM/Nav2, save artifacts, restart AMCL and navigate again."""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUN = Path.home() / 'wheeltec_sim_ws/data/runs' / (time.strftime('%Y%m%d-%H%M%S') + '_navigation')
RUN.mkdir(parents=True)
os.environ.update(ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID='78')
result = {'success': False, 'run_dir': str(RUN), 'goals': []}
process = None
log = None
node = None

try:
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from rclpy.parameter import Parameter
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from nav_msgs.msg import OccupancyGrid, Odometry
    from nav2_msgs.action import NavigateToPose
    from lifecycle_msgs.srv import GetState
    from tf2_ros import Buffer, TransformListener
    from tf2_msgs.msg import TFMessage

    rclpy.init()
    node = rclpy.create_node('wheeltec_navigation_check', parameter_overrides=[Parameter('use_sim_time', value=True)])
    latest = {}
    tf = Buffer(node=node)
    listener = TransformListener(tf, node)
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    subs = [node.create_subscription(OccupancyGrid, '/map', lambda m: latest.update(map=m), qos),
            node.create_subscription(Odometry, '/odom', lambda m: latest.update(odom=m), 10),
            node.create_subscription(TFMessage, '/simulation/ground_truth', lambda m: latest.update(truth=m), 10)]
    client = ActionClient(node, NavigateToPose, 'navigate_to_pose')
    active = node.create_client(GetState, '/bt_navigator/get_state')

    def wait(predicate, seconds, reason):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
            if process is not None and process.poll() is not None:
                raise RuntimeError('Launch exited; see log.')
            if predicate():
                return
        raise RuntimeError('Timeout: ' + reason)

    def future(f, seconds=30):
        wait(f.done, seconds, 'ROS future')
        return f.result()

    def pose():
        try:
            t = tf.lookup_transform('map', 'base_link', rclpy.time.Time()).transform
            return (t.translation.x, t.translation.y)
        except Exception:
            return None

    def ready():
        wait(lambda: 'map' in latest and 'truth' in latest and pose() is not None, 65, 'SLAM map and map→base_link')
        m = latest['map']
        free = sum(0 <= v < 25 for v in m.data)
        occupied = sum(v > 65 for v in m.data)
        assert free > 1000 and occupied > 100, (free, occupied)
        wait(lambda: client.server_is_ready() and active.service_is_ready(), 45, 'Nav2 action and lifecycle')
        for _ in range(40):
            state = future(active.call_async(GetState.Request()), 10)
            if state.current_state.id == 3:
                return {'free_cells': free, 'occupied_cells': occupied, 'resolution': m.info.resolution}
            until = time.monotonic() + .5
            wait(lambda: time.monotonic() >= until, 2, 'lifecycle settling')
        raise RuntimeError('Nav2 never became active.')

    def start(mode, map_path=None):
        global process, log, tf, listener
        latest.clear()
        listener.unregister()
        tf = Buffer(node=node)
        listener = TransformListener(tf, node)
        log = (RUN / (mode + '.log')).open('w')
        args = ['python3', str(ROOT / 'simulation/run_room.py'), 'gui:=false', 'rviz:=false',
                'ros_domain_id:=78', 'mode:=' + mode, 'partition:=wheeltec-nav-' + str(os.getpid()) + mode]
        if map_path:
            args.append('map:=' + str(map_path))
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    def stop():
        global process, log
        if process:
            try:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=25)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            process = None
        if log:
            log.close()
            log = None

    def navigate(x, y, mode):
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = node.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        goal.pose.pose.orientation.w = 1.0
        begin = time.monotonic()
        handle = future(client.send_goal_async(goal))
        assert handle.accepted, 'Navigation goal rejected.'
        answer = future(handle.get_result_async(), 160)
        position = pose()
        assert position is not None
        error = math.hypot(position[0] - x, position[1] - y)
        # Read simulator world pose only for evaluation; algorithms never consume it.
        truth = next(t.transform.translation for t in latest['truth'].transforms if t.child_frame_id == 'wheeltec_reference')
        truth_error = math.hypot(truth.x + 1.7 - x, truth.y + 1.5 - y)
        row = {'mode': mode, 'target': [x,y], 'status': answer.status,
               'estimated_error_m': error, 'gazebo_truth_error_m': truth_error,
               'wall_seconds': time.monotonic() - begin}
        result['goals'].append(row)
        print(json.dumps(row), flush=True)
        assert answer.status == 4, row
        assert error < .22 and truth_error < .22, row

    start('mapping')
    result['mapping'] = ready()
    for xy in [(2.7,0.0),(3.0,3.3),(0.0,3.4),(0.0,0.0)]:
        navigate(*xy, 'mapping')
    save = subprocess.run(['python3', str(ROOT / 'simulation/save_map.py'), '--output', str(RUN/'map'),
                           '--reference-yaw', '0.0', '--no-latest'], env=os.environ.copy(),
                          capture_output=True, text=True, timeout=70)
    (RUN/'save.log').write_text(save.stdout + save.stderr)
    assert save.returncode == 0, save.stdout + save.stderr
    for extension in ['.yaml','.pgm','.posegraph','.data','.metadata.json']:
        assert Path(str(RUN/'map')+extension).stat().st_size > 0, extension
    result['saved_map'] = str(RUN/'map.yaml')
    stop()
    # Drop stale /map and TF from the mapping session before AMCL is started.
    start('localization', RUN/'map.yaml')
    init = node.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
    wait(lambda: init.get_subscription_count() > 0, 60, 'AMCL initialpose subscriber')
    initial = PoseWithCovarianceStamped()
    initial.header.frame_id = 'map'
    initial.pose.pose.orientation.w = 1.0
    initial.pose.covariance[0] = initial.pose.covariance[7] = .10
    initial.pose.covariance[35] = .05
    for _ in range(5):
        initial.header.stamp = node.get_clock().now().to_msg()
        init.publish(initial)
        rclpy.spin_once(node, timeout_sec=.2)
    result['localization'] = ready()
    navigate(1.8, 0.2, 'localization')
    result['success'] = True
except Exception as exc:
    result['error'] = repr(exc)
finally:
    if process:
        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=25)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    if log:
        log.close()
    if node:
        node.destroy_node()
        rclpy.shutdown()
    (RUN/'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
raise SystemExit(0 if result['success'] else 1)
