"""Exercise the real browser worker, Gazebo, SLAM, Nav2, and AMCL in WSL."""
import json
from pathlib import Path
import select
import subprocess
import time


def main():
    script = Path(__file__).resolve().with_name('web_session.sh')
    with subprocess.Popen(['bash', str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          text=True, encoding='utf-8') as worker:
        sequence = 0

        def request(op, args=None):
            nonlocal sequence
            sequence += 1
            worker.stdin.write(json.dumps({'id': sequence, 'op': op, 'args': args or {}}) + '\n')
            worker.stdin.flush()
            if not select.select([worker.stdout], [], [], 16)[0]:
                raise TimeoutError(op)
            line = worker.stdout.readline()
            if not line:
                raise RuntimeError(f'{op}: worker exited with code {worker.poll()}')
            response = json.loads(line)
            assert response.get('id') == sequence, response
            return response

        def rpc(op, args=None):
            response = request(op, args)
            if not response['ok']:
                raise RuntimeError(f"{op}: {response['error']}")
            return response['result']

        def wait(accept, timeout, label):
            end = time.monotonic() + timeout
            message = None
            while time.monotonic() < end:
                state = rpc('state')
                if state['phase'] == 'failed':
                    raise RuntimeError(state['message'])
                if accept(state):
                    return state
                if state['message'] != message:
                    message = state['message']
                    print(message, flush=True)
                time.sleep(.25)
            raise TimeoutError(f'{label}: run={state["run_id"]}, phase={state["phase"]}, goal={state["goal"]}')

        def start(args):
            pending = rpc('start', args)
            print('started', pending['run_id'], pending['mode'], flush=True)
            state = wait(lambda s: s['navigation_ready'], 77, 'ready')
            print('ready', {'run_id': state['run_id'], 'map': [state['map']['width'], state['map']['height']],
                            'scan_beams': len(state['scan']['ranges']), 'pose': state['pose']}, flush=True)
            assert state['map']['frame'] == state['pose']['frame'] == state['laser_pose']['frame'] == 'map'
            return state

        def target(state, x, y):
            return {'run_id': state['run_id'], 'map_revision': state['map']['revision'],
                    'frame': 'map', 'x': x, 'y': y, 'yaw': 0.}

        try:
            state = start({'scenario': 'baseline'})
            rejected = request('goal', target(state, 100., 100.))
            assert not rejected['ok'] and rejected['error']['code'] == 'invalid_goal', rejected
            assert rpc('goal', target(state, .75, 0.))['status'] == 'pending'
            state = wait(lambda s: s['goal']['status'] not in ('pending', 'active', 'canceling'), 30, 'navigate')
            assert state['goal']['status'] == 'succeeded', state['goal']
            assert abs(state['pose']['x'] - .75) <= .20, state['pose']
            print('reached', state['pose'], flush=True)

            rpc('goal', target(state, 0., 0.))
            wait(lambda s: s['goal']['status'] == 'active', 10, 'active for cancellation')
            assert rpc('cancel')['status'] == 'canceling'
            wait(lambda s: s['goal']['status'] == 'canceled', 10, 'cancel')
            state = wait(lambda s: s['odom'] and abs(s['odom']['linear']) < .02
                         and abs(s['odom']['angular']) < .05, 5, 'stationary odometry')
            print('canceled with stationary odometry', state['odom'], flush=True)

            time.sleep(.75)
            record = rpc('save')
            assert record in rpc('maps')
            assert rpc('stop')['phase'] == 'stopped'
            print('saved', record, flush=True)
            original_run = state['run_id']
            state = start({'mode': 'localization', 'map_id': record['id']})
            assert state['run_id'] != original_run and abs(state['pose']['x']) < .35
            rejected = request('goal', target(state, .3, 0.) | {'run_id': original_run})
            assert not rejected['ok'] and rejected['error']['code'] == 'stale_map', rejected
            assert rpc('goal', target(state, .7, 0.))['status'] == 'pending'
            state = wait(lambda s: s['goal']['status'] not in ('pending', 'active', 'canceling'), 30, 'localized navigate')
            assert state['goal']['status'] == 'succeeded', state['goal']
            assert abs(state['pose']['x'] - .7) <= .20, state['pose']
            print('reloaded map reached goal', state['pose'], flush=True)
        finally:
            if worker.poll() is None:
                stopped = rpc('stop')
                assert stopped['phase'] == 'stopped', stopped
            worker.stdin.close()
            worker.wait(timeout=10)
        assert worker.returncode == 0, worker.returncode


if __name__ == '__main__':
    main()
