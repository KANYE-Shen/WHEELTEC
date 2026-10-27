import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from console.backend import app as gateway
from console.backend.transport import PinnedKey
import paramiko


class GatewayTests(unittest.TestCase):
    def setUp(self): self.c = TestClient(
        gateway.app, base_url='http://127.0.0.1:8766'); self.headers = {'origin': 'http://127.0.0.1:8766'}

    def test_auth_required(self): self.assertEqual(
        self.c.get('/api/v1/profiles').status_code, 401)

    def test_foreign_origin_and_host(self):
        self.c.get('/bootstrap')
        self.assertEqual(self.c.post(
            '/api/v1/disconnect', headers={'origin': 'http://evil.test'}).status_code, 403)
        self.assertEqual(self.c.get(
            '/bootstrap', headers={'host': 'evil.test'}).status_code, 403)

    def test_secret_fields_not_saved(self):
        self.c.get('/bootstrap')
        with tempfile.TemporaryDirectory() as d, patch.object(gateway, 'STATE', Path(d)):
            data = {'name': 'test', 'kind': 'robot', 'host': 'example', 'username': 'user',
                    'fingerprint': 'SHA256:abc', 'password': 'NEVER_SAVE', 'adapter_token': 'NEVER_SAVE'}
            self.assertEqual(self.c.post('/api/v1/profiles',
                             json=data, headers=self.headers).status_code, 200)
            self.assertNotIn(
                'NEVER_SAVE', (Path(d)/'profiles.json').read_text())

    def test_ws_foreign_origin(self):
        self.c.get('/bootstrap')
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect):
            with self.c.websocket_connect('ws://127.0.0.1:8766/api/v1/events', headers={'origin': 'http://evil.test'}):
                pass

    def test_pin_rejects_untrusted(self):
        key = paramiko.RSAKey.generate(1024)
        with self.assertRaises(paramiko.SSHException):
            PinnedKey('SHA256:wrong').missing_host_key(None, 'host', key)

    def test_managed_logs_contain_only_fixed_events(self):
        self.c.get('/bootstrap')
        self.c.post('/api/v1/disconnect', headers=self.headers)
        response = self.c.get('/api/v1/logs')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(x['name'] == 'console.gateway' for x in response.json()))
        self.assertNotIn('password', str(response.json()).lower())

    def test_robot_readonly_terminal_cannot_claim_verified_stop(self):
        import json
        from unittest.mock import MagicMock
        self.c.get('/bootstrap')
        fake=gateway.Session()
        fake.ssh=MagicMock()
        fake.request=MagicMock(return_value=json.dumps({'kind':'robot','control':{'enabled':False}}).encode())
        with patch.object(gateway,'session',fake):
            with self.c.websocket_connect('ws://127.0.0.1:8766/api/v1/terminal',headers=self.headers) as ws:
                self.assertIn('read-only',ws.receive_text())
        fake.ssh.terminal.assert_not_called()
