"""Run the real frontier explorer with SLAM/Nav2, then assess saved map and return.

Run after sourcing ROS and the WSL workspace. Simulation truth is subscribed only
by this evaluator; no truth data is passed to SLAM, Nav2 or frontier selection.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--task-timeout',type=float,default=300.0,
                    help='Explorer wall-clock budget before saving and returning')
parser.add_argument('--timeout',type=float,default=460.0,
                    help='Evaluator deadline including map saving and return')
arguments = parser.parse_args()
if arguments.task_timeout <= 0 or arguments.timeout <= arguments.task_timeout:
    parser.error('--timeout must exceed the positive --task-timeout')

ROOT = Path(__file__).resolve().parents[1]
RUN = Path.home()/'wheeltec_sim_ws/data/runs'/(time.strftime('%Y%m%d-%H%M%S')+'_exploration')
RUN.mkdir(parents=True,exist_ok=False)
os.environ.update(ROS_LOCALHOST_ONLY='1',ROS_DOMAIN_ID='80')
result = {'success':False,'run_dir':str(RUN),'ros_domain_id':80,
          'task_timeout_wall_seconds':arguments.task_timeout,
          'ground_truth_used_only_for_evaluation':True,'status_history':[]}
launch_process = explorer_process = node = None
launch_log = explorer_log = None
latest = {}
start_wall = time.monotonic()


def stop_owned(process):
    """Signal only our child; kill only its independently created group on timeout."""
    if process is None:
        return
    try:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=25)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=5)


try:
    import rclpy
    from rclpy.parameter import Parameter
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from rclpy.signals import SignalHandlerOptions
    from lifecycle_msgs.srv import GetState
    from nav_msgs.msg import OccupancyGrid
    from std_msgs.msg import String
    from tf2_msgs.msg import TFMessage
    from tf2_ros import Buffer, TransformListener

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('wheeltec_exploration_check',
                            parameter_overrides=[Parameter('use_sim_time',value=True)])
    qos = QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def receive_status(message):
        report = json.loads(message.data)
        latest['status'] = report
        entry = {key:report[key] for key in ('state','reason','elapsed_wall_seconds') if key in report}
        result['status_history'].append(entry)
        print(json.dumps(entry),flush=True)

    def receive_truth(message):
        for transform in message.transforms:
            if transform.child_frame_id=='wheeltec_reference':
                p = transform.transform.translation
                point = (p.x,p.y)
                latest['truth'] = point
                if 'initial_truth_world_m' not in result:
                    result['initial_truth_world_m'] = list(point)
                initial = result['initial_truth_world_m']
                result['maximum_distance_from_start_m'] = max(
                    result.get('maximum_distance_from_start_m',0.0),math.dist(point,initial))
                return

    subscriptions = [
        node.create_subscription(String,'/exploration/status',receive_status,qos),
        node.create_subscription(TFMessage,'/simulation/ground_truth',receive_truth,10),
        node.create_subscription(OccupancyGrid,'/map',lambda m:latest.update(map=m),qos),
    ]
    costmap_subscription = node.create_subscription(OccupancyGrid, '/global_costmap/costmap', lambda m:latest.update(costmap=m), qos)
    buffer = Buffer(node=node)
    transform_listener = TransformListener(buffer,node)
    snapshots = []
    def snapshot():
        if latest.get('status',{}).get('state') not in ('returning','failed','incomplete','completed'):
            return
        try:
            transform = buffer.lookup_transform('map','base_link',rclpy.time.Time()).transform
        except Exception:
            return
        entry = {'wall_elapsed':time.monotonic()-start_wall,
                 'state':latest['status']['state'],
                 'estimated_position':[transform.translation.x,transform.translation.y],
                 'orientation':[transform.rotation.x,transform.rotation.y,transform.rotation.z,transform.rotation.w],
                 'truth':latest.get('truth')}
        for name in ('map','costmap'):
            m = latest.get(name)
            if m is not None:
                entry[name]={'width':m.info.width,'height':m.info.height,'resolution':m.info.resolution,
                             'origin':[m.info.origin.position.x,m.info.origin.position.y], 'data':list(m.data)}
        path = RUN/('return-snapshot-%03d.json'%len(snapshots))
        path.write_text(json.dumps(entry))
        snapshots.append(path.name)
        result['return_snapshots'] = snapshots[:]
    snapshot_timer = node.create_timer(2.0,snapshot)
    lifecycle = node.create_client(GetState,'/bt_navigator/get_state')

    def wait(predicate,timeout,reason,check_explorer=False):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=0.05)
            if launch_process is not None and launch_process.poll() is not None:
                raise RuntimeError('Simulation launch exited; see launch.log')
            if predicate():
                return
            if check_explorer and explorer_process.poll() is not None:
                # Drain the durable terminal status already queued before exit.
                for _ in range(20):
                    rclpy.spin_once(node,timeout_sec=0.05)
                    if predicate():
                        return
                raise RuntimeError('Explorer exited before reporting a terminal status; see explore.log')
        raise RuntimeError('Timeout: '+reason)

    launch_log = (RUN/'launch.log').open('w')
    launch_process = subprocess.Popen(
        [sys.executable,str(ROOT/'simulation/run_room.py'),'gui:=false','rviz:=false',
         'mode:=mapping','navigation:=true','explore:=false','ros_domain_id:=80',
         'partition:=wheeltec-exploration-check-'+str(os.getpid())],
        stdout=launch_log,stderr=subprocess.STDOUT,start_new_session=True)
    wait(lambda:'map' in latest and 'truth' in latest and lifecycle.service_is_ready(),
         85,'SLAM map, evaluation ground truth and Nav2 lifecycle')
    active_deadline = time.monotonic()+45
    while True:
        future = lifecycle.call_async(GetState.Request())
        wait(future.done,10,'Nav2 lifecycle response')
        if future.result().current_state.id==3:
            break
        if time.monotonic()>=active_deadline:
            raise RuntimeError('Nav2 did not reach active state')
        until = time.monotonic()+0.5
        wait(lambda:time.monotonic()>=until,2,'Nav2 lifecycle settling')
    assert math.dist(result['initial_truth_world_m'],(-1.7,-1.5))<0.05, result['initial_truth_world_m']

    # Start the same installed algorithm as explore:=true, with bounded test
    # parameters and artifacts grouped in this test run, after Nav2 is active.
    explorer_log = (RUN/'explore.log').open('w')
    workspace_setup = Path.home()/'wheeltec_sim_ws/install/setup.bash'
    command = ('source /opt/ros/humble/setup.bash && source "$1" && shift && '
               'exec ros2 run wheeltec_explore explore "$@"')
    explorer_process = subprocess.Popen(
        ['bash','-lc',command,'wheeltec-exploration-check',str(workspace_setup),
         '--ros-args','-p','use_sim_time:=true','-p','map_output:='+str(RUN/'map'),
         '-p','task_timeout:='+str(arguments.task_timeout),'-p','goal_timeout:=75.0',
         '-p','reference_yaw_rad:=0.0','-p','max_goals:=60'],
        stdout=explorer_log,stderr=subprocess.STDOUT,start_new_session=True)
    wait(lambda:latest.get('status',{}).get('state') in ('completed','incomplete','failed'),
         arguments.timeout,'exploration terminal status',check_explorer=True)
    terminal = latest['status']
    result['explorer'] = terminal
    # Let the last velocity command settle and collect the final simulator pose.
    until = time.monotonic()+1.0
    wait(lambda:time.monotonic()>=until,3,'final truth sample')
    result['final_truth_world_m'] = list(latest['truth'])
    result['gazebo_return_error_m'] = math.dist(latest['truth'],result['initial_truth_world_m'])
    result['artifact_bytes'] = {}
    for extension in ('.yaml','.pgm','.posegraph','.data','.metadata.json'):
        artifact = Path(str(RUN/'map')+extension)
        assert artifact.is_file() and artifact.stat().st_size>0, 'Missing map artifact: '+extension
        result['artifact_bytes'][extension] = artifact.stat().st_size
    metadata = json.loads(Path(str(RUN/'map')+'.metadata.json').read_text())
    assert metadata['map_yaml']==str(RUN/'map.yaml'), metadata
    assert metadata['posegraph']==str(RUN/'map'), metadata
    assert metadata['reference_yaw_rad']==0.0, metadata
    result['map_metadata'] = metadata
    assert terminal.get('map_saved') is True, terminal
    assert terminal.get('returned') is True, terminal
    assert result['gazebo_return_error_m']<0.22, result['gazebo_return_error_m']
    assert terminal['state']=='completed', terminal
    result['success'] = True
except KeyboardInterrupt:
    result['error'] = 'operator_interrupted'
except Exception as exc:
    result['error'] = repr(exc)
finally:
    # A second Ctrl+C must not interrupt owned-process cleanup or lose evidence.
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    if 'status' in latest:
        result['explorer'] = latest['status']
    (RUN/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    # Explorer cancels its own Nav2 goal while the ROS stack is still alive.
    stop_owned(explorer_process)
    stop_owned(launch_process)
    if explorer_log is not None:
        explorer_log.close()
    if launch_log is not None:
        launch_log.close()
    if node is not None:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    result['elapsed_wall_seconds'] = time.monotonic()-start_wall
    (RUN/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)

raise SystemExit(0 if result['success'] else 1)