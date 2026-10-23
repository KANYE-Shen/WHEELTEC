"""Start the project simulation; resolve the most recently saved map for AMCL."""
import fcntl
import json
import os
from pathlib import Path
import sys
from build_gui_sync import ensure_gui_sync

arguments = list(sys.argv[1:])
options = dict(arg.split(':=', 1) for arg in arguments if ':=' in arg)
if options.get('mode') == 'localization' and not options.get('map'):
    record = Path.home()/'wheeltec_sim_ws/data/maps/latest.json'
    if not record.is_file():
        raise SystemExit('No saved map yet. Run mapping and save the map first.')
    map_path = Path(json.loads(record.read_text())['map_yaml'])
    if not map_path.is_file():
        raise SystemExit('The most recently saved map is missing: '+str(map_path))
    arguments.append('map:='+str(map_path))
# A second room in the same ROS domain would mix sensors and velocity commands.
lock = os.open('/tmp/wheeltec-room-'+options.get('ros_domain_id','77')+'.lock', os.O_CREAT|os.O_RDWR, 0o600)
try:
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('A room simulation is already running in this ROS domain. Close its launch terminal first.')
os.set_inheritable(lock, True)
if options.get('gui', 'true').lower() not in ('false', '0'):
    ensure_gui_sync()
launch_file = Path(__file__).resolve().parent/'launch/room.launch.py'
setup = Path.home()/'wheeltec_sim_ws/install/setup.bash'
command = 'source /opt/ros/humble/setup.bash; if [ -f "$1" ]; then source "$1"; fi; shift; exec ros2 launch "$@"'
os.execv('/bin/bash',['bash','-lc',command,'wheeltec-room',str(setup),str(launch_file),*arguments])
