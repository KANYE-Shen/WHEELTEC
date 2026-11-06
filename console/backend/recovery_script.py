"""Fixed-purpose robot adapter inspection/restoration, sent over pinned SSH.

No command, path or source code is accepted from an HTTP request. Restoring
requires the exact previously deployed command and live parked-chain evidence.
"""
import json
import math
import os
from pathlib import Path
import re
import shlex
import time

COMPONENTS = ('lidar','camera','model','ekf','control_stack','base_feedback','slam')

def runtime_root():
    return Path.home()/'.wheeltec-console/trial-20261031'

def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

def adapter_command(root):
    home = root.parent.parent
    q = shlex.quote
    return ('source /opt/ros/humble/setup.bash && source '+q(str(home/'wheeltec_ros2/install/setup.bash'))+
            ' && cd '+q(str(root))+' && exec python3 -m console.target.adapter --kind robot --robot-config '+
            q(str(root/'robot-live.json'))+' --token-file '+q(str(root.parent/'adapter.token'))+
            ' --mapping-runtime '+q(str(root/'owned-processes.json')))

def identity(record, boot):
    try:
        parts=Path('/proc',str(int(record['pid'])),'stat').read_text().rsplit(')',1)[1].split()
        return parts[0]!='Z' and parts[19]==str(record.get('start_ticks')) and record.get('boot_id')==boot
    except (FileNotFoundError,ProcessLookupError,KeyError,ValueError,TypeError):
        return False

def listening():
    for name in ('tcp','tcp6'):
        for line in Path('/proc/net',name).read_text().splitlines()[1:]:
            fields=line.split()
            if int(fields[1].rsplit(':',1)[1],16)==8767 and fields[3]=='0A':
                return True
    return False

def inspect_adapter():
    root=runtime_root()
    receipt=root/'owned-processes.json'
    if not receipt.is_file():
        return {'status':'blocked','reason':'runtime_manifest_missing','missing_services':list(COMPONENTS)}
    records=json.loads(receipt.read_text())
    boot=boot_id()
    states={name:{'pid':records.get(name,{}).get('pid'),
                  'alive':identity(records.get(name,{}),boot)} for name in (*COMPONENTS,'adapter')}
    adapter=records.get('adapter',{})
    tail=''
    log=Path(adapter.get('log',''))
    if log.is_absolute() and log.resolve().is_relative_to(root.resolve()) and log.is_file():
        with log.open('rb') as source:
            source.seek(0,2)
            source.seek(max(0,source.tell()-16384))
            tail=source.read(16384).decode('utf-8',errors='replace')
        token_file=root.parent/'adapter.token'
        if token_file.is_file():
            token=token_file.read_text().strip()
            if token:tail=tail.replace(token,'[redacted]')
        tail='\n'.join('[credential-related line omitted]' if re.search(
            r'password|authorization|bearer|token',line,re.I) else line for line in tail.splitlines())
    return {'status':'inspected','boot_id':boot,'wall_time':time.time(),'processes':states,'listening':listening(),
            'missing_services':[name for name in COMPONENTS if not states[name]['alive']],
            'command_matches':adapter.get('command')==adapter_command(root),'log_tail':tail}

def recovery_blocker(evidence):
    if evidence.get('reason'):return evidence['reason']
    if evidence.get('missing_services'):return 'other_services_missing'
    if evidence.get('listening'):return 'adapter_already_listening'
    if evidence['processes']['adapter']['alive']:return 'adapter_still_running'
    if not evidence.get('command_matches'):return 'adapter_command_changed'
    return None

