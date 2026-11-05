"""Own only the exploration child; stop preempts an unfinished start."""
import signal
import threading
import time


def wait_for_stable_readiness(current, check, healthy_for=.5, timeout=5.,
                              clock=time.monotonic, sleep=time.sleep):
    """Wait while disarmed; intermittent health is never permission to start."""
    deadline = clock()+timeout
    healthy_since = None
    last_problem = '尚未收到连续有效的传感器与TF'
    while current():
        now = clock()
        if now >= deadline:
            raise ValueError('启动健康检查未稳定：'+last_problem)
        problem = check()
        if problem:
            last_problem = problem
            healthy_since = None
        elif healthy_since is None:
            healthy_since = now
        elif now-healthy_since >= healthy_for:
            if not current():
                break
            return
        sleep(.05)
    raise ValueError('启动已取消')


class TaskController:
    def __init__(self, preflight, activate, spawn, halt):
        self.preflight, self.activate, self.spawn, self.halt = preflight, activate, spawn, halt
        self.lock = threading.RLock()
        self.generation = 0
        self.mode = 'remote'
        self.error = ''
        self.process = None
        self.stop_sent = False

    def current(self, ticket):
        with self.lock:
            return self.generation == ticket and self.mode in ('starting', 'autonomous')

    def start(self):
        with self.lock:
            if self.mode in ('starting', 'autonomous'):
                return {'mode': self.mode, 'error': self.error}
            if self.process is not None and self.process.poll() is None:
                raise ValueError('上一次探索正在停止，请稍后再启动')
            self.generation += 1
            ticket = self.generation
            self.mode, self.error = 'starting', ''
        try:
            self.preflight()
        except Exception as exc:
            with self.lock:
                if self.current(ticket):
                    self.mode, self.error = 'remote', str(exc)
            raise
        with self.lock:
            if not self.current(ticket):
                return {'mode': self.mode, 'error': self.error}
        threading.Thread(target=self._start, args=(ticket,), daemon=True).start()
        return self.snapshot()

    def _start(self, ticket):
        try:
            self.activate(lambda: self.current(ticket))
            with self.lock:
                if not self.current(ticket):
                    return
                self.process = self.spawn()
                self.stop_sent = False
                self.mode = 'autonomous'
        except Exception as exc:
            with self.lock:
                if not self.current(ticket):
                    return
                self.generation += 1
                self.mode, self.error = 'remote', str(exc)
            self.halt()

    def remote(self, reason=""):
        with self.lock:
            self.generation += 1
            self.mode, self.error = 'remote', reason
            process = self.process
            signal_child = process is not None and process.poll() is None and not self.stop_sent
            self.stop_sent = self.stop_sent or signal_child
        # Halt the final command chain before waiting for any algorithm cancellation.
        try:
            self.halt()
        finally:
            if signal_child:
                try:
                    process.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
        return self.snapshot()

    def snapshot(self):
        stopped = False
        with self.lock:
            if self.mode == 'autonomous' and self.process is not None:
                code = self.process.poll()
                if code is not None:
                    self.generation += 1
                    self.mode = 'remote'
                    self.error = '' if code == 0 else '探索进程已退出，代码 '+str(code)
                    stopped = True
            result = {'mode': self.mode, 'error': self.error}
        if stopped:
            self.halt()
        return result
