"""Open the installed GUI tools, capture their windows, then stop only these processes."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--room', action='store_true', help='Open the project room instead of stock examples')
args = parser.parse_args()
project_dir = Path(__file__).resolve().parents[1]

log_dir = Path.home() / 'simulation-checks' / ('gui-' + time.strftime('%Y%m%d-%H%M%S'))
log_dir.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID='77',
           IGN_PARTITION=f'wheeltec-gui-check-{os.getpid()}', QT_QPA_PLATFORM='xcb')
processes = []
handles = []
results = {'log_dir': str(log_dir), 'gazebo_gui_engine': 'ogre', 'scene': 'room_25m2' if args.room else 'stock_examples'}

try:
    commands = ([('room', ['python3', str(project_dir / 'simulation/run_room.py'),
                            'partition:=' + env['IGN_PARTITION']])] if args.room else
                [('gazebo', ['ign', 'gazebo', '--render-engine-gui', 'ogre', '-r', 'shapes.sdf']),
                 ('rviz', ['rviz2'])])
    for name, command in commands:
        handle = (log_dir / (name + '.log')).open('w')
        handles.append(handle)
        processes.append(subprocess.Popen(command, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                          start_new_session=True))
    deadline = time.monotonic() + 45
    windows = {}
    while time.monotonic() < deadline:
        tree = subprocess.run(['xwininfo', '-root', '-tree'], env=env, text=True,
                              capture_output=True, timeout=5).stdout
        (log_dir / 'windows.log').write_text(tree)
        windows = {}
        for line in tree.splitlines():
            match = re.search(r'(0x[0-9a-f]+) "([^"]+)".*? (\d+)x(\d+)', line, re.I)
            if not match or int(match[3]) < 400 or int(match[4]) < 300:
                continue
            for name in ['gazebo', 'rviz']:
                if name in match[2].lower() and name not in windows:
                    windows[name] = {'id': match[1], 'title': match[2]}
        if len(windows) == 2:
            break
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('A GUI process exited before both windows appeared.')
        time.sleep(0.5)
    if len(windows) != 2:
        raise RuntimeError(f'Expected Gazebo and RViz windows, found {windows}.')
    time.sleep(4)
    for name, window in windows.items():
        info = subprocess.run(['xwininfo', '-id', window['id']], env=env,
                              capture_output=True, text=True, timeout=5)
        (log_dir / (name + '-window.log')).write_text(info.stdout + info.stderr)
        if 'IsViewable' not in info.stdout:
            raise RuntimeError(f'{name} window is not viewable.')
    helper = subprocess.check_output(['wslpath', '-w', str(project_dir / 'setup' / 'Capture-SimulationWindows.ps1')], text=True).strip()
    capture_dir = project_dir / 'setup' / 'verification'
    if args.room:
        capture_dir = capture_dir / 'room'
    capture_dir.mkdir(parents=True, exist_ok=True)
    output = subprocess.check_output(['wslpath', '-w', str(capture_dir)], text=True).strip()
    capture = subprocess.run([
        '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-File',
        helper,
        '-OutputDirectory', output],
        capture_output=True, timeout=30)
    (log_dir / 'windows-capture.log').write_bytes(capture.stdout + capture.stderr)
    if capture.returncode:
        raise RuntimeError('Windows capture helper failed; see windows-capture.log.')
    results['windows_capture'] = capture.stdout.decode('utf-8', errors='replace')
    results['windows'] = windows
    results['capture_directory'] = str(capture_dir)
    results['success'] = True
except Exception as error:
    results['success'] = False
    results['error'] = str(error)
finally:
    for process in processes:
        try:
            if args.room:
                process.send_signal(signal.SIGINT)
            else:
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