def parked_blocker(data, received, now, nonzero, explorer, lifecycle, require_odom=True, require_navigation=True):
    required=('/safety/status','/safety/selected_source','/console/driver_cmd_vel')+(('/odom',) if require_odom else ())
    if any(now-received.get(k,float('-inf'))>.5 for k in required):return 'parked_evidence_unavailable'
    if data['/safety/status'].get('armed') is not False or data['/safety/selected_source']!='hold':return 'not_parked'
    if nonzero or (require_odom and any(not math.isfinite(v) or abs(v)>.001 for v in data['/odom'])):return 'vehicle_moving'
    if explorer:return 'explorer_running'
    if require_navigation and (len(lifecycle)!=5 or any(v!='active' for v in lifecycle.values())):return 'navigation_services_unavailable'
    return None

def require_parked(require_odom=True, require_navigation=True, timeout=7):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile
    from std_msgs.msg import String
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from lifecycle_msgs.srv import GetState
    rclpy.init()
    node=Node('console_adapter_restore_parked_check')
    data={};received={};counts={};nonzero=[]
    def sample(topic,msg):
        received[topic]=time.monotonic();counts[topic]=counts.get(topic,0)+1
        if isinstance(msg,String):data[topic]=json.loads(msg.data) if msg.data.startswith('{') else msg.data
        elif isinstance(msg,Twist):
            data[topic]=[msg.linear.x,msg.angular.z]
            if any((msg.linear.x,msg.linear.y,msg.linear.z,msg.angular.x,msg.angular.y,msg.angular.z)):nonzero.append(topic)
        else:
            data[topic]=[msg.twist.twist.linear.x,msg.twist.twist.angular.z]
            if any(abs(v)>.001 for v in data[topic]):nonzero.append(topic)
    topics=[('/safety/status',String),('/safety/selected_source',String),('/console/driver_cmd_vel',Twist)]
    if require_odom:topics.append(('/odom',Odometry))
    subscriptions=[node.create_subscription(typ,topic,lambda m,t=topic:sample(t,m),QoSProfile(depth=1)) for topic,typ in topics]
    names=('velocity_smoother','collision_monitor','controller_server','planner_server','bt_navigator')
    clients={name:node.create_client(GetState,'/'+name+'/get_state') for name in names} if require_navigation else {}
    try:
        end=time.monotonic()+timeout;futures={};queried={};life={}
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.03)
            now=time.monotonic()
            for name,client in clients.items():
                future=futures.get(name)
                if future and future.done() and future.result():life[name]=future.result().current_state.label
                if client.service_is_ready() and (future is None or (future.done() and life.get(name)!='active' and now-queried[name]>.5)):
                    futures[name]=client.call_async(GetState.Request());queried[name]=now
            enough=all(counts.get(k,0)>=3 for k,_ in topics)
            if nonzero or (enough and (not require_navigation or (len(life)==5 and all(v=='active' for v in life.values())))):break
        reason=parked_blocker(data,received,time.monotonic(),nonzero,'wheeltec_explore' in node.get_node_names(),life,require_odom,require_navigation)
        if any(counts.get(k,0)<3 for k,_ in topics):
            reason='parked_evidence_unavailable'
        return {'reason':reason,'lifecycle':life,'data':data,'sample_counts':counts}
    finally:
        node.destroy_node();rclpy.shutdown()

