import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from console.backend import app as gateway
from console.backend.simulation import SimulationWorker


MOCK_WORKER = '''
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    op, args = request['op'], request['args']
    if op == 'goal':
        reply = {'ok': False, 'error': {'code': 'occupied', 'message': 'Goal is occupied'}}
    else:
        result = [{'id': 'map-1', 'name': 'Room'}] if op == 'maps' else {'op': op, 'args': args}
        reply = {'ok': True, 'result': result}
    print(json.dumps({'id': request['id'], **reply}), flush=True)
'''


class SimulationGatewayTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(gateway.app, base_url='http://127.0.0.1:8766')
        self.headers = {'origin': 'http://127.0.0.1:8766'}
        self.worker = SimulationWorker([sys.executable, '-u', '-c', MOCK_WORKER])
        self.addCleanup(self.worker.close)
        change = patch('console.backend.simulation.worker', self.worker)
        change.start()
        self.addCleanup(change.stop)

    def start(self, payload):
        return self.client.post('/api/v1/simulation/start', json=payload, headers=self.headers)

    def test_get_state_does_not_start_wsl_and_uses_existing_session_cookie(self):
        self.assertEqual(self.client.get('/api/v1/simulation/state').status_code, 401)
        self.client.get('/bootstrap')
        response = self.client.get('/api/v1/simulation/state')
        self.assertEqual(response.json()['phase'], 'stopped')
        self.assertIsNone(self.worker.process)

    def test_only_simulation_worker_receives_start_and_map_requests(self):
        self.client.get('/bootstrap')
        with patch.object(gateway, 'SSH', side_effect=AssertionError('unexpected SSH')):
            response = self.start({'mode': 'mapping', 'seed': 42})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {'op': 'start', 'args': {'mode': 'mapping', 'seed': 42}})
            self.assertEqual(self.client.get('/api/v1/simulation/maps').json(),
                             {'maps': [{'id': 'map-1', 'name': 'Room'}]})
            response = self.client.post('/api/v1/simulation/stop', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(self.worker.process)
        self.assertEqual(self.start({'mode': 'mapping', 'host': 'robot'}).status_code, 422)

    def test_goal_rejection_and_same_origin_gate(self):
        self.client.get('/bootstrap')
        point = {'x': 1, 'y': 2, 'yaw': 0, 'frame': 'map', 'run_id': 'test', 'map_revision': 3}
        self.assertEqual(self.client.post('/api/v1/simulation/goal', json=point).status_code, 403)
        response = self.client.post('/api/v1/simulation/goal', json=point, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['code'], 'occupied')
