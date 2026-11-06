import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import paramiko
from fastapi.testclient import TestClient
from console.backend import app as gateway
from console.backend import recovery_script as recovery
from console.backend.transport import SSH

PROFILE={'name':'robot','kind':'robot','host':'192.0.2.1','username':'wheeltec','fingerprint':'SHA256:test'}

class AutoPrepareTests(unittest.TestCase):
    def test_one_password_connect_automatically_prepares_then_adopts_same_ssh(self):
        ssh=MagicMock();ssh.adapter_token.return_value='token'
        ssh.request.side_effect=[paramiko.ChannelException(2,'Connection refused'),b'{"kind":"robot"}']
        ssh.prepare_robot.return_value={'status':'ready','started':['adapter']}
        client=TestClient(gateway.app,base_url='http://127.0.0.1:8766');client.get('/bootstrap')
        session=gateway.Session()
        with patch.object(gateway,'session',session),patch.object(gateway,'profiles',return_value={'r':PROFILE}),patch.object(gateway,'SSH',return_value=ssh):
            r=client.post('/api/v1/connect-robot',json={'password':'sample'},headers={'origin':'http://127.0.0.1:8766'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(ssh.prepare_robot.call_args.args[0],'sample')
        self.assertIs(session.ssh,ssh)
        self.assertIsNone(session.recovery)
        self.assertTrue(all(call.args[0]=='GET' for call in ssh.request.call_args_list))
    def test_already_online_adapter_does_not_run_preparation_or_reset_clock(self):
        ssh=MagicMock();ssh.adapter_token.return_value='token';ssh.request.return_value=b'{"kind":"robot"}'
        client=TestClient(gateway.app,base_url='http://127.0.0.1:8766');client.get('/bootstrap')
        with patch.object(gateway,'session',gateway.Session()),patch.object(gateway,'profiles',return_value={'r':PROFILE}),patch.object(gateway,'SSH',return_value=ssh):
            r=client.post('/api/v1/connect-robot',json={'password':'sample'},headers={'origin':'http://127.0.0.1:8766'})
        self.assertEqual(r.status_code,200)
        ssh.prepare_robot.assert_not_called()

class PrepareSafetyTests(unittest.TestCase):
    def test_rejected_nan_odometry_still_returns_clear_json_error(self):
        import io
        from contextlib import redirect_stdout
        output=io.StringIO()
        with patch.object(recovery,'prepare_stack',return_value={'status':'blocked','reason':'vehicle_moving','data':{'/odom':[float('nan'),0]}}),redirect_stdout(output):
            recovery.main('prepare')
        result=json.loads(output.getvalue())
        self.assertEqual(result['reason'],'vehicle_moving')
        self.assertEqual(result['data']['/odom'],[None,0])

    def test_unsafe_hold_blocks_driver_slam_and_adapter_start(self):
        names=(*recovery.COMPONENTS,'adapter')
        plan={'status':'planned','needed':list(names),'boot_id':'b','listening':False,
              'processes':{name:{'alive':False} for name in names}}
        fake_fcntl=SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=MagicMock())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'owned-processes.json').write_text('{}')
            with patch.dict('sys.modules',{'fcntl':fake_fcntl}),patch.object(recovery,'runtime_root',return_value=root),patch.object(recovery,'preparation_plan',return_value=plan),patch.object(recovery,'boot_id',return_value='b'),patch.object(recovery,'fixed_commands',return_value={name:'fixed' for name in names}),patch.object(recovery,'require_parked',return_value={'reason':'not_parked'}),patch.object(recovery,'launch_component') as launch:
                result=recovery.prepare_stack()
        self.assertEqual(result['reason'],'not_parked')
        self.assertEqual([c.args[0] for c in launch.call_args_list],['lidar','camera','model','ekf','control_stack'])
    def test_existing_components_are_preserved(self):
        names=(*recovery.COMPONENTS,'adapter')
        plan={'status':'planned','needed':['camera','adapter'],'boot_id':'b','listening':False,
              'processes':{name:{'alive':name not in ('camera','adapter')} for name in names}}
        fake_fcntl=SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=MagicMock())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'owned-processes.json').write_text('{}')
            with patch.dict('sys.modules',{'fcntl':fake_fcntl}),patch.object(recovery,'runtime_root',return_value=root),patch.object(recovery,'preparation_plan',return_value=plan),patch.object(recovery,'boot_id',return_value='b'),patch.object(recovery,'fixed_commands',return_value={'camera':'fixed','adapter':'fixed'}),patch.object(recovery,'require_parked',return_value={'reason':None}),patch.object(recovery,'inspect_adapter',return_value={'missing_services':[]}),patch.object(recovery,'listening',return_value=True),patch.object(recovery,'launch_component') as launch:
                result=recovery.prepare_stack()
        self.assertEqual(result['status'],'ready')
        self.assertEqual([c.args[0] for c in launch.call_args_list],['camera','adapter'])
    def test_clock_password_is_stdin_only_and_live_clock_is_not_changed(self):
        ssh=object.__new__(SSH);ssh.client=MagicMock()
        stdin,stdout,stderr=MagicMock(),MagicMock(),MagicMock()
        stdout.channel.recv_exit_status.return_value=0
        ssh.client.exec_command.return_value=(stdin,stdout,stderr)
        ssh.adapter_operation=MagicMock(side_effect=[{'status':'planned','wall_time':0,'clock_reset_allowed':True},{'status':'ready'}])
        self.assertEqual(ssh.prepare_robot('sample-password')['status'],'ready')
        command=ssh.client.exec_command.call_args.args[0]
        self.assertNotIn('sample-password',command)
        stdin.write.assert_called_once_with('sample-password\n')
        ssh.client.exec_command.reset_mock()
        ssh.adapter_operation=MagicMock(return_value={'status':'planned','wall_time':0,'clock_reset_allowed':False})
        self.assertEqual(ssh.prepare_robot('sample-password')['reason'],'clock_drift_live_stack')
        ssh.client.exec_command.assert_not_called()
