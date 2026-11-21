"""Loopback-only WSL Gazebo worker. The Windows gateway owns its stdio."""
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

from room_session import active_session, stop_owned

SIMULATION = Path(__file__).resolve().parent
SCENARIOS = frozenset(path.stem for path in (SIMULATION / 'scenarios').glob('*.json'))
DOMAIN = '218'
DATA = Path.home() / 'wheeltec_sim_ws/data'
WEB_DATA = DATA / 'web'
MOVING = frozenset({'pending', 'active', 'canceling'})


class RequestError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def number(value):
    return (type(value) is int and -sys.float_info.max <= value <= sys.float_info.max
            or type(value) is float and math.isfinite(value))


def start_options(arguments):
    allowed = {'mode', 'scenario', 'spawn', 'seed', 'lidar_noise_stddev', 'map_id'}
    if arguments.keys() - allowed:
        raise RequestError('invalid_settings', 'Unsupported simulator setting')
    mode = arguments.get('mode', 'mapping')
    if mode not in ('mapping', 'localization'):
        raise RequestError('invalid_settings', 'Choose mapping or localization')
    map_id = arguments.get('map_id')
    scenario = arguments.get('scenario', 'baseline')
    spawn = arguments.get('spawn', 0)
    if mode == 'localization':
        if not isinstance(map_id, str) or not map_id or {'scenario', 'spawn'} & arguments.keys():
            raise RequestError('invalid_settings', 'Choose one saved map to restore its scenario and spawn')
        scenario = spawn = None
    elif map_id is not None or not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise RequestError('invalid_settings', 'Choose a packaged mapping scenario')
    elif type(spawn) is not int or not 0 <= spawn < 3:
        raise RequestError('invalid_settings', 'Spawn must be 0, 1, or 2')
    seed = arguments.get('seed', 0)
    sigma = arguments.get('lidar_noise_stddev', .01)
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise RequestError('invalid_settings', 'Seed must be an integer between 0 and 2147483647')
    if not number(sigma) or not 0 <= sigma <= .03:
        raise RequestError('invalid_settings', 'LiDAR standard deviation must be between 0 and 0.03 m')
    return {'mode': mode, 'scenario': scenario, 'spawn': spawn, 'seed': seed,
            'lidar_noise_stddev': sigma, 'map_id': map_id}


def goal_options(arguments, state, geometry_revision):
    grid = state['map']
    revision = arguments.get('map_revision')
    if not grid or arguments.get('run_id') != state['run_id'] or arguments.get('frame') != grid['frame']:
        raise RequestError('stale_map', 'Select the goal on the active simulation map')
    if type(revision) is not int or not geometry_revision <= revision <= grid['revision']:
        raise RequestError('stale_map', 'Map geometry changed; select the goal again')
    if not state['navigation_ready']:
        raise RequestError('navigation_unavailable', 'Wait for fresh map, pose, scan and active Nav2')
    x, y, yaw = (arguments.get(key) for key in ('x', 'y', 'yaw'))
    if not all(map(number, (x, y, yaw))) or not -math.pi <= yaw <= math.pi:
        raise RequestError('invalid_goal', 'Enter finite map coordinates and yaw in [-π, π]')
    check_goal_cell(grid, x, y)
    return float(x), float(y), float(yaw)


def check_goal_cell(grid, x, y):
    ox, oy, heading = grid['origin']
    dx, dy = x - ox, y - oy
    c, s = math.cos(heading), math.sin(heading)
    gx, gy = (c * dx + s * dy) / grid['resolution'], (-s * dx + c * dy) / grid['resolution']
    if not (0 <= gx < grid['width'] and 0 <= gy < grid['height']):
        raise RequestError('invalid_goal', 'Goal lies outside the current map')
    if grid['data'][math.floor(gy) * grid['width'] + math.floor(gx)] != 0:
        raise RequestError('invalid_goal', 'Choose a known free cell')


def available_maps():
    for prefix, directory in (('sim', WEB_DATA/'maps'), ('legacy', DATA/'maps')):
        for folder in sorted(directory.glob('*'), reverse=True):
            path = folder / 'room.yaml'
            if (folder.is_symlink() or path.is_symlink() or not path.is_file()
                    or not path.with_suffix('.pgm').is_file()
                    or (prefix == 'sim' and not path.with_suffix('.metadata.json').is_file())):
                continue
            yield {'id': prefix + ':' + folder.name, 'name': folder.name}, path


