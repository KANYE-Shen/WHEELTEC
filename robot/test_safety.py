import importlib
import unittest
class SafetyTests(unittest.TestCase):
    def setUp(self): self.module=importlib.import_module('safety')
    def ready(self):
        gate=self.module.MotionGate(.5,1.,.1,.3)
        gate.heartbeat(1.); gate.command((0.,0.),1.)
        self.assertTrue(gate.arm(1.)); return gate
    def test_boot_and_lost_heartbeat_latch_until_explicit_rearm(self):
        gate=self.module.MotionGate(.5,1.,.1,.3)
        gate.command((.1,0.),1.); self.assertEqual(gate.output(1.),(0.,0.))
        gate=self.ready(); gate.command((.1,0.),1.1)
        self.assertEqual(gate.output(1.2),(.1,0.))
        self.assertEqual(gate.output(2.2),(0.,0.))
        gate.heartbeat(2.3); gate.command((.1,0.),2.3)
        self.assertEqual(gate.output(2.3),(0.,0.)); self.assertFalse(gate.arm(2.3))
        gate.command((0.,0.),2.3); self.assertTrue(gate.arm(2.3))
    def test_timeout_estop_invalid_and_reverse_time_stop(self):
        gate=self.ready(); gate.command((.2,-.8),1.1)
        self.assertEqual(gate.output(1.2),(.1,-.3))
        self.assertEqual(gate.output(1.7),(0.,0.))
        gate=self.ready(); gate.emergency(True); self.assertEqual(gate.output(1.1),(0.,0.))
        gate.emergency(False); self.assertEqual(gate.output(1.2),(0.,0.))
        gate=self.ready(); gate.command((float('nan'),0),1.1); self.assertEqual(gate.output(1.2),(0.,0.))
        gate=self.ready(); gate.output(1.1); self.assertEqual(gate.output(.5),(0.,0.))
    def test_robot_dimensions_require_the_shared_measured_calibration(self):
        import json,math
        from pathlib import Path
        from preflight import calibrated_geometry
        profile=json.loads((Path(__file__).resolve().parent/'calibration/2026-10-27.json').read_text(encoding='utf-8'))
        with self.assertRaises(ValueError): calibrated_geometry(profile)
        for name in ('length_m','width_m'):
            entry=profile['parameters']['geometry'][name]
            entry.update(source='measured',evidence='unit-test fixture only')
        polygon,radius=calibrated_geometry(profile)
        self.assertEqual(polygon[0],[.2,.215]); self.assertAlmostEqual(radius,.35)

    def test_airborne_gate_does_not_require_future_ground_braking_measurement(self):
        from preflight import validate
        import json
        from pathlib import Path
        from unittest.mock import patch
        profile=json.loads((Path(__file__).resolve().parent/'calibration/2026-10-27.json').read_text(encoding='utf-8'))
        for key in ('length_m','width_m'): profile['parameters']['geometry'][key].update(source='measured',evidence='unit-test fixture')
        config={'hardware_verified':True,'measured_kinematics':'differential','base_frame':'base','odom_frame':'odom','scan_frame':'laser','scan_topic':'/scan','odom_topic':'/odom','driver_command_topic':'/driver','driver_command_type':'geometry_msgs/msg/Twist','calibration_file':'unit-test-calibration','approval_record':'unit-test-approval','admission_protocol':'three-stage-20261029','driver_timeout_verified_s':.2,'measured_braking_distance_m':None,'safety':{'operator_timeout_s':1.,'command_timeout_s':.5,'max_linear_m_s':.1,'max_yaw_rad_s':.3,'obstacle_margin_m':.1}}
        # In-memory test fixture; no gate approval file is created.
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',side_effect=[json.dumps(profile),'流程版本:three-stage-20261029\n允许阶段一实测']):
            self.assertIs(validate(config,required_gate=1),config)
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',return_value=json.dumps(profile)):
            with self.assertRaises(ValueError): validate(config,required_gate=2)

    def test_authentication_and_launch_fail_closed(self):
        from bridge_auth import authenticate
        self.assertTrue(authenticate('Bearer '+'a'*32,'a'*32))
        self.assertFalse(authenticate('Bearer wrong','a'*32)); self.assertFalse(authenticate('', ''))
        from preflight import validate
        import json
        from pathlib import Path
        config=json.loads((Path(__file__).resolve().parent/'config/robot.json').read_text(encoding='utf-8'))
        with self.assertRaises(ValueError): validate(config)