def fixed_commands(records, root, needed=None):
    """Reconstruct reviewed commands; never execute command text from the receipt."""
    home=root.parent.parent;q=shlex.quote
    env='source /opt/ros/humble/setup.bash && source '+q(str(home/'wheeltec_ros2/install/setup.bash'))+' && '
    commands={
        'lidar':env+'exec ros2 launch turn_on_wheeltec_robot wheeltec_lidar.launch.py',
        'camera':env+'source '+q(str(root.parent/'stationary-20261030-v2/camera-overlay/install/local_setup.bash'))+' && exec ros2 run usb_cam usb_cam_node_exe --ros-args -r __node:=usb_cam --params-file '+q(str(root/'camera-live.yaml')),
        'model':env+'exec ros2 launch turn_on_wheeltec_robot robot_mode_description.launch.py start_state_publisher:=false robot_model_yaml:='+q(str(root/'model-trial.yaml')),
        'ekf':env+'exec ros2 launch turn_on_wheeltec_robot wheeltec_ekf.launch.py',
        'control_stack':env+'cd '+q(str(root))+' && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 exec ros2 launch '+q(str(root/'robot/launch/robot.launch.py'))+' hardware:='+q(str(root/'robot-live.json'))+' start_slam:=false explore:=false',
        'base_feedback':env+'exec '+q(str(root/'driver-overlay/install/turn_on_wheeltec_robot/lib/turn_on_wheeltec_robot/wheeltec_robot_node'))+' --ros-args -p car_mode:=mini_4wd -p usart_port_name:=/dev/wheeltec_controller -p serial_baud_rate:=115200 -p robot_frame_id:=base_footprint -p odom_frame_id:=odom_combined -r /cmd_vel:=/console/driver_cmd_vel',
        'adapter':adapter_command(root)}
    needed=set(needed if needed is not None else (*COMPONENTS,'adapter'))
    if 'slam' in needed:
        args=shlex.split(records['slam']['command'])
        binary=Path(args[args.index('exec')+1]);config=Path(args[args.index('--params-file')+1])
        if not binary.resolve().is_relative_to(root.resolve()) or not config.resolve().is_relative_to(root.resolve()):raise ValueError('slam_path_outside_runtime')
        if not re.fullmatch(r'slam-motion-gate-\d+/install/lib/wheeltec_slam/motion_gated_slam',binary.relative_to(root).as_posix()):raise ValueError('unknown_slam_binary')
        if not re.fullmatch(r'map-resets/\d+/fresh-slam\.yaml|slam-live\.yaml',config.relative_to(root).as_posix()):raise ValueError('unknown_slam_configuration')
        commands['slam']=env+'OMP_NUM_THREADS=1 exec '+q(str(binary))+' --ros-args -r __node:=slam_toolbox --params-file '+q(str(config))
    for name in needed:
        if records.get(name,{}).get('command')!=commands[name]:raise ValueError('original_command_changed:'+name)
    return commands

def unknown_ros_processes(records, boot):
    owned={int(r['pid']) for r in records.values() if isinstance(r,dict) and identity(r,boot)}
    processes={}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            stat=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
            if stat[0]=='Z':continue
            processes[int(p.name)]=(int(stat[1]),p.joinpath('cmdline').read_bytes())
        except (OSError,ProcessLookupError):continue
    while True:
        descendants={pid for pid,(parent,_) in processes.items() if parent in owned}
        if descendants.issubset(owned):break
        owned.update(descendants)
    tags=(b'/opt/ros/',b'console.target.adapter',b'wheeltec_robot_node',b'motion_gated_slam',b'/watchdog.py',b'/command_selector.py',b'wheeltec_explore')
    return [pid for pid,(_,args) in processes.items() if pid not in owned and pid!=os.getpid() and b'ros2cli.daemon' not in args and any(tag in args for tag in tags)]