def default_state(phase='stopped', message='Simulation stopped', run_id=None, mode=None):
    return {'phase': phase, 'message': message, 'run_id': run_id, 'mode': mode,
            'map': None, 'pose': None, 'laser_pose': None, 'scan': None, 'odom': None,
            'navigation_ready': False, 'goal': None}


class Session:
    def __init__(self):
        self.process = None
        self.ros = None
        self.options = None
        self.run = None
        self.runtime_state = default_state()
        self.deadline = 0.

    def state(self):
        result = dict(self.runtime_state)
        if self.ros is not None:
            result.update(self.ros.snapshot())
            if result['navigation_ready']:
                result.update(phase='running', message='Gazebo and Nav2 ready')
            else:
                result.update(message='Waiting for ' + ', '.join(self.ros.waiting_for))
        return result

    def start(self, arguments):
        if self.process is not None:
            raise RequestError('already_running', 'Stop the current simulation to apply new settings')
        options = start_options(arguments)
        saved = dict((row['id'], path) for row, path in available_maps())
        if options['map_id'] is not None and options['map_id'] not in saved:
            raise RequestError('map_not_found', 'The selected simulation map is unavailable')
        run_id = uuid.uuid4().hex
        run = WEB_DATA / 'runs' / run_id
        run.mkdir(parents=True)
        from realism import load_profile
        import yaml
        profile = load_profile()
        sigma = profile['parameters']['laser']['noise_sigma_m']
        sigma.update(value=options['lidar_noise_stddev'], interval=[0, .03],
                     basis='Web simulator parameter, Gaussian range error standard deviation')
        config = run / 'realism.yaml'
        config.write_text(yaml.safe_dump(profile, sort_keys=False), encoding='utf-8')
        runtime = [f"mode:={options['mode']}", 'gui:=false', 'rviz:=false', 'explore:=false',
                   f'ros_domain_id:={DOMAIN}', f'partition:=wheeltec-web-{run_id}',
                   f"seed:={options['seed']}", f'realism_profile:={config}']
        if options['map_id'] is not None:
            runtime.append(f"map:={saved[options['map_id']]}")
        else:
            runtime += [f"scenario:={options['scenario']}", f"spawn:={options['spawn']}"]
        env = self.environment(run)
        with (run / 'room.log').open('wb') as log:
            self.process = subprocess.Popen(
                [sys.executable, '-B', str(SIMULATION/'run_room.py'), *runtime],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                env=env, start_new_session=True)
        self.options = options
        self.run = run
        self.runtime_state = default_state('starting', 'Starting Gazebo and Nav2', run_id, options['mode'])
        self.deadline = time.monotonic() + 75
        return self.state()

    @staticmethod
    def environment(run):
        return os.environ | {'ROS_LOCALHOST_ONLY': '1', 'ROS_DOMAIN_ID': DOMAIN,
                             'WHEELTEC_SIM_DATA_ROOT': str(run), 'ROS_LOG_DIR': str(run/'ros-log')}

    def tick(self):
        if self.process is None:
            return
        if self.process.poll() is not None:
            self.stop(f'Gazebo launch exited ({self.process.returncode}); see {self.run / "room.log"}')
            return
        if self.ros is None:
            record = active_session(self.run, DOMAIN)
            if record is not None and record['owner_pid'] == self.process.pid:
                from web_ros import RosSession
                self.ros = RosSession(self.options['mode'], check_goal_cell)
        if self.ros is not None:
            self.ros.tick()
            if self.ros.failure:
                self.stop(self.ros.failure)
                return
            if self.ros.snapshot()['navigation_ready']:
                self.runtime_state.update(phase='running')
        if self.runtime_state['phase'] == 'starting' and time.monotonic() >= self.deadline:
            awaiting = ', '.join(self.ros.waiting_for) if self.ros else 'the owned Gazebo session'
            self.stop(f'Timed out waiting for {awaiting}. See {self.run / "room.log"}')

    def goal(self, arguments):
        state = self.state()
        if self.ros is None or state['phase'] != 'running':
            raise RequestError('navigation_unavailable', 'Wait for the simulation to run')
        if state['goal'] and state['goal']['status'] in MOVING:
            raise RequestError('goal_busy', 'Cancel the current goal before sending another')
        x, y, yaw = goal_options(arguments, state, self.ros.geometry_revision)
        return self.ros.start_goal(x, y, yaw, arguments['map_revision'])

    def cancel(self):
        if self.ros is None or self.ros.goal is None or self.ros.goal['status'] not in MOVING:
            raise RequestError('no_active_goal', 'There is no active simulation goal')
        return self.ros.cancel_goal()

    def save(self):
        if self.ros is None or self.options['mode'] != 'mapping' or not self.ros.stationary():
            raise RequestError('save_unavailable', 'Stop motion and wait for a fresh map and odometry before saving')
        name = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        output = WEB_DATA / 'maps' / name / 'room'
        try:
            with (self.run/'save.log').open('ab') as log:
                result = subprocess.run(
                    [sys.executable, '-B', str(SIMULATION/'save_map.py'), '--output', str(output), '--no-latest'],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    env=self.environment(self.run), timeout=12)
            if result.returncode:
                raise RequestError('save_failed', f'Map save failed; see {self.run / "save.log"}')
        except subprocess.TimeoutExpired as exc:
            raise RequestError('save_timeout', f'Map save timed out; see {self.run / "save.log"}') from exc
        return {'id': 'sim:' + name, 'name': name}

    def stop(self, failure=None):
        goal = self.ros.goal if self.ros is not None else None
        if self.process is not None:
            outcome = stop_owned(self.process, timeout=4.)
            if outcome['remaining_live_group_members']:
                raise RuntimeError('Some simulation processes did not exit; retry Stop')
            self.process = None
        if self.ros is not None:
            self.ros.close()
            self.ros = None
        if failure:
            self.runtime_state = default_state('failed', failure, self.runtime_state['run_id'],
                                               self.runtime_state['mode'])
            if goal and goal['status'] in MOVING:
                goal.update(status='aborted', message=failure)
            self.runtime_state['goal'] = goal
        else:
            self.runtime_state = default_state()
        return self.state()


