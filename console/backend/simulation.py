"""Transport from the Windows console to its local WSL simulation."""
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
from threading import Lock, Thread
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class SimulationWorker:
    def __init__(self, command):
        self.command = command
        self.process = None
        self.lock = Lock()

    def _open(self):
        self.process = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.replies = Queue()
        Thread(target=self._read, args=(self.process.stdout, self.replies),
               name='simulation-replies', daemon=True).start()

    @staticmethod
    def _read(stream, replies):
        try:
            for line in stream:
                replies.put(line)
        finally:
            replies.put(None)

    def request(self, op, args):
        with self.lock:
            if self.process is None and op in ('state', 'stop'):
                return dict(phase='stopped', message='', run_id=None, mode=None, map=None,
                            pose=None, laser_pose=None, scan=None, goal=None, navigation_ready=False)
            try:
                if self.process is None:
                    self._open()
                process = self.process
                # One in-flight request, protected by the lock.
                request = {'id': 1, 'op': op, 'args': args}
                process.stdin.write((json.dumps(request, allow_nan=False) + '\n').encode('utf-8'))
                process.stdin.flush()
                line = self.replies.get(timeout=35)
                reply = json.loads(line) if line is not None else {}
                if reply.get('id') != request['id'] or 'ok' not in reply:
                    raise RuntimeError('Unexpected simulation worker response')
            except (Empty, OSError, ValueError, RuntimeError) as exc:
                self._close()
                raise HTTPException(503, detail={
                    'code': 'simulation_unavailable',
                    'message': '本机仿真进程无响应。请检查 WSL 中的 ROS 2 安装后重新启动仿真。',
                }) from exc
            if not reply['ok']:
                raise HTTPException(409, detail=reply['error'])
            if op == 'stop':
                self._close()
            return reply['result']

    def _close(self):
        process, self.process = self.process, None
        if process is None:
            return
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()

    def close(self):
        with self.lock:
            self._close()


ROOT = Path(__file__).resolve().parents[2]
worker = SimulationWorker([
    'wsl.exe', '--distribution', os.environ.get('WHEELTEC_SIM_DISTRO', 'WHEELTEC-Ubuntu-22.04'),
    '--cd', str(ROOT), '--exec', 'bash', 'simulation/web_session.sh',
])
router = APIRouter(prefix='/api/v1/simulation')


class StartRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['mapping', 'localization']
    map_id: str | None = Field(default=None, min_length=1, max_length=100)
    scenario: Literal['baseline', 'l_shape', 'clutter', 'bent_passage', 'recess',
                      'irregular_arc', 'irregular_frame'] | None = None
    spawn: int | None = Field(default=None, ge=0, le=2, strict=True)
    seed: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    lidar_noise_stddev: float | None = Field(default=None, ge=0, le=0.03)


class GoalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x: float
    y: float
    yaw: float
    frame: Literal['map']
    run_id: str = Field(min_length=1, max_length=100)
    map_revision: int = Field(ge=0, strict=True)


@router.get('/state')
def state():
    return worker.request('state', {})


@router.get('/maps')
def maps():
    return {'maps': worker.request('maps', {})}


@router.post('/start')
def start(request: StartRequest):
    return worker.request('start', request.model_dump(exclude_none=True))


@router.post('/goal')
def goal(request: GoalRequest):
    return worker.request('goal', request.model_dump())


@router.post('/cancel')
def cancel():
    return worker.request('cancel', {})


@router.post('/save')
def save():
    return worker.request('save', {})


@router.post('/stop')
def stop():
    return worker.request('stop', {})
