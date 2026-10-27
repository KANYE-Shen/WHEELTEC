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
        config={'hardware_verified':True,'measured_kinematics':'differential','base_frame':'base','odom_frame':'odom','scan_frame':'laser','scan_topic':'/scan','odom_topic':'/odom','driver_command_topic':'/driver','driver_command_type':'geometry_msgs/msg/Twist','calibration_file':'unit-test-calibration','approval_record':'unit-test-approval','driver_timeout_verified_s':.2,'measured_braking_distance_m':None,'safety':{'operator_timeout_s':1.,'command_timeout_s':.5,'max_linear_m_s':.1,'max_yaw_rad_s':.3,'obstacle_margin_m':.1}}
        # In-memory test fixture; no gate approval file is created.
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',side_effect=[json.dumps(profile),'通过关卡1']):
            self.assertIs(validate(config,required_gate=1),config)
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',return_value=json.dumps(profile)):
            with self.assertRaises(ValueError): validate(config,required_gate=4)

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
