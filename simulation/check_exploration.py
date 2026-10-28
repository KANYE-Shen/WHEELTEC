"""Run real exploration in an isolated room and retain every outcome and replay.

Source ROS and the workspace first. A selected scenario uses domain 83; the
legacy baseline check keeps domain 80. Truth and source geometry are evaluator
inputs only and are excluded from process.json and exploration interfaces.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
from resource_monitor import ProcessResources
from truth_capture import GazeboTruthCapture,truth_quality,synchronize_terminal_truth


def parse_arguments(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--realism',choices=['on','off'],default='on')
    parser.add_argument('--viewpoint-strategy',choices=['centroid','visibility'],default='centroid')
    parser.add_argument('--active-scan-angle',type=float,choices=[0.,90.,180.,360.],default=0.)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--noise-scale',type=float,default=1.)
    parser.add_argument('--task-timeout',type=float,default=300.0,help='Explorer ROS-time budget before saving and returning')
    parser.add_argument('--timeout',type=float,default=460.0,help='Evaluator deadline after explorer start, including saving and return')
    parser.add_argument('--scenario',help='Source scenario ID; omitted keeps the existing baseline world')
    parser.add_argument('--spawn',type=int,default=0,help='Zero-based named spawn index')
    parser.add_argument('--spawn-pose',type=float,nargs=3,help='Evaluator/runtime seeded x y yaw; never supplied to algorithms')
    parser.add_argument('--output',type=Path,help='New run directory, normally under ~/wheeltec_sim_ws/data/runs')
    parser.add_argument('--domain',type=int,help='ROS domain override; default 83 for scenarios, otherwise 80')
    recording=parser.add_mutually_exclusive_group()
    recording.add_argument('--record',dest='record',action='store_true',help='Record rosbag2 and verify its topic message counts')
    recording.add_argument('--no-record',dest='record',action='store_false',help='Keep JSON process capture without a rosbag')
    parser.set_defaults(record=False)
    args=parser.parse_args(argv)
    if not all(math.isfinite(value) for value in (args.task_timeout,args.timeout)):
        parser.error('timeouts must be finite')
    if args.seed<0 or not math.isfinite(args.noise_scale) or args.noise_scale<0:
        parser.error('seed and noise scale must be nonnegative and finite')
    if args.domain is not None and not 0<=args.domain<=232:
        parser.error('--domain must be between 0 and 232')
    if args.task_timeout<=0 or args.timeout<=args.task_timeout:
        parser.error('--timeout must exceed the positive --task-timeout')
    if args.spawn<0 or (args.spawn!=0 and args.scenario is None):
        parser.error('--spawn must be nonnegative and requires --scenario for nonzero starts')
    return args


def _live_group_members(pgid):
    """Linux owned-group liveness; terminated zombies need no more signals."""
    members=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields=(entry/'stat').read_text().rpartition(')')[2].split()
            if int(fields[2])==pgid and fields[0] not in ('Z','X','x'):
                members.append(int(entry.name))
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            pass
    return sorted(members)


def stop_owned(process,timeout=25.0):
    """Reap the owned leader and stop its group even if the leader died first."""
    if process is None:
        return None
    pgid=process.pid
    forced=False
    deadline=time.monotonic()+timeout
    try:
        os.killpg(pgid,signal.SIGINT)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=max(0,deadline-time.monotonic()))
    except subprocess.TimeoutExpired:
        pass
    members=_live_group_members(pgid)
    while members and time.monotonic()<deadline:
        time.sleep(min(.05,max(0,deadline-time.monotonic())))
        process.poll()
        members=_live_group_members(pgid)
    if members:
        try:
            os.killpg(pgid,signal.SIGKILL)
            forced=True
        except ProcessLookupError:
            pass
    process.wait(timeout=5)
    deadline=time.monotonic()+2
    members=_live_group_members(pgid)
    while members and time.monotonic()<deadline:
        time.sleep(.02)
        members=_live_group_members(pgid)
    return {'returncode':process.returncode,'forced_kill':forced,
            'process_group_id':pgid,'remaining_live_group_members':members}

def shutdown_abnormal(name, state, terminal):
    if state is None:
        return False
    expected_codes = (0, -signal.SIGINT, 130)
    if name == 'explorer' and terminal.get('state') in ('incomplete','failed','map_unstable'):
        expected_codes += (2,)
    return bool(state['forced_kill'] or state.get('remaining_live_group_members')
                or state['returncode'] not in expected_codes)


def launch_shutdown_abnormal(text):
    """ROS launch can hide a killed child behind a successful wrapper exit."""
    return "sending signal 'SIGKILL'" in text or 'exit code -9' in text


def drain_terminal_status(predicate, spin_once, now=time.monotonic, timeout=1.):
    # Twenty immediately-ready /clock callbacks are not one second of DDS grace.
    deadline=now()+timeout
    while not predicate():
        if now()>=deadline:
            return False
        spin_once(.05)
    return True


def source_manifest():
    files=[]
    for directory in (ROOT/'simulation',ROOT/'src/wheeltec_explore'):
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.suffix in ('.py','.yaml','.xml','.sdf','.json','.cc','.hh','.qml') and '__pycache__' not in path.parts:
                files.append(path)
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    revision=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True)
    return {'git_revision':revision.stdout.strip() if revision.returncode==0 else None,'sha256':hashes}


def verify_bag(path):
    import yaml
    info=subprocess.run(['ros2','bag','info',str(path)],capture_output=True,text=True,timeout=30)
    report={'info_returncode':info.returncode,'info':info.stdout,'error':info.stderr}
    if info.returncode!=0:
        report['readable']=False
        return report
    metadata=yaml.safe_load((path/'metadata.yaml').read_text())['rosbag2_bagfile_information']
    counts={item['topic_metadata']['name']:item['message_count'] for item in metadata['topics_with_message_count']}
    required=('/scan','/odom','/tf','/tf_static','/map','/exploration/status','/clock','/plan')
    report.update(readable=True,topic_message_counts=counts,
                  missing_or_empty_topics=[name for name in required if counts.get(name,0)==0])
    return report


def main(argv=None):
    args=parse_arguments(argv)
    from scenarios import load_scenario
    from map_metrics import initial_alignment,load_saved_grid,score_map,trajectory_safety
    from process_capture import ProcessCapture,yaw
    scene=load_scenario(args.scenario or 'baseline')
    if args.spawn>=len(scene['spawns']):
        raise SystemExit('spawn index out of range')
    spawn=scene['spawns'][args.spawn]
    if args.spawn_pose is not None:
        if args.scenario is None or not all(math.isfinite(x) for x in args.spawn_pose):
            raise SystemExit('finite --spawn-pose requires --scenario')
        spawn={**spawn,'pose':args.spawn_pose,'named_pose':spawn['pose']}
    domain=args.domain if args.domain is not None else (83 if args.scenario else 80)
    run=args.output.expanduser().resolve() if args.output else Path.home()/'wheeltec_sim_ws/data/runs'/(time.strftime('%Y%m%d-%H%M%S')+'_'+scene['id']+'_spawn'+str(args.spawn))
    run.mkdir(parents=True,exist_ok=False)
    os.environ.update(ROS_LOCALHOST_ONLY='1',ROS_DOMAIN_ID=str(domain))
    result={'success':False,'run_dir':str(run),'ros_domain_id':domain,
            'scenario':scene['id'],'spawn_index':args.spawn,'spawn':spawn,
            'viewpoint_strategy':args.viewpoint_strategy,'active_scan_angle_deg':args.active_scan_angle,
            'realism_mode':args.realism,'seed':args.seed,'noise_scale':args.noise_scale,
            'real_robot_admission_ready':False,
            'task_timeout_ros_seconds':args.task_timeout,'record_requested':args.record,
            'ground_truth_used_only_for_evaluation':True,'status_history':[],
            'failures':[],'source':source_manifest()}
    latest_selector=Path.home()/'wheeltec_sim_ws/data/maps/latest.json'
    result['latest_selector_sha256_before']=hashlib.sha256(latest_selector.read_bytes()).hexdigest() if latest_selector.is_file() else None
    launch_process=explorer_process=recorder_process=node=capture=truth_capture=None
    logs=[]
    resources=ProcessResources(run/'resources.jsonl')
    latest={}
    truth=[]
    started=time.monotonic()
    shutdown={}
    task_start_wall_t=None
    partition='wheeltec-validation-'+str(os.getpid())
    try:
        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.qos import QoSProfile,DurabilityPolicy
        from rclpy.signals import SignalHandlerOptions
        from lifecycle_msgs.srv import GetState
        from tf2_ros import Buffer,TransformListener
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node=rclpy.create_node('wheeltec_exploration_check',parameter_overrides=[Parameter('use_sim_time',value=True)])
        buffer=Buffer(node=node)
        listener=TransformListener(buffer,node)
        metadata={'id':scene['id'],'name':scene['name'],'spawn_index':args.spawn,'spawn_name':spawn['name']}
        capture=ProcessCapture(node,buffer,run/'process.json',metadata)
        truth_capture=GazeboTruthCapture(partition,started,run/'truth-reader.log')
        def drain_truth():
            for sample in truth_capture.drain():
                pose=sample['pose']
                truth.append(sample)
                latest['truth']=pose
                if 'initial_truth_world_m' not in result:
                    result['initial_truth_world_m']=pose[:2]
                result['maximum_distance_from_start_m']=max(result.get('maximum_distance_from_start_m',0),math.dist(pose[:2],result['initial_truth_world_m']))
        lifecycle=node.create_client(GetState,'/bt_navigator/get_state')
        def wait(predicate,timeout,reason,check_explorer=False):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                rclpy.spin_once(node,timeout_sec=.05)
                drain_truth()
                resources.tick({p.pid for p in (launch_process,explorer_process) if p is not None})
                if truth_capture.process.poll() is not None:
                    raise RuntimeError('Evaluation truth reader exited; see truth-reader.log')
                if launch_process is not None and launch_process.poll() is not None:
                    raise RuntimeError('Simulation launch exited; see launch.log')
                if recorder_process is not None and recorder_process.poll() is not None:
                    raise RuntimeError('Recorder exited prematurely; see bag.log')
                if predicate():
                    return
                if check_explorer and explorer_process.poll() is not None:
                    if drain_terminal_status(predicate,lambda timeout:rclpy.spin_once(node,timeout_sec=timeout)):
                        return
                    raise RuntimeError('Explorer exited before terminal status; see explore.log')
            raise RuntimeError('Timeout: '+reason)
        def launch(command,log_name):
            log=(run/log_name).open('w')
            logs.append(log)
            return subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        if args.record:
            qos=run/'bag-qos.yaml'
            qos.write_text('\n'.join(name+':\n  durability: transient_local\n  reliability: reliable\n  history: keep_last\n  depth: 10' for name in ('/map','/tf_static','/exploration/status'))+'\n')
            recorder_process=launch(['ros2','bag','record','--use-sim-time','--qos-profile-overrides-path',str(qos),
                                     '-o',str(run/'bag'),'/scan','/odom','/tf','/tf_static','/map','/exploration/status','/clock','/plan'],'bag.log')
        command=[sys.executable,str(ROOT/'simulation/run_room.py'),'gui:=false','rviz:=false',
                 'mode:=mapping','navigation:=true','explore:=false','ros_domain_id:='+str(domain),
                 'partition:='+partition,'realism:='+args.realism,'seed:='+str(args.seed),
                 'noise_scale:='+str(args.noise_scale),'realism_assets:='+str(run/'realism')]
        if args.scenario:
            command+=['scenario:='+args.scenario,'spawn:='+str(args.spawn)]
        if args.spawn_pose is not None: command+=['spawn_pose:='+json.dumps(args.spawn_pose,separators=(',',':'))]
        launch_process=launch(command,'launch.log')
        wait(lambda:capture.timeline.map_index is not None and 'truth' in latest and lifecycle.service_is_ready(),
             100,'SLAM map, truth and Nav2 lifecycle')
        deadline=time.monotonic()+45
        while True:
            future=lifecycle.call_async(GetState.Request())
            wait(future.done,10,'Nav2 lifecycle response')
            if future.result().current_state.id==3:
                break
            if time.monotonic()>deadline:
                raise RuntimeError('Nav2 did not become active')
            until=time.monotonic()+.5
            wait(lambda:time.monotonic()>=until,2,'Nav2 settling')
        wait(lambda:capture.initial_pose is not None,20,'initial map pose')
        if math.dist(result['initial_truth_world_m'],spawn['pose'][:2])>.05:
            raise RuntimeError('Simulator spawn differs from selected scenario')
        result['initial_map_pose']=capture.initial_pose
        result['map_from_world']=initial_alignment(spawn['pose'],capture.initial_pose)
        if args.realism=='on':
            result['realism']=json.loads((run/'realism/manifest.json').read_text())
        setup=Path.home()/'wheeltec_sim_ws/install/setup.bash'
        command='source /opt/ros/humble/setup.bash && source "$1" && shift && exec ros2 run wheeltec_explore explore "$@"'
        task_start_wall_t=time.monotonic()-started
        explorer_command=['bash','-lc',command,'wheeltec-exploration-check',str(setup),
                                '--ros-args','-p','use_sim_time:=true','-p','map_output:='+str(run/'map'),
                                '-p','update_latest:=false','-p','frontier_viewpoint_strategy:='+args.viewpoint_strategy,
                                '-p','active_scan_angle_deg:='+str(args.active_scan_angle),
                                '-p','expected_status_observers:='+str(2 if args.record else 1),
                                '-p','task_timeout:='+str(args.task_timeout),
                                '-p','goal_timeout:=75.0','-p','reference_yaw_rad:=0.0','-p','max_goals:=60',
                                '-p','robot_radius:='+str(result.get('realism',{}).get('robot_radius',.35))]
        affinity=result.get('realism',{}).get('cpu_affinity')
        if affinity: explorer_command=['taskset','-c',','.join(map(str,affinity)),*explorer_command]
        explorer_process=launch(explorer_command,'explore.log')
        wait(lambda:capture.status.get('state') in ('completed','completed_with_residual_frontiers','incomplete','failed','map_unstable'),args.timeout,'exploration terminal status',True)
        until=time.monotonic()+1
        wait(lambda:time.monotonic()>=until,3,'final truth settling')
    except KeyboardInterrupt:
        result['failures'].append('operator_interrupted')
    except Exception as exc:
        result['failures'].append(repr(exc))
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        # Stop periodic serialization before synchronizing callback-ordered ROS
        # time with the independently timestamped worker; freeze before writes
        # and owned shutdown. Historical quality failures are never retried away.
        if capture is not None:
            capture.timer.cancel()
            capture.wall_timer.cancel()
        if truth_capture is not None and node is not None:
            result['truth_quality']=synchronize_terminal_truth(
                truth,drain_truth,lambda timeout:rclpy.spin_once(node,timeout_sec=timeout),
                lambda:node.get_clock().now().nanoseconds/1e9,started,
                task_start_wall_t=task_start_wall_t or 0.0)
        else:
            result['truth_quality']=truth_quality(truth,time.monotonic()-started,
                                                 task_start_wall_t=task_start_wall_t or 0.0)
        if not result['truth_quality']['valid']:
            result['failures'].append('Invalid evaluation truth: '+', '.join(result['truth_quality']['issues']))
        if capture is not None:
            result['explorer']=capture.status
            result['status_history']=capture.timeline.document['statuses']
            capture.close(capture.status or {'state':'failed','reason':result['failures']})
            result['process_capture']={'path':str(run/'process.json'),'frames':len(capture.timeline.document['frames']),
                                       'maps':len(capture.timeline.document['maps']),'issues':capture.issue_counts}
        # Finalize rosbag metadata while the stack and its publishers are alive.
        for name,process in (('recorder',recorder_process),('explorer',explorer_process),('launch',launch_process),
                             ('truth_reader',truth_capture.process if truth_capture is not None else None)):
            try:
                shutdown[name]=stop_owned(process)
            except Exception as exc:
                result['failures'].append('shutdown '+name+': '+repr(exc))
        if truth_capture is not None:
            truth_capture.close()
            result['truth_source']=truth_capture.diagnostics()
            if result['truth_source']['parse_errors'] or result['truth_source']['queue_dropped_samples'] or result['truth_source']['reader_error']:
                result['failures'].append('Evaluation truth reader lost or rejected data')
        result['resource_summary']=resources.summary
        result['cpu_measurement_scope']='WSL host reference; not RDK X5 measured performance'
        result['shutdown']=shutdown
        for name,state in shutdown.items():
            if shutdown_abnormal(name,state,result.get('explorer',{})):
                result['failures'].append('abnormal shutdown '+name+': '+repr(state))
        result['latest_selector_sha256_after']=hashlib.sha256(latest_selector.read_bytes()).hexdigest() if latest_selector.is_file() else None
        if result['latest_selector_sha256_after']!=result['latest_selector_sha256_before']:
            result['failures'].append('User latest map selection changed during validation')
        for log in logs:
            log.close()
        launch_log=run/'launch.log'
        if launch_log.is_file() and launch_shutdown_abnormal(launch_log.read_text(errors='replace')):
            result['failures'].append('abnormal shutdown: launch reported nested SIGKILL')
        if node is not None:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        (run/'truth.json').write_text(json.dumps({'version':1,'coordinate_frame':'world','evaluator_only':True,
                                                 'scenario':scene,'source':result.get('truth_source'),
                                                 'quality':result['truth_quality'],'trajectory':truth},separators=(',',':'))+'\n')
        result['gazebo_return_error_m']=None
        result['truth_traveled_distance_m']=None
        if result['truth_quality']['valid']:
            result['final_truth_world_m']=truth[-1]['pose'][:2]
            result['gazebo_return_error_m']=math.dist(truth[-1]['pose'][:2],result['initial_truth_world_m'])
            result['truth_traveled_distance_m']=sum(math.dist(a['pose'][:2],b['pose'][:2]) for a,b in zip(truth,truth[1:]))
            result['trajectory_safety']=trajectory_safety(scene,[entry['pose'] for entry in truth],
                 model_path=run/'realism/model.sdf' if args.realism=='on' and (run/'realism/model.sdf').is_file() else None)
        else:
            result['final_truth_world_m']=None
            result['trajectory_safety']={'contact_measurement':'unavailable_invalid_truth',
                'minimum_clearance_m':None,'geometric_overlap_samples':None,
                'geometric_overlap_events':None,'samples':len(truth),'quality':result['truth_quality']}
        if capture is not None and capture.initial_pose is not None:
            transform=result.get('map_from_world') or initial_alignment(spawn['pose'],capture.initial_pose)
            try:
                if capture.timeline.map_index is not None:
                    result['map_metrics']=score_map(scene,capture.timeline.document['maps'][capture.timeline.map_index],transform,spawn['pose'])
                if (run/'map.yaml').is_file():
                    result['saved_map_metrics']=score_map(scene,load_saved_grid(run/'map.yaml'),transform,spawn['pose'])
            except Exception as exc:
                result['failures'].append('map metrics: '+repr(exc))
        result['artifact_bytes']={}
        for suffix in ('.yaml','.pgm','.posegraph','.data','.metadata.json'):
            artifact=Path(str(run/'map')+suffix)
            if artifact.is_file() and artifact.stat().st_size:
                result['artifact_bytes'][suffix]=artifact.stat().st_size
            else:
                result['failures'].append('Missing map artifact '+suffix)
        if (run/'map.metadata.json').is_file():
            result['map_metadata']=json.loads((run/'map.metadata.json').read_text())
        if args.record:
            try:
                result['rosbag']=verify_bag(run/'bag')
                if not result['rosbag']['readable'] or result['rosbag'].get('missing_or_empty_topics'):
                    result['failures'].append('rosbag missing required messages or unreadable')
            except Exception as exc:
                result['failures'].append('rosbag verification: '+repr(exc))
        terminal=result.get('explorer',{})
        metrics=result.get('saved_map_metrics',{})
        result['acceptance']={
            'truth_quality':result['truth_quality']['valid'],
            'completed':terminal.get('state') in ('completed','completed_with_residual_frontiers'),
            'map_saved':terminal.get('map_saved') is True,
            'returned':terminal.get('returned') is True,
            'return_error':result['gazebo_return_error_m'] is not None and result['gazebo_return_error_m']<(.20 if args.scenario else .22),
            'no_geometric_overlap':result['trajectory_safety']['geometric_overlap_samples']==0,
            'reachable_coverage':metrics.get('reachable_coverage',0)>=.95,
            'observable_contour_p95':metrics.get('observable_contour_symmetric_p95_m') is not None and metrics['observable_contour_symmetric_p95_m']<=.10,
            'observable_contour_coverage':metrics.get('observable_contour_coverage',0)>=.95}
        result['functional_success']=all(result['acceptance'].values()) and not result['failures']
        result['acceptance']['realism_enabled']=args.realism=='on'
        result['success']=result['functional_success'] and args.realism=='on'
        result['elapsed_wall_seconds']=time.monotonic()-started
        if result['failures']:
            result['error']=result['failures'][0]
        (run/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)
    return 0 if result['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