if __name__=='__main__': unittest.main()


class ThreeStageApprovalTests(unittest.TestCase):
    def fixture(self,complete=False,braking=None):
        import json
        from pathlib import Path
        profile=json.loads((Path(__file__).resolve().parent/'calibration/2026-10-27.json').read_text(encoding='utf-8'))
        for key in ('length_m','width_m'):
            profile['parameters']['geometry'][key].update(source='measured',evidence='test fixture only')
        profile.update(calibration_complete=complete,physical_data_collected=complete)
        config={'admission_protocol':'three-stage-20261029','hardware_verified':True,'measured_kinematics':'differential','base_frame':'base','odom_frame':'odom','scan_frame':'laser','scan_topic':'/scan','odom_topic':'/odom','driver_command_topic':'/driver','driver_command_type':'geometry_msgs/msg/Twist','calibration_file':'fixture-calibration','approval_record':'fixture-approval','driver_timeout_verified_s':.2,'measured_braking_distance_m':braking,'safety':{'operator_timeout_s':1.,'command_timeout_s':.5,'max_linear_m_s':.1,'max_yaw_rad_s':.3,'obstacle_margin_m':.1}}
        return config,profile
    def check(self,stage,record,complete=False,braking=None,protocol='three-stage-20261029'):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from preflight import validate
        c,p=self.fixture(complete,braking);c['admission_protocol']=protocol
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',side_effect=[json.dumps(p),record]):
            return validate(c,required_gate=stage)
    def record(self,stage):
        return '流程版本:three-stage-20261029\n允许阶段'+{1:'一',2:'二',3:'三'}[stage]+'实测'
    def test_stage_one_can_collect_missing_ground_calibration(self):
        self.assertTrue(self.check(1,self.record(1)))
    def test_stage_two_requires_completed_calibration(self):
        with self.assertRaises(ValueError):self.check(2,self.record(2),braking=.1)
    def test_stage_two_requires_braking(self):
        with self.assertRaises(ValueError):self.check(2,self.record(2),complete=True)
    def test_stage_three_requires_complete_measurement(self):
        with self.assertRaises(ValueError):self.check(3,self.record(3),braking=.1)
    def test_each_new_stage_accepts_only_explicit_matching_record(self):
        for stage in (1,2,3):
            with self.subTest(stage=stage):self.assertTrue(self.check(stage,self.record(stage),complete=True,braking=.1))
    def test_old_approval_is_not_reinterpreted_as_new_stage(self):
        with self.assertRaises(ValueError):self.check(1,'通过关卡1')
    def test_foreign_protocol_is_rejected(self):
        with self.assertRaises(ValueError):self.check(1,self.record(1),protocol='legacy')
    def test_wrong_stage_record_and_negative_sentence_are_rejected(self):
        for record in [self.record(2),'流程版本:three-stage-20261029\n不允许阶段一实测','允许阶段一实测']:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):self.check(1,record)
    def test_only_three_stages_are_valid(self):
        for stage in (0,4,5,True,1.5):
            with self.subTest(stage=stage):
                with self.assertRaises(ValueError):self.check(stage,self.record(1),complete=True,braking=.1)


