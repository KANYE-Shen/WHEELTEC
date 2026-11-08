"""Map bounds and task-owned supervisor for manufacturer exploration nodes."""
import math
import os
import signal
import subprocess
import sys


def map_sampling_bounds(info):
    """Return interior bounds supported by the vendor's axis-aligned map indexing."""
    q = info.origin.orientation
    if (not all(math.isfinite(v) for v in (q.x, q.y, q.z, q.w)) or
            abs(q.x) > 1e-6 or abs(q.y) > 1e-6 or abs(q.z) > 1e-6 or
            abs(abs(q.w)-1.) > 1e-6):
        raise ValueError('厂家探索不支持旋转地图坐标系')
    r = info.resolution
    x, y = info.origin.position.x, info.origin.position.y
    if not all(math.isfinite(v) for v in (r, x, y)) or r <= 0 or info.width < 2 or info.height < 2:
        raise ValueError('地图范围无效，未启动厂家探索')
    return (x+r*.5, y+r*.5, x+(info.width-.5)*r, y+(info.height-.5)*r)


def bounds_changed(old, new, resolution):
    """Ignore floating-point jitter; real expansion or shrink changes safe sampling."""
    return any(abs(a-b) > resolution*.1 for a, b in zip(old, new))


class VendorProcesses:
    """Own one supervisor; it reaps its three nodes even if this process dies."""
    def __init__(self):
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'wheeltec_explore.vendor_supervisor', str(os.getpid())],
            stdin=subprocess.DEVNULL, start_new_session=True)

    def check(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('厂家探索节点已退出，任务保持停车')

    def stop(self):
        child, self.process = self.process, None
        if child is None:
            return
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
        try:
            child.wait(timeout=12.)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=3.)