def dispatch(session, request):
    op, arguments = request.get('op'), request.get('args', {})
    if not isinstance(arguments, dict):
        raise RequestError('invalid_request', 'args must be a JSON object')
    if op == 'start':
        return session.start(arguments)
    if op == 'goal':
        return session.goal(arguments)
    if op == 'state':
        return session.state()
    if op == 'maps':
        return [row for row, _ in available_maps()]
    if op == 'cancel':
        return session.cancel()
    if op == 'save':
        return session.save()
    if op == 'stop':
        return session.stop()
    raise RequestError('invalid_request', 'Unknown simulator operation')


def main():
    import fcntl
    import signal
    os.environ.update(ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID=DOMAIN, RCUTILS_LOGGING_USE_STDOUT='0')
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    with (WEB_DATA/'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A Windows simulation worker is already running')
        requests = queue.Queue(maxsize=32)

        def read_requests():
            try:
                for line in sys.stdin:
                    requests.put(line)
            finally:
                requests.put(None)

        signal.signal(signal.SIGTERM, signal.default_int_handler)
        threading.Thread(target=read_requests, daemon=True).start()
        session = Session()
        try:
            while True:
                session.tick()
                try:
                    line = requests.get(timeout=.03)
                except queue.Empty:
                    continue
                if line is None:
                    break
                request_id = None
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise RequestError('invalid_request', 'Request must be a JSON object')
                    request_id = request.get('id')
                    result = dispatch(session, request)
                    response = {'id': request_id, 'ok': True, 'result': result}
                except RequestError as exc:
                    response = {'id': request_id, 'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
                except (ValueError, OSError, RuntimeError) as exc:
                    response = {'id': request_id, 'ok': False,
                                'error': {'code': 'simulation_error', 'message': str(exc)}}
                print(json.dumps(response, allow_nan=False, ensure_ascii=False), flush=True)
        except (KeyboardInterrupt, BrokenPipeError):
            pass
        finally:
            session.stop()


if __name__ == '__main__':
    main()
