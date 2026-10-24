"""Serial smoke test of the ordinary simulation entry points (domain 82 only).

Source ROS and the workspace, then explicitly pass --run after other simulations
have finished. This checks recording, manual save identity and AMCL restart, not
independent exploration quality. The user's latest.json bytes are restored.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from room_session import active_session, atomic_json, process_start_ticks
from scenarios import load_scenario
from check_exploration import stop_owned as stop_owned_group

SIMULATION = Path(__file__).resolve().parent


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def stop_owned(process, start_ticks):
    if process is None:
        return None
    cached = getattr(process,'normal_shutdown_report',None)
    if cached is not None:
        return cached
    if process.poll() is None:
        try:
            identity_matches = process_start_ticks(process.pid) == start_ticks
        except (FileNotFoundError,ProcessLookupError,ValueError) as exc:
            # The leader may exit between poll and /proc; its group still needs cleanup.
            if process.poll() is None:
                raise RuntimeError('Live owned process identity cannot be verified') from exc
        else:
            if not identity_matches:
                raise RuntimeError('Owned process identity changed; refusing to signal it')
    # Reuse the evaluator's group cleanup even when its leader has already died.
    state = stop_owned_group(process,timeout=35)
    state['forced'] = state['forced_kill']
    process.normal_shutdown_report = state
    return state


def clean_shutdown(state):
    return state is None or (not state['forced'] and not state.get('remaining_live_group_members')
                             and state['returncode'] in (0,-signal.SIGINT,130))

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Explicitly start the serial simulation smoke test')
    parser.add_argument('--explore-seconds',type=float,default=300,help='Wait this many wall seconds for exploration terminal status before manual save (max 300)')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--expected-latest-sha',help='Optional expected SHA-256 of the existing latest.json before starting')
    args = parser.parse_args(argv)
    if not args.run:
        parser.error('No simulation started. Pass --run only when the serial test is authorized.')
    if not math.isfinite(args.explore_seconds) or not 1 <= args.explore_seconds <= 300:
        parser.error('--explore-seconds must be between 1 and 300')
    def terminated(*_):
        raise KeyboardInterrupt('SIGTERM')
    signal.signal(signal.SIGTERM,terminated)
    data = Path.home()/'wheeltec_sim_ws/data'
    latest = data/'maps/latest.json'
    original = latest.read_bytes() if latest.is_file() else None
    if args.expected_latest_sha and (original is None or digest(original) != args.expected_latest_sha):
        raise SystemExit('Latest map selection differs from expected original SHA; nothing started')
    run = (args.output or data/'runs'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-normal-session-check')).expanduser().resolve()
    if not run.is_relative_to((data/'runs').resolve()):
        parser.error('--output must be a new directory under ~/wheeltec_sim_ws/data/runs')
    run.mkdir(parents=True,exist_ok=False)
    if original is not None:
        (run/'latest.original.json').write_bytes(original)
    report = {'success':False,'run_dir':str(run),'domain':82,'scenario':'l_shape','spawn_index':1,
              'latest_sha256_before':digest(original) if original is not None else None,'latest_existed_before':original is not None,'independent_exploration_assessment':False,'failures':[]}
    processes = []
    logs = []
    node = None
    os.environ.update(ROS_DOMAIN_ID='82',ROS_LOCALHOST_ONLY='1')
    try:
        import fcntl
        lock = os.open('/tmp/wheeltec-room-82.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:
            os.close(lock)
        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.signals import SignalHandlerOptions
        from rclpy.time import Time
        from tf2_ros import Buffer,TransformListener
        from tf2_msgs.msg import TFMessage
        from nav_msgs.msg import Odometry
        from geometry_msgs.msg import PoseWithCovarianceStamped
        from lifecycle_msgs.srv import GetState

        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)

        def observer():
            observer_node = rclpy.create_node('wheeltec_normal_session_check',
                parameter_overrides=[Parameter('use_sim_time',value=True)])
            observer_buffer = Buffer(node=observer_node)
            listener = TransformListener(observer_buffer,observer_node)
            observations = {'truth':[],'amcl':[],'odom':None,'odom_wall':None}
            def truth(message):
                for transform in message.transforms:
                    if transform.child_frame_id == 'wheeltec_reference':
                        p,q = transform.transform.translation,transform.transform.rotation
                        a = math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
                        if len(observations['truth'])<20:
                            observations['truth'].append([p.x,p.y,a])
            def odom(message):
                observations['odom'] = message
                observations['odom_wall'] = time.monotonic()
            odom_subscription = observer_node.create_subscription(Odometry,'/odom',odom,10)
            subscription = observer_node.create_subscription(TFMessage,'/simulation/ground_truth',truth,10)
            amcl_subscription = observer_node.create_subscription(PoseWithCovarianceStamped,'/amcl_pose',observations['amcl'].append,10)
            return observer_node,observer_buffer,listener,observations,subscription,amcl_subscription

        def spin_wait(predicate,timeout,label,process=None):
            deadline = time.monotonic()+timeout
            while time.monotonic()<deadline:
                rclpy.spin_once(node,timeout_sec=.05)
                if process is not None and process.poll() is not None:
                    raise RuntimeError(label+': launch exited')
                if predicate():
                    return
            raise RuntimeError('Timed out: '+label)

        def launch(arguments,name):
            log = (run/(name+'.log')).open('w')
            logs.append(log)
            process = subprocess.Popen([sys.executable,str(SIMULATION/'run_room.py'),*arguments,
                'gui:=false','rviz:=false','ros_domain_id:=82','partition:=wheeltec-normal-serial-check',
                'capture_browser:=false'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            ticks = process_start_ticks(process.pid)
            processes.append((name,process,ticks))
            atomic_json(run/'owned-processes.json',[{'name':n,'pid':p.pid,'start_ticks':s} for n,p,s in processes])
            return process,ticks

        def captured_run():
            log = (run/'explore.log').read_text(errors='replace')
            for line in log.splitlines():
                if line.startswith('过程目录 '):
                    return Path(line.removeprefix('过程目录 '))
            return None

        def recording_ready():
            directory = captured_run()
            if directory is None or not (directory/'process.json').is_file():
                return False
            document = json.loads((directory/'process.json').read_text())
            return len(document['frames'])>=3 and document.get('capture',{}).get('initial_pose') is not None

        node,buffer,listener,observations,truth_subscription,amcl_subscription = observer()
        print('Starting ordinary l_shape / spawn1 exploration on domain82',flush=True)
        explore,explore_ticks = launch(['explore:=true','scenario:=l_shape','spawn:=1'],'explore')
        spin_wait(lambda:active_session(data,82) is not None,30,'active normal session',explore)
        current = active_session(data,82)
        assert current['owner_pid']==explore.pid and current['simulation']['scenario']=='l_shape' and current['simulation']['spawn_index']==1
        report['exploration_session'] = current
        spin_wait(recording_ready,90,'normal process capture and estimated initial pose',explore)
        capture_run = captured_run()
        report['capture_run'] = str(capture_run)
        world = data/'worlds'/('room-'+str(explore.pid)+'.sdf')
        initial_world = world.read_bytes()
        scene = load_scenario('l_shape')
        expected_spawn = scene['spawns'][1]['pose']
        world_spawn = [float(x) for x in ET.fromstring(initial_world).find('world/include/pose').text.split()]
        assert math.dist(world_spawn[:2],expected_spawn[:2])<1e-9 and abs(world_spawn[5]-expected_spawn[2])<1e-9
        report['world_sha256_before'] = digest(initial_world)
        report['world_spawn'] = world_spawn
        deadline = time.monotonic()+args.explore_seconds
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
            if explore.poll() is not None:
                raise RuntimeError('Ordinary exploration launch exited unexpectedly')
            document = json.loads((capture_run/'process.json').read_text())
            if document.get('terminal'):
                break
        document = json.loads((capture_run/'process.json').read_text())
        if not document.get('terminal'):
            raise RuntimeError('Exploration did not reach terminal status within budget; refusing to save while it may be moving')
        stable_since = None
        def stationary():
            nonlocal stable_since
            odometry = observations['odom']
            fresh = observations['odom_wall'] is not None and time.monotonic()-observations['odom_wall']<1.0
            quiet = odometry is not None and math.hypot(odometry.twist.twist.linear.x,odometry.twist.twist.linear.y)<.015 and abs(odometry.twist.twist.angular.z)<.03
            if not fresh or not quiet:
                stable_since = None
                return False
            if stable_since is None:
                stable_since = time.monotonic()
            return time.monotonic()-stable_since>=1.0
        spin_wait(stationary,20,'stationary robot after exploration terminal',explore)
        report['stationary_before_manual_save'] = True
        initial_pose = document['capture']['initial_pose']
        report['normal_explorer_terminal_before_stop'] = document.get('terminal')
        report['initial_truth_world'] = observations['truth'][:1]
        print('Manually saving the current nondefault scene via save_map.py',flush=True)
        output = run/'manual-map/room'
        save_log = (run/'save-map.log').open('w')
        logs.append(save_log)
        save = subprocess.Popen([sys.executable,str(SIMULATION/'save_map.py'),'--output',str(output)],
            stdout=save_log,stderr=subprocess.STDOUT,start_new_session=True)
        save_ticks = process_start_ticks(save.pid)
        processes.append(('save',save,save_ticks))
        try:
            code = save.wait(timeout=80)
        except subprocess.TimeoutExpired:
            stop_owned(save,save_ticks)
            raise RuntimeError('Manual save timed out')
        if code != 0:
            raise RuntimeError('Manual save failed; see save-map.log')
        identity = json.loads(output.with_suffix('.simulation.json').read_text())
        assert identity == current['simulation']
        assert json.loads(latest.read_text())['map_yaml']==str(output.with_suffix('.yaml'))
        report['manual_saved_identity'] = identity
        report['manual_artifact_bytes'] = {}
        for suffix in ('.yaml','.pgm','.posegraph','.data','.metadata.json','.simulation.json'):
            path = output.with_suffix(suffix)
            assert path.is_file() and path.stat().st_size>0
            report['manual_artifact_bytes'][suffix] = path.stat().st_size
        report['exploration_shutdown'] = stop_owned(explore,explore_ticks)
        assert clean_shutdown(report['exploration_shutdown']),report['exploration_shutdown']
        assert active_session(data,82) is None
        finalized = json.loads((capture_run/'process.json').read_text())
        session = json.loads((capture_run/'session.json').read_text())
        assert session['recorder_exit_code']==0
        replay = capture_run/'replay.html'
        assert replay.is_file() and 'process-data' in replay.read_text()
        report['recording'] = {'frames':len(finalized['frames']),'maps':len(finalized['maps']),
                               'terminal':finalized.get('terminal'),'replay_bytes':replay.stat().st_size,
                               'recorder_exit_code':session['recorder_exit_code']}
        node.destroy_node()
        node,buffer,listener,observations,truth_subscription,amcl_subscription = observer()
        print('Restarting localization using latest only; no scenario/spawn override',flush=True)
        localization,localization_ticks = launch(['mode:=localization'],'localization')
        spin_wait(lambda:active_session(data,82) is not None,30,'active localization session',localization)
        restored = active_session(data,82)
        assert restored['owner_pid']==localization.pid and restored['simulation']==identity and restored['mode']=='localization'
        restored_world = data/'worlds'/('room-'+str(localization.pid)+'.sdf')
        assert digest(restored_world.read_bytes())==digest(initial_world)
        report['world_sha256_after'] = digest(restored_world.read_bytes())
        report['localization_session'] = restored
        lifecycle = node.create_client(GetState,'/amcl/get_state')
        spin_wait(lifecycle.service_is_ready,60,'AMCL lifecycle service',localization)
        active = False
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            future = lifecycle.call_async(GetState.Request())
            spin_wait(future.done,10,'AMCL lifecycle response',localization)
            if future.result().current_state.id == 3:
                active = True
                break
            until = time.monotonic()+.3
            spin_wait(lambda:time.monotonic()>=until,2,'AMCL settling',localization)
        assert active,'AMCL did not become active'
        publisher = node.create_publisher(PoseWithCovarianceStamped,'/initialpose',10)
        spin_wait(lambda:publisher.get_subscription_count()>0,15,'AMCL initial pose subscriber',localization)
        request = PoseWithCovarianceStamped()
        request.header.frame_id = 'map'
        request.header.stamp = node.get_clock().now().to_msg()
        request.pose.pose.position.x,request.pose.pose.position.y = initial_pose[:2]
        request.pose.pose.orientation.z = math.sin(initial_pose[2]/2)
        request.pose.pose.orientation.w = math.cos(initial_pose[2]/2)
        request.pose.covariance[0]=.25
        request.pose.covariance[7]=.25
        request.pose.covariance[35]=.0685
        publisher.publish(request)
        spin_wait(lambda:len(observations['amcl'])>0,30,'AMCL estimated pose after user initial pose',localization)
        spin_wait(lambda:buffer.can_transform('map','base_link',Time()),10,'fresh AMCL map transform',localization)
        transform = buffer.lookup_transform('map','base_link',Time()).transform
        report['amcl_active'] = True
        report['localized_map_pose'] = [transform.translation.x,transform.translation.y,
            math.atan2(2*(transform.rotation.w*transform.rotation.z+transform.rotation.x*transform.rotation.y),
                       1-2*(transform.rotation.y**2+transform.rotation.z**2))]
        assert math.dist(report['localized_map_pose'][:2],initial_pose[:2])<.35
        spin_wait(lambda:len(observations['truth'])>0,10,'localization simulator initial pose',localization)
        report['localized_truth_world'] = observations['truth'][0]
        assert math.dist(observations['truth'][0][:2],expected_spawn[:2])<.05
        report['localization_shutdown'] = stop_owned(localization,localization_ticks)
        assert clean_shutdown(report['localization_shutdown']),report['localization_shutdown']
        report['success'] = True
    except (Exception,KeyboardInterrupt) as exc:
        report['failures'].append(repr(exc))
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        for name,process,ticks in reversed(processes):
            try:
                state = stop_owned(process,ticks)
                report.setdefault('cleanup',{})[name] = state
                if not clean_shutdown(state):
                    report['failures'].append('abnormal shutdown '+name+': '+repr(state))
            except Exception as exc:
                report['failures'].append('cleanup '+name+': '+repr(exc))
        try:
            if node is not None:
                node.destroy_node()
                if rclpy.ok():
                    rclpy.shutdown()
        except Exception as exc:
            report['failures'].append('observer cleanup: '+repr(exc))
        for log in logs:
            try:
                log.close()
            except Exception as exc:
                report['failures'].append('log cleanup: '+repr(exc))
        if original is not None:
            temporary = latest.with_name(latest.name+'.normal-check-restore.tmp')
            temporary.write_bytes(original)
            temporary.replace(latest)
        elif latest.exists():
            latest.unlink()
        restored = latest.read_bytes() if latest.is_file() else None
        report['latest_sha256_after'] = digest(restored) if restored is not None else None
        report['latest_restored_exactly'] = restored==original
        report['success'] = report['success'] and report['latest_restored_exactly'] and not report['failures']
        atomic_json(run/'result.json',report)
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