class TimeoutEvidenceTests(unittest.TestCase):
    def gate(self):
        from safety import MotionGate
        gate=MotionGate(.5,.8,.1,.3)
        gate.command((0.,0.),1.);gate.heartbeat(1.)
        self.assertTrue(gate.arm(1.))
        return gate

    def test_command_timeout_is_latched_with_input_ages(self):
        gate=self.gate();gate.heartbeat(1.6)
        self.assertEqual(gate.output(1.6),(0.,0.));self.assertFalse(gate.armed)
        detail=gate.status(1.6)['timeout_detail']
        self.assertEqual(detail['expired'],['command'])
        self.assertAlmostEqual(detail['command_age_s'],.6)
        gate.stop('operator_hold');gate.command((0.,0.),2.);gate.heartbeat(2.)
        self.assertEqual(gate.status(2.)['timeout_detail'],detail)
        self.assertTrue(gate.arm(2.));self.assertIsNone(gate.status(2.)['timeout_detail'])

    def test_operator_timeout_is_distinct_and_does_not_auto_resume(self):
        gate=self.gate();gate.command((.05,0.),1.9)
        self.assertEqual(gate.output(1.9),(0.,0.))
        self.assertEqual(gate.status(1.9)['timeout_detail']['expired'],['operator'])
        gate.heartbeat(2.);gate.command((.05,0.),2.)
        self.assertEqual(gate.output(2.),(0.,0.));self.assertFalse(gate.armed)


class StatusCadenceTests(unittest.TestCase):
    def test_repeated_status_is_bounded_and_transitions_are_immediate(self):
        from safety import StatusCadence
        cadence=StatusCadence(.1)
        self.assertTrue(cadence.due(('held',False),0.))
        self.assertFalse(cadence.due(('held',False),.02))
        self.assertTrue(cadence.due(('armed',True),.021))
        self.assertFalse(cadence.due(('armed',True),.04))
        self.assertTrue(cadence.due(('held',False),.041))
        self.assertTrue(cadence.due(('held',False),.142))

    def test_watchdog_keeps_every_driver_tick_while_bounding_status(self):
        import ast,types
        from pathlib import Path
        from unittest.mock import patch
        from safety import MotionGate,StatusCadence
        source=ast.parse((Path(__file__).parent/'watchdog.py').read_text())
        cls=next(n for f in source.body if isinstance(f,ast.FunctionDef) and f.name=='main' for n in f.body if isinstance(n,ast.ClassDef) and n.name=='Watchdog')
        class Pub:
            def __init__(self):self.messages=[]
            def publish(self,m):self.messages.append(m)
        class Node:
            def __init__(self,*a):pass
            def create_publisher(self,*a):return Pub()
            def create_subscription(self,*a):return None
            def create_service(self,*a):return None
            def create_timer(self,*a,**kw):return None
        class Twist:
            def __init__(self):self.linear=types.SimpleNamespace(x=0.);self.angular=types.SimpleNamespace(z=0.)
        import json,time
        namespace=dict(Node=Node,MotionGate=MotionGate,StatusCadence=StatusCadence,Twist=Twist,String=lambda **kw:kw,Empty=object,Bool=object,SetBool=object,Clock=lambda **kw:None,ClockType=types.SimpleNamespace(STEADY_TIME=1),time=time,json=json,config={'safety':{'command_timeout_s':.5,'operator_timeout_s':.8,'max_linear_m_s':.1,'max_yaw_rad_s':.3},'driver_command_topic':'fixture_driver'})
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'actual-watchdog-fixture','exec'),namespace)
        node=namespace['Watchdog']()
        for i in range(50):
            with patch.object(time,'monotonic',return_value=i*.02):node.tick()
        self.assertEqual(len(node.output_pub.messages),50)
        self.assertLessEqual(len(node.status_pub.messages),10)
        self.assertGreaterEqual(len(node.status_pub.messages),8)
        node.gate.command((0.,0.),1.);node.gate.heartbeat(1.);self.assertTrue(node.gate.arm(1.))
        before=len(node.status_pub.messages)
        with patch.object(time,'monotonic',return_value=1.):node.tick()
        self.assertEqual(len(node.status_pub.messages),before+1)
