import json
import unittest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from console.backend import app as gateway
from console.backend.transport import SSH

PROFILE = {'name': 'robot', 'kind': 'robot', 'host': '192.0.2.1', 'username': 'wheeltec', 'fingerprint': 'SHA256:test'}

class PasswordConnectTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(gateway.app, base_url='http://127.0.0.1:8766')
        self.client.get('/bootstrap')
        self.headers = {'origin': 'http://127.0.0.1:8766'}
        self.session = gateway.Session()
    def post(self, password='secret'):
        return self.client.post('/api/v1/connect-robot', json={'password':password}, headers=self.headers)
    def test_password_connect_fetches_adapter_token_over_ssh(self):
        ssh=MagicMock(); ssh.adapter_token.return_value='token'; ssh.request.return_value=json.dumps({'kind':'robot'}).encode()
        with patch.object(gateway,'session',self.session), patch.object(gateway,'profiles',return_value={'robot':PROFILE}), patch.object(gateway,'SSH',return_value=ssh) as ctor:
            result=self.post()
        self.assertEqual(result.status_code,200)
        ctor.assert_called_once_with(gateway.valid_profile(PROFILE),'secret')
        ssh.request.assert_called_once_with('GET','/state',token='token')
        self.assertEqual(self.session.token,'token')
        self.assertNotIn('secret',str(result.json()))
    def test_existing_session_is_not_disrupted(self):
        old=MagicMock();self.session.ssh=old
        with patch.object(gateway,'session',self.session), patch.object(gateway,'profiles',return_value={'robot':PROFILE}), patch.object(gateway,'SSH') as ctor:
            result=self.post()
        self.assertEqual(result.status_code,409);ctor.assert_not_called();old.close.assert_not_called();old.request.assert_not_called()
    def test_explicit_disconnect_clears_stale_session_then_can_reconnect(self):
        old=MagicMock();old.request.side_effect=OSError('offline');self.session.ssh=old
        new=MagicMock();new.adapter_token.return_value='token';new.request.return_value=b'{"kind":"robot"}'
        with patch.object(gateway,'session',self.session), patch.object(gateway,'profiles',return_value={'robot':PROFILE}), patch.object(gateway,'SSH',return_value=new):
            self.assertEqual(self.post().status_code,409)
            self.assertEqual(self.client.post('/api/v1/disconnect',json={},headers=self.headers).status_code,200)
            self.assertEqual(self.post().status_code,200)
        old.close.assert_called_once();self.assertIs(self.session.ssh,new)
    def test_missing_adapter_or_token_does_not_create_session(self):
        ssh=MagicMock();ssh.adapter_token.return_value='token';ssh.request.side_effect=OSError('sensitive exception')
        with patch.object(gateway,'session',self.session), patch.object(gateway,'profiles',return_value={'robot':PROFILE}), patch.object(gateway,'SSH',return_value=ssh):
            result=self.post()
        self.assertEqual(result.status_code,503);self.assertIn('适配器',result.json()['detail']);self.assertIsNone(self.session.ssh);ssh.close.assert_called_once();self.assertNotIn('sensitive',str(result.json()))
    def test_missing_profile_and_empty_password_are_rejected(self):
        with patch.object(gateway,'session',self.session), patch.object(gateway,'profiles',return_value={}):
            self.assertEqual(self.post().status_code,400)
        with patch.object(gateway,'session',self.session), patch.object(gateway,'profiles',return_value={'r':PROFILE}), patch.object(gateway,'SSH') as ctor:
            self.assertEqual(self.post('').status_code,400);ctor.assert_not_called()
    def test_sftp_reads_fixed_token_only_and_rejects_empty(self):
        ssh=object.__new__(SSH);ssh.client=MagicMock();sftp=ssh.client.open_sftp.return_value
        sftp.open.return_value.__enter__.return_value.read.return_value=b'abc\n'
        self.assertEqual(ssh.adapter_token(),'abc')
        sftp.open.assert_called_with('.wheeltec-console/adapter.token','r')
        sftp.open.return_value.__enter__.return_value.read.return_value=b'\n'
        with self.assertRaises(ValueError):ssh.adapter_token()

    def test_disconnect_cancels_pending_connection_for_both_endpoints(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                session = gateway.Session()
                ssh = MagicMock()
                ssh.adapter_token.return_value = 'token'
                ssh.request.return_value = b'{"kind":"robot"}'
                async def scenario():
                    entered, release = asyncio.Event(), asyncio.Event()
                    original = asyncio.to_thread
                    async def delayed(fn, *args, **kwargs):
                        if fn is gateway.SSH:
                            entered.set()
                            await release.wait()
                        return await original(fn, *args, **kwargs)
                    request = MagicMock()
                    async def body():
                        return {'profile': PROFILE, 'password': 'secret', 'adapter_token': 'token'}
                    request.json = body
                    with patch.object(gateway.asyncio, 'to_thread', delayed):
                        task = asyncio.create_task((gateway.connect if legacy else gateway.connect_robot)(request))
                        await asyncio.wait_for(entered.wait(), timeout=3)
                        await gateway.disconnect()
                        release.set()
                        with self.assertRaises(gateway.HTTPException) as error:
                            await task
                        self.assertEqual(error.exception.status_code, 409)
                with patch.object(gateway, 'session', session), patch.object(gateway, 'profiles', return_value={'robot': PROFILE}), patch.object(gateway, 'SSH', return_value=ssh):
                    asyncio.run(scenario())
                self.assertIsNone(session.ssh)
                self.assertFalse(session.connecting)
                ssh.close.assert_called_once()

    def test_legacy_connect_still_replaces_existing_session(self):
        old, new = MagicMock(), MagicMock()
        new.request.return_value = b'{"kind":"robot"}'
        self.session.ssh, self.session.token = old, 'old-token'
        with patch.object(gateway, 'session', self.session), patch.object(gateway, 'SSH', return_value=new):
            result = self.client.post('/api/v1/connect', json={'profile':PROFILE, 'password':'secret', 'adapter_token':'token'}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        old.request.assert_called_once_with('POST', '/control', b'{"action": "stop"}', 'old-token')
        old.close.assert_called_once()
        self.assertIs(self.session.ssh, new)
