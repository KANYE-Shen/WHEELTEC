"""Run only vendor candidate nodes and stop them when the owning task exits."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def bind_parent(expected_parent):
    # Linux parent-death signal closes the window where Explorer is SIGKILLed.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'PR_SET_PDEATHSIG failed')
    if os.getppid() != expected_parent:
        raise RuntimeError('Exploration task exited before supervisor started')


def stop_children(children):
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    for child in children:
        try:
            child.wait(timeout=3.)
        except subprocess.TimeoutExpired:
            pass
        # The ros2 CLI may have exited before its executable: clear its own group.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if child.poll() is None:
            child.wait(timeout=3.)


def main():
    stopping = [False]
    def stop(signum, frame):
        stopping[0] = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    bind_parent(int(sys.argv[1]))
    from ament_index_python.packages import get_package_share_directory
    params = Path(get_package_share_directory('wheeltec_robot_rrt'))/'config'/'exploration_params.yaml'
    remaps = [('/clicked_point', '/wheeltec_explore/vendor_boundary'),
              ('/detected_frontiers', '/wheeltec_explore/vendor_detected'),
              ('/filtered_goal_points', '/wheeltec_explore/vendor_points')]
    children = []
    try:
        for name in ('global_rrt', 'local_rrt', 'filter'):
            if stopping[0]:
                return 1
            command = ['ros2', 'run', 'wheeltec_robot_rrt', name, '--ros-args',
                       '--params-file', str(params), '-p', 'use_sim_time:=false']
            for source, target in remaps:
                command += ['-r', source+':='+target]
            children.append(subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                              start_new_session=True))
        while not stopping[0]:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('厂家探索节点异常退出')
            time.sleep(.1)
        return 0
    finally:
        stop_children(children)


if __name__ == '__main__':
    raise SystemExit(main())
