"""Optional simulation desktop. All listeners are loopback and VNC is view-only."""
import argparse
import os
import signal
import subprocess
import time
import shutil


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--display', default=':88')
    p.add_argument('--private-display', action='store_true')
    p.add_argument('--web-port', type=int, default=6080)
    p.add_argument('--vnc-port', type=int, default=5908)
    a = p.parse_args()
    for tool in ('x11vnc', 'websockify'):
        if not shutil.which(tool):
            p.error('Install optional dependency: '+tool)
    if a.private_display and not shutil.which('Xvfb'):
        p.error('Install xvfb')
    children = []

    def run(command):
        child = subprocess.Popen(command, start_new_session=True)
        children.append(child)
        return child
    try:
        if a.private_display:
            display = run(['Xvfb', a.display, '-screen', '0',
                          '1440x900x24', '-nolisten', 'tcp'])
            time.sleep(1)
            if display.poll() is not None:
                raise RuntimeError('Display is already in use or Xvfb failed')
        run(['x11vnc', '-display', a.display, '-localhost', '-rfbport',
            str(a.vnc_port), '-nopw', '-forever', '-shared', '-viewonly'])
        run(['websockify', '--web=/usr/share/novnc', '127.0.0.1:' +
            str(a.web_port), '127.0.0.1:'+str(a.vnc_port)])
        print('Start Gazebo/RViz with DISPLAY='+a.display +
              '; desktop is read-only over the existing SSH tunnel.', flush=True)
        while True:
            if any(c.poll() is not None for c in children):
                raise RuntimeError('An owned desktop process exited')
            time.sleep(.25)
    except KeyboardInterrupt:
        pass
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)


if __name__ == '__main__':
    main()