def preparation_plan():
    root=runtime_root();evidence=inspect_adapter()
    if evidence.get('reason'):return {**evidence,'status':'blocked'}
    records=json.loads((root/'owned-processes.json').read_text())
    needed=[name for name,state in evidence['processes'].items() if not state['alive']]
    try:
        commands=fixed_commands(records,root,needed)
        required=[Path('/opt/ros/humble/setup.bash'),root.parent.parent/'wheeltec_ros2/install/setup.bash',root/'robot-live.json',root/'console/target/adapter.py']
        for name in needed:
            args=shlex.split(commands[name])
            if name=='camera':required.extend([root.parent/'stationary-20261030-v2/camera-overlay/install/local_setup.bash',root/'camera-live.yaml'])
            if name=='model':required.append(root/'model-trial.yaml')
            if name=='control_stack':required.append(root/'robot/launch/robot.launch.py')
            if name in ('base_feedback','slam'):required.append(Path(args[args.index('exec')+1]))
            if name=='slam':
                import yaml
                config=Path(args[args.index('--params-file')+1]);required.append(config)
                values=yaml.safe_load(config.read_text())['slam_toolbox']['ros__parameters']
                if any('map_file' in key for key in values):raise ValueError('saved_map_loading_not_allowed')
                if values.get('scan_queue_size')!=3 or values.get('stationary_keyframe_distance')!=.03:raise ValueError('slam_runtime_settings_changed')
        if any(not p.is_file() for p in required):raise ValueError('configured_runtime_file_missing')
        if 'base_feedback' in needed and not Path('/dev/wheeltec_controller').exists():raise ValueError('controller_device_missing')
        import sys
        sys.path.insert(0,str(root/'robot'))
        from preflight import validate_runtime
        validate_runtime(json.loads((root/'robot-live.json').read_text()),required_gate=1)
    except (ValueError,KeyError,IndexError,OSError,ImportError) as exc:
        return {**evidence,'status':'blocked','reason':'runtime_preflight_failed','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
    unknown=unknown_ros_processes(records,evidence['boot_id'])
    critical=('control_stack','base_feedback','slam','adapter')
    return {**evidence,'status':'blocked' if unknown else 'planned','reason':'unowned_ros_processes' if unknown else '',
            'unknown_processes':unknown,'needed':needed,'clock_reset_allowed':not unknown and not any(evidence['processes'][n]['alive'] for n in critical)}

def launch_component(name,command,root,out,boot):
    import subprocess
    log=out/(name+'.log')
    with log.open('wb') as output:
        process=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c',command],stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    try:ticks=Path('/proc',str(process.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    except FileNotFoundError:raise RuntimeError('component_exited:'+name)
    receipt=root/'owned-processes.json';records=json.loads(receipt.read_text())
    records[name]={'pid':process.pid,'start_ticks':ticks,'boot_id':boot,'command':command,'log':str(log)}
    tmp=receipt.with_suffix('.prepare.tmp');tmp.write_text(json.dumps(records,indent=2));tmp.replace(receipt)
    time.sleep(.3)
    if process.poll() is not None:raise RuntimeError('component_exited:'+name)
    return process.pid

def prepare_stack():
    import fcntl
    root=runtime_root()
    if not root.is_dir():return {'status':'blocked','reason':'runtime_manifest_missing'}
    with (root/'adapter-recovery.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'blocked','reason':'recovery_in_progress'}
        plan=preparation_plan()
        if plan['status']!='planned':return plan
        if not plan['needed'] and plan['listening']:return {'status':'ready','started':[]}
        if plan['processes']['adapter']['alive'] and not plan['listening']:return {'status':'blocked','reason':'adapter_still_running'}
        driver_live=plan['processes']['base_feedback']['alive']
        if driver_live or plan['processes']['control_stack']['alive']:
            guard=require_parked(require_odom=driver_live,require_navigation=False)
            if guard['reason']:return {'status':'blocked',**guard}
        receipt=root/'owned-processes.json';records=json.loads(receipt.read_text())
        commands=fixed_commands(records,root,plan['needed'])
        out=root/'web-prepare'/str(time.time_ns());out.mkdir(parents=True)
        (out/'receipt-before.json').write_text(json.dumps(records,indent=2))
        started=[]
        def start(name):
            if name not in plan['needed']:return
            if boot_id()!=plan['boot_id']:raise RuntimeError('boot_changed')
            launch_component(name,commands[name],root,out,plan['boot_id']);started.append(name)
        try:
            for name in ('lidar','camera','model','ekf','control_stack'):start(name)
            # Safety/hold and zero final commands MUST precede starting a driver.
            guard=require_parked(require_odom=driver_live,require_navigation=False,timeout=12)
            if guard['reason']:return {'status':'blocked','started':started,**guard}
            (out/'before-driver-parked.json').write_text(json.dumps(guard,indent=2))
            start('base_feedback');start('slam')
            guard=require_parked(timeout=25)
            if guard['reason']:return {'status':'blocked','started':started,**guard}
            fresh=inspect_adapter()
            if fresh['missing_services']:return {'status':'blocked','reason':'component_exited','missing_services':fresh['missing_services'],'started':started}
            (out/'before-adapter-parked.json').write_text(json.dumps(guard,indent=2))
            start('adapter')
            end=time.monotonic()+12
            while time.monotonic()<end:
                if listening():return {'status':'ready','started':started,'directory':str(out)}
                time.sleep(.2)
            return {'status':'failed','reason':'adapter_start_timeout','started':started,'directory':str(out)}
        except RuntimeError as exc:
            return {'status':'failed','reason':str(exc),'started':started,'directory':str(out)}

def restore_adapter():
    import fcntl
    import subprocess
    root=runtime_root()
    # The runtime must already exist. Never create a new control stack.
    if not root.is_dir():return {'status':'blocked','reason':'runtime_manifest_missing'}
    with (root/'adapter-recovery.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'blocked','reason':'recovery_in_progress'}
        evidence=inspect_adapter()
        reason=recovery_blocker(evidence)
        if reason=='adapter_already_listening':return {'status':'ready','restored':False}
        if reason:return {'status':'blocked','reason':reason,'missing_services':evidence.get('missing_services',[])}
        parked=require_parked()
        if parked['reason']:return {'status':'blocked','reason':parked['reason'],'parked':parked}
        receipt=root/'owned-processes.json'
        records=json.loads(receipt.read_text())
        # Recheck identity after the ROS subscription, immediately before spawning.
        fresh=inspect_adapter()
        if recovery_blocker(fresh):return {'status':'blocked','reason':'runtime_changed'}
        out=root/'adapter-recovery'/str(time.time_ns())
        out.mkdir(parents=True)
        (out/'receipt-before.json').write_text(json.dumps(records,indent=2))
        (out/'parked.json').write_text(json.dumps(parked,indent=2))
        log=out/'adapter.log'
        command=adapter_command(root)  # Fixed template; NEVER execute receipt['command'].
        with log.open('wb') as output:
            process=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c',command],stdin=subprocess.DEVNULL,
                                     stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        try:ticks=Path('/proc',str(process.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except FileNotFoundError:return {'status':'failed','reason':'adapter_exited','log':str(log)}
        records['adapter']={'pid':process.pid,'start_ticks':ticks,'boot_id':fresh['boot_id'],'command':command,'log':str(log)}
        tmp=receipt.with_suffix('.adapter-recovery.tmp')
        tmp.write_text(json.dumps(records,indent=2));tmp.replace(receipt)
        end=time.monotonic()+12
        while time.monotonic()<end:
            if process.poll() is not None:return {'status':'failed','reason':'adapter_exited','exit_code':process.returncode,'log':str(log)}
            if listening():return {'status':'ready','restored':True,'pid':process.pid,'log':str(log)}
            time.sleep(.2)
        return {'status':'failed','reason':'adapter_start_timeout','pid':process.pid,'log':str(log)}

def main(action):
    try:
        if action=='inspect':
            result=inspect_adapter()
            result['preparation']=preparation_plan()
        elif action=='restore':result=restore_adapter()
        elif action=='plan':result=preparation_plan()
        elif action=='prepare':result=prepare_stack()
        else:raise ValueError('Unsupported fixed operation')
    except Exception as exc:
        result={'status':'failed','reason':'recovery_error','error_type':type(exc).__name__}
    # A rejected nonfinite odometry sample must still produce a readable error.
    def safe(value):
        if isinstance(value,float) and not math.isfinite(value):return None
        if isinstance(value,dict):return {key:safe(item) for key,item in value.items()}
        if isinstance(value,(list,tuple)):return [safe(item) for item in value]
        return value
    print(json.dumps(safe(result),allow_nan=False),flush=True)
