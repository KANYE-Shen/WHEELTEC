import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import paramiko
from fastapi.testclient import TestClient
from console.backend import app as gateway
from console.backend import recovery_script
from console.backend.transport import SSH

PROFILE={'name':'robot','kind':'robot','host':'192.0.2.1','username':'wheeltec','fingerprint':'SHA256:test'}

class AdapterRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.session=gateway.Session()
        self.ssh=MagicMock()
        self.ssh.adapter_token.return_value='token'
        self.ssh.prepare_robot.return_value={'status':'blocked','reason':'test_unavailable'}
        self.ssh.request.side_effect=paramiko.ChannelException(2,'Connection refused')
        self.client=TestClient(gateway.app,base_url='http://127.0.0.1:8766')
        self.client.get('/bootstrap')
        self.headers={'origin':'http://127.0.0.1:8766'}
        self.patches=[patch.object(gateway,'session',self.session),patch.object(gateway,'profiles',return_value={'robot':PROFILE}),patch.object(gateway,'SSH',return_value=self.ssh)]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
    def connect(self):
        return self.client.post('/api/v1/connect-robot',json={'password':'sample'},headers=self.headers)
    def restore(self,body=None):
        return self.client.post('/api/v1/adapter/restore',json=body if body is not None else {'confirm_parked':True},headers=self.headers)
    def test_refused_adapter_keeps_ssh_for_fixed_diagnostics_not_control(self):
        response=self.connect()
        self.assertEqual(response.status_code,503)
        self.assertIn('端口',response.json()['detail'])
        self.assertIsNone(self.session.ssh)
        self.assertIs(self.session.recovery['ssh'],self.ssh)
        self.ssh.close.assert_not_called()
        self.ssh.adapter_operation.return_value={'status':'inspected','log_tail':'Traceback: example','missing_services':[]}
        r=self.client.get('/api/v1/adapter/diagnostics')
        self.assertEqual(r.status_code,200)
        self.ssh.adapter_operation.assert_called_once_with('inspect')
        self.ssh.request.assert_called_once_with('GET','/state',token='token')
    def test_disconnect_closes_provisional_ssh_without_chassis_request(self):
        self.connect()
        self.client.post('/api/v1/disconnect',json={},headers=self.headers)
        self.ssh.close.assert_called_once()
        self.assertIsNone(self.session.recovery)
        self.ssh.request.assert_called_once_with('GET','/state',token='token')
    def test_restore_requires_confirmation_and_rejects_command_input(self):
        self.connect()
        for body in ({},{'confirm_parked':False},{'confirm_parked':True,'command':'anything'}):
            self.assertEqual(self.restore(body).status_code,400)
        self.ssh.adapter_operation.assert_not_called()
    def test_blocked_recovery_keeps_ssh_and_does_not_publish_control_session(self):
        self.connect()
        self.ssh.adapter_operation.return_value={'status':'blocked','reason':'other_services_missing','missing_services':['slam']}
        r=self.restore()
        self.assertEqual(r.status_code,409)
        self.assertIn('slam',r.json()['detail'])
        self.assertIsNone(self.session.ssh)
        self.ssh.request.assert_called_once_with('GET','/state',token='token')
    def test_success_adopts_same_ssh_only_after_adapter_check(self):
        self.connect()
        self.ssh.adapter_operation.return_value={'status':'ready'}
        self.ssh.request.side_effect=None
        self.ssh.request.return_value=b'{"kind":"robot"}'
        r=self.restore()
        self.assertEqual(r.status_code,200)
        self.ssh.adapter_operation.assert_called_once_with('restore')
        self.assertIs(self.session.ssh,self.ssh)
        self.assertIsNone(self.session.recovery)
        self.assertTrue(all(call.args[0]=='GET' for call in self.ssh.request.call_args_list))

class FixedRecoveryGuardTests(unittest.TestCase):
    def test_restore_never_spawns_when_other_services_missing_or_parked_check_fails(self):
        safe={'processes':{'adapter':{'alive':False}},'missing_services':[], 'listening':False,'command_matches':True}
        fcntl=SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=MagicMock())
        cases=[({**safe,'missing_services':['slam']},'other_services_missing'),(safe,'not_parked')]
        with tempfile.TemporaryDirectory() as directory:
            for evidence,expected in cases:
                with self.subTest(expected=expected),patch.dict('sys.modules',{'fcntl':fcntl}),patch.object(recovery_script,'runtime_root',return_value=Path(directory)),patch.object(recovery_script,'inspect_adapter',return_value=evidence),patch.object(recovery_script,'require_parked',return_value={'reason':'not_parked'}),patch('subprocess.Popen') as launch:
                    result=recovery_script.restore_adapter()
                    self.assertEqual(result['reason'],expected)
                    launch.assert_not_called()

    def test_other_missing_services_and_changed_command_block_restore(self):
        state={'processes':{'adapter':{'alive':False}},'missing_services':[], 'listening':False,'command_matches':True}
        self.assertIsNone(recovery_script.recovery_blocker(state))
        self.assertEqual(recovery_script.recovery_blocker({**state,'missing_services':['slam']}),'other_services_missing')
        self.assertEqual(recovery_script.recovery_blocker({**state,'command_matches':False}),'adapter_command_changed')
        self.assertEqual(recovery_script.recovery_blocker({**state,'processes':{'adapter':{'alive':True}}}),'adapter_still_running')
    def test_parked_guard_rejects_armed_stale_motion_nan_explorer_and_missing_nav(self):
        data={'/safety/status':{'armed':False},'/safety/selected_source':'hold','/console/driver_cmd_vel':[0,0],'/odom':[0,0]}
        received={k:10 for k in data}; life={str(i):'active' for i in range(5)}
        check=lambda d=data,r=received,nz=[],ex=False,lf=life:recovery_script.parked_blocker(d,r,10.1,nz,ex,lf)
        self.assertIsNone(check())
        self.assertEqual(check({**data,'/safety/status':{'armed':True}}),'not_parked')
        self.assertEqual(check(r={**received,'/odom':9}),'parked_evidence_unavailable')
        self.assertEqual(check(nz=['/console/driver_cmd_vel']),'vehicle_moving')
        self.assertEqual(check({**data,'/odom':[float('nan'),0]}),'vehicle_moving')
        self.assertEqual(check(ex=True),'explorer_running')
        self.assertEqual(check(lf={}), 'navigation_services_unavailable')
    def test_arbitrary_transport_operation_is_rejected_before_exec(self):
        ssh=object.__new__(SSH);ssh.client=MagicMock()
        with self.assertRaises(ValueError):ssh.adapter_operation('run anything')
        ssh.client.exec_command.assert_not_called()
