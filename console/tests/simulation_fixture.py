"""Owned WSL fixture; never run on the robot. Existing evidence is immutable."""
import argparse
import ctypes
import fcntl
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DATA = None
ENV = dict(os.environ, ROS_DOMAIN_ID='87', ROS_LOCALHOST_ONLY='1',
           IGN_PARTITION='wheeltec-console-test', DISPLAY=':88', QT_QPA_PLATFORM='xcb')
ENV.pop('WAYLAND_DISPLAY', None)


def launch(name, command):
    records = json.loads((DATA/'processes.json').read_text()
                         ) if (DATA/'processes.json').exists() else []
    log = (DATA/(name+'.log')).open('xb')
    p = subprocess.Popen(command, env=ENV, cwd=ROOT, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    records.append({'name': name, 'pid': p.pid, 'start': Path(
        '/proc/'+str(p.pid)+'/stat').read_text().split()[21]})
    (DATA/'processes.json').write_text(json.dumps(records, indent=2))
    return p


def start(mode):
    if DATA.exists():
        raise SystemExit(
            'New run-id required; never overwrite previous fixture evidence')
    # Wait for owned launch children to release their inherited lock; never unlink it.
    deadline = time.monotonic()+30
    with open('/tmp/wheeltec-room-87.lock', 'a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise SystemExit('Domain 87 still has an active room')
                time.sleep(.25)
    DATA.mkdir(parents=True, mode=0o700)
    launch('display', ['Xvfb', ':88', '-screen',
           '0', '1440x900x24', '-nolisten', 'tcp'])
    time.sleep(1)
    launch('vnc', ['x11vnc', '-display', ':88', '-localhost',
           '-rfbport', '5908', '-nopw', '-forever', '-shared', '-viewonly'])
    launch('novnc', ['websockify', '--web=/usr/share/novnc',
           '127.0.0.1:6080', '127.0.0.1:5908'])
    command = 'source /opt/ros/humble/setup.bash; source /home/wheeltec/wheeltec_sim_ws/install/setup.bash; exec python3 simulation/run_room.py gui:=true rviz:=true navigation:=false realism:=' + \
        mode+' ros_domain_id:=87 partition:=wheeltec-console-test seed:=0'
    launch('room', ['bash', '-lc', command])
    command = 'source /opt/ros/humble/setup.bash; source /home/wheeltec/wheeltec_sim_ws/install/setup.bash; exec python3 -m console.target.adapter --kind simulation --enable-simulation-control --token-file ' + \
        str(DATA/'adapter.token')+' --ros-args -p use_sim_time:=true'
    launch('adapter', ['bash', '-lc', command])
    (DATA/'configuration.json').write_text(json.dumps(
        {'realism': mode, 'domain': 87, 'seed': 0, 'partition': 'wheeltec-console-test'}))
    print(DATA)


def camera():
    sdf = (ROOT/'console/tests/observer-camera.sdf').read_text()
    result = subprocess.run(['ign', 'service', '-s', '/world/wheeltec_room/create', '--reqtype', 'ignition.msgs.EntityFactory', '--reptype',
                            'ignition.msgs.Boolean', '--timeout', '5000', '--req', 'sdf: '+json.dumps(sdf)], env=ENV, capture_output=True, text=True, check=True)
    (DATA/'camera-spawn.txt').write_text(result.stdout)
    if 'true' not in result.stdout:
        raise SystemExit('Observer camera spawn failed')
    launch('camera-bridge', ['bash', '-lc', 'source /opt/ros/humble/setup.bash; exec ros2 run ros_gz_bridge parameter_bridge /console_test/camera@sensor_msgs/msg/Image[ignition.msgs.Image --ros-args -r /console_test/camera:=/image_raw'])


def evaluate():
    started = time.monotonic()
    (DATA/'evaluation-start.json').write_text(
        json.dumps({'monotonic': started, 'wall': time.time()}))
    launch('command-evaluation', ['bash', '-lc', 'source /opt/ros/humble/setup.bash; exec python3 console/tests/evaluation_recorder.py --output '+str(
        DATA/'commands.jsonl')+' --ros-args -p use_sim_time:=true'])
    launch('native-evaluation', ['python3', 'simulation/truth_capture_worker.py', '--partition', 'wheeltec-console-test', '--started', str(
        started), '--samples', str(DATA/'native-truth.jsonl'), '--diagnostics', str(DATA/'native-truth-diagnostics.json'), '--sample-period', '.02'])


def tile():
    output = subprocess.check_output(
        ['xwininfo', '-root', '-tree'], env=ENV, text=True)
    lib = ctypes.CDLL('libX11.so.6')
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XMoveResizeWindow.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    lib.XFlush.argtypes = [ctypes.c_void_p]
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = lib.XOpenDisplay(b':88')
    if not display:
        raise SystemExit('No fixture display')
    try:
        for line in output.splitlines():
            match = re.match(r'\s+(0x[0-9a-f]+) "(.*)"', line)
            if match and (match[2] == 'Gazebo' or ' - RViz' in match[2]):
                lib.XMoveResizeWindow(display, int(
                    match[1], 16), 0 if match[2] == 'Gazebo' else 720, 0, 720, 900)
        lib.XFlush(display)
    finally:
        lib.XCloseDisplay(display)


def signal_owned(name, sig):
    records = json.loads((DATA/'processes.json').read_text())
    for item in reversed(records):
        if not item['name'].startswith(name):
            continue
        try:
            stat = Path('/proc/'+str(item['pid'])+'/stat').read_text().split()
            if stat[21] == item['start'] and int(stat[4]) == item['pid']:
                os.killpg(item['pid'], sig)
                return
        except FileNotFoundError:
            pass
    raise RuntimeError('No matching owned live process')


def pause_room(): signal_owned('room', signal.SIGSTOP)
def resume_room(): signal_owned('room', signal.SIGCONT)
def pause_adapter(): signal_owned('adapter', signal.SIGSTOP)
def resume_adapter(): signal_owned('adapter', signal.SIGCONT)


def stop():
    if not (DATA/'processes.json').exists():
        return
    records = json.loads((DATA/'processes.json').read_text())
    for sig in (signal.SIGINT, signal.SIGTERM):
        for item in reversed(records):
            try:
                stat = Path(
                    '/proc/'+str(item['pid'])+'/stat').read_text().split()
                if stat[21] == item['start'] and int(stat[4]) == item['pid']:
                    os.killpg(item['pid'], sig)
            except (ProcessLookupError, FileNotFoundError):
                pass
        time.sleep(2)
    print('Owned fixture process groups stopped; evidence retained')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=[
                   'start', 'stop', 'camera', 'evaluate', 'tile', 'pause_room', 'resume_room', 'pause_adapter', 'resume_adapter'])
    p.add_argument('--realism', choices=['on', 'off'], default='on')
    p.add_argument('--run-id', default='20261027-console')
    a = p.parse_args()
    if os.environ.get('WSL_DISTRO_NAME') != 'WHEELTEC-Ubuntu-22.04':
        p.error('Fixture is restricted to the named WSL simulation distro')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', a.run_id):
        p.error('Simple run-id required')
    DATA = Path.home()/'wheeltec_sim_ws/data/runs'/a.run_id
    if a.action == 'start':
        start(a.realism)
    else:
        globals()[a.action]()
