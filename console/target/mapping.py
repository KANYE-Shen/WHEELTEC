"""Restart only an explicitly recorded, owned mapper after its graph is archived."""
import copy
import json
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path


def fresh_parameters(parameters):
    result = copy.deepcopy(parameters)
    p = result['slam_toolbox']['ros__parameters']
    for key in ('map_file_name', 'map_start_pose', 'map_start_at_dock'):
        p.pop(key, None)
    return result


def mapping_command(command, parameters):
    parts = shlex.split(command)
    if parts.count('--params-file') != 1 or not any(
            Path(x).name in ('async_slam_toolbox_node', 'motion_gated_slam') for x in parts):
        raise ValueError('未配置独立、可识别的建图进程；未重启任何进程')
    i = parts.index('--params-file') + 1
    if i >= len(parts):
        raise ValueError('建图参数文件缺失')
    old = parts[i]
    if command.count(old) != 1:
        raise ValueError('建图参数路径不唯一')
    return command.replace(old, shlex.quote(parameters.as_posix()), 1)


def owned_mapper(receipt):
    records = json.loads(receipt.read_text())
    record = records['slam']
    pid = record['pid']
    proc = Path('/proc') / str(pid)
    stat = proc.joinpath('stat').read_text().split()
    cmdline = proc.joinpath('cmdline').read_bytes().replace(b'\0', b' ').decode()
    if stat[21] != record['start_ticks'] or os.getpgid(pid) != pid or not any(
            name in cmdline for name in ('slam_toolbox', 'motion_gated_slam')):
        raise ValueError('建图进程身份已变化；拒绝停止')
    mapping_command(record['command'], Path('/identity-check/slam.yaml'))
    return record


def restart_mapper(receipt, archive, guard, parameters_config):
    """The caller must first archive via SLAM's serialize service, with wheels held."""
    import yaml
    record = owned_mapper(receipt)
    parts = shlex.split(record['command'])
    old_parameters = Path(parts[parts.index('--params-file') + 1])
    parameters = archive / 'fresh-slam.yaml'
    parameters.write_text(yaml.safe_dump(fresh_parameters(parameters_config)))
    (archive / 'previous-command.json').write_text(json.dumps(record))
    (archive / 'previous-slam.yaml').write_bytes(old_parameters.read_bytes())
    command = mapping_command(record['command'], parameters)
    guard()
    if owned_mapper(receipt) != record:
        raise ValueError('建图进程在重置准备期间变化')
    os.killpg(record['pid'], signal.SIGINT)
    deadline = time.monotonic() + 12.
    def group_running():
        for member in Path('/proc').iterdir():
            if not member.name.isdigit():
                continue
            try:
                stat = member.joinpath('stat').read_text().split()
                if stat[2] != 'Z' and os.getpgid(int(member.name)) == record['pid']:
                    return True
            except (ProcessLookupError, FileNotFoundError):
                continue
        return False
    while group_running():
        if time.monotonic() >= deadline:
            raise ValueError('旧建图进程组未退出，未启动副本')
        time.sleep(.05)
    # A mapper started by this adapter is our child; /proc persists until reaped.
    try:
        os.waitpid(record['pid'], os.WNOHANG)
    except ChildProcessError:
        pass
    # Holding stop is mandatory even if the browser disconnected during the reset.
    guard()
    with (archive / 'fresh-slam.log').open('wb') as log:
        child = subprocess.Popen(['bash', '--noprofile', '--norc', '-c', command],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
    records = json.loads(receipt.read_text())
    records['slam'] = {'pid': child.pid, 'command': command,
        'start_ticks': Path('/proc', str(child.pid), 'stat').read_text().split()[21]}
    temp = receipt.with_suffix('.reset.tmp')
    temp.write_text(json.dumps(records, indent=2))
    temp.replace(receipt)
    time.sleep(.5)
    if child.poll() is not None:
        raise ValueError('新建图进程启动失败，保持停车；见 '+str(archive/'fresh-slam.log'))
    return records['slam']


class MapReset:
    """A stopped-only asynchronous reset; requests never arm or resume a task."""
    def __init__(self, halt, reset):
        import threading
        self.lock = threading.Lock()
        self.halt, self.reset = halt, reset
        self.busy, self.error, self.sequence = False, '', 0

    def start(self):
        import threading
        with self.lock:
            if self.busy:
                raise ValueError('地图正在重置')
            self.busy, self.error = True, ''
        try:
            self.halt()
        except Exception:
            with self.lock:
                self.busy = False
            raise
        threading.Thread(target=self._run, daemon=True).start()
        return self.snapshot()

    def _run(self):
        try:
            self.reset()
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
        finally:
            with self.lock:
                self.busy = False
                self.sequence += 1

    def snapshot(self):
        with self.lock:
            return {'busy': self.busy, 'error': self.error, 'sequence': self.sequence}
