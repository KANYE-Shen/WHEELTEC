"""Start simulation; preserve saved-map layout and normal exploration recordings."""
import fcntl
import json
import os
from pathlib import Path
import sys
from build_gui_sync import ensure_gui_sync
from room_session import prepare_exploration, register_session, resolve_session
from scenarios import load_scenario, generate_world
from realism import load_profile,prepare_assets,value


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    data_root = Path.home()/'wheeltec_sim_ws/data'
    try:
        session = resolve_session(arguments,data_root)
    except (ValueError,KeyError,OSError) as exc:
        raise SystemExit(str(exc))
    options = session['options']
    realism_mode=options.get('realism','on')
    if realism_mode not in ('on','off'): raise SystemExit('realism must be on or off')
    # Keep the lock across exec; a second room would mix sensors and commands.
    lock = os.open('/tmp/wheeltec-room-'+options.get('ros_domain_id','77')+'.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A room simulation is already running in this ROS domain. Close its launch terminal first.')
    os.set_inheritable(lock,True)
    if session['scenario']:
        scene = load_scenario(session['scenario'])
        output = data_root/'worlds'/('room-'+str(os.getpid())+'.sdf')
        generate_world(scene,session['spawn'],output)
        arguments = [arg for arg in arguments if not arg.startswith(('scenario:=','spawn:=','world:='))]
        arguments.append('world:='+str(output))
        print('仿真场景 '+session['scenario']+' / 起点 '+str(session['spawn']),flush=True)
    if realism_mode=='on':
        selected=Path(next((arg.split(':=',1)[1] for arg in arguments if arg.startswith('world:=')),
                           str(Path(__file__).resolve().parent/'worlds/room_25m2.sdf')))
        profile_path=Path(options.get('realism_profile',str(Path(__file__).resolve().parent/'config/realism.yaml')))
        profile=load_profile(profile_path)
        assets=prepare_assets(selected,Path(options.get('realism_assets',str(data_root/'runtime'/str(os.getpid())))),
                              profile,int(options.get('seed','0')),float(options.get('noise_scale','1')))
        if value(profile,'compute.apply_limit'):
            affinity=sorted(os.sched_getaffinity(0))[:int(value(profile,'compute.cores'))]
            os.sched_setaffinity(0,affinity)
            assets['cpu_affinity']=affinity
            (Path(assets['model']).parent/'manifest.json').write_text(json.dumps(assets,indent=2)+'\n')
        arguments=[arg for arg in arguments if not arg.startswith(('world:=','bridge_config:=','slam_config:=','nav2_config:=','explorer_radius:='))]
        arguments+=['world:='+assets['world'],'bridge_config:='+assets['bridge'],
                    'slam_config:='+assets['slam'],'nav2_config:='+assets['nav2'],
                    'explorer_radius:='+str(assets['robot_radius'])]
    arguments=[arg for arg in arguments if not arg.startswith('realism_assets:=')]
    if not any(arg.startswith('realism:=') for arg in arguments): arguments.append('realism:='+realism_mode)
    if session['map'] is not None:
        arguments = [arg for arg in arguments if not arg.startswith('map:=')]
        arguments.append('map:='+str(session['map']))
    if session['explore']:
        prepare_exploration(session,data_root)
        arguments = [arg for arg in arguments if not arg.startswith(('map_output:=','capture_run:=','capture_metadata:='))]
        arguments += ['map_output:='+str(session['map_output']),
                      'capture_run:='+str(session['run_dir']),
                      'capture_metadata:='+json.dumps(session['metadata'],ensure_ascii=False,separators=(',',':'))]
        print('地图保存前缀 '+str(session['map_output'])+'\n过程目录 '+str(session['run_dir']),flush=True)
    if options.get('gui','true').lower() not in ('false','0'):
        ensure_gui_sync()
    register_session(session,data_root,options.get('ros_domain_id','77'),
                     Path('/tmp')/('wheeltec-room-'+options.get('ros_domain_id','77')+'.lock'))
    launch_file = Path(__file__).resolve().parent/'launch/room.launch.py'
    setup = Path.home()/'wheeltec_sim_ws/install/setup.bash'
    command = 'source /opt/ros/humble/setup.bash; if [ -f "$1" ]; then source "$1"; fi; shift; exec ros2 launch "$@"'
    os.execv('/bin/bash',['bash','-lc',command,'wheeltec-room',str(setup),str(launch_file),*arguments])


if __name__ == '__main__':
    main()
