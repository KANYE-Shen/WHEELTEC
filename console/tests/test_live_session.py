import copy,json,tempfile,unittest
from pathlib import Path
from robot.preflight import validate_runtime

class LiveSessionTests(unittest.TestCase):
 def fixture(self,folder):
  profile={'calibration_complete':False,'parameters':{'geometry':{'length_m':{'value':.30,'source':'measured','evidence':'user reported measurement'},'width_m':{'value':.25,'source':'measured','evidence':'user reported measurement'},'safety_margin_m':{'value':.1}}}}
  path=Path(folder)/'geometry.json';path.write_text(json.dumps(profile))
  return {'admission_protocol':'supervised-live-session-v1','operator_authorization':{'request':'directly enable manual and autonomous control','scope':['manual','autonomy']},'measured_kinematics':'differential','base_frame':'base_footprint','odom_frame':'odom_combined','scan_frame':'laser','scan_topic':'/scan','odom_topic':'/odom','driver_command_topic':'/console/driver_cmd_vel','driver_command_type':'geometry_msgs/msg/Twist','driver_command_expiry_s':.3,'calibration_file':str(path),'safety':{'max_linear_m_s':.1,'max_yaw_rad_s':.3,'operator_timeout_s':.8,'command_timeout_s':.5,'obstacle_margin_m':.1}}
 def test_explicit_live_session_keeps_incomplete_calibration_truthful(self):
  with tempfile.TemporaryDirectory() as folder:
   c=self.fixture(folder);self.assertIs(validate_runtime(c,3),c)
   self.assertFalse(json.loads(Path(c['calibration_file']).read_text())['calibration_complete'])
 def test_missing_authorization_or_unsafe_limits_are_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   source=self.fixture(folder)
   variants=[]
   c=copy.deepcopy(source);c['operator_authorization']={};variants.append(c)
   for key,value in [('max_linear_m_s',.2),('max_yaw_rad_s',.5),('operator_timeout_s',5.),('command_timeout_s',0)]:
    c=copy.deepcopy(source);c['safety'][key]=value;variants.append(c)
   c=copy.deepcopy(source);c['driver_command_expiry_s']=2.;variants.append(c)
   c=copy.deepcopy(source);c['driver_command_topic']='/safety/nav_cmd_vel';variants.append(c)
   for c in variants:
    with self.subTest(config=c),self.assertRaises(ValueError):validate_runtime(c,3)
 def test_existing_unconfigured_default_remains_rejected(self):
  with self.assertRaises(ValueError):validate_runtime(json.loads((Path(__file__).resolve().parents[2]/'robot/config/robot.json').read_text()),1)
