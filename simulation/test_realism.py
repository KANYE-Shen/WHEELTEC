import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    import realism
except ImportError:
    realism=None

class RealismTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(realism,'Realism layer is missing')
        self.profile=realism.load_profile()

    def test_seeded_scan_is_repeatable_and_zero_scale_preserves_valid_values(self):
        a=realism.ScanModel(self.profile,seed=42,scale=1)
        b=realism.ScanModel(self.profile,seed=42,scale=1)
        x,stamp=a.apply([2.]*540,10.,.08,8.)
        y,other=b.apply([2.]*540,10.,.08,8.)
        self.assertEqual(x,y); self.assertEqual(stamp,other)
        self.assertNotEqual(x,[2.]*540)
        z,t=realism.ScanModel(self.profile,seed=42,scale=0).apply([2.]*540,10.,.08,8.)
        self.assertEqual(z,[2.]*540); self.assertEqual(t,10.)
        self.assertTrue(all(math.isinf(v) or .08 <= v <= 8. for v in x))

    def test_odom_zero_scale_matches_raw_and_seeded_errors_accumulate(self):
        zero=realism.OdomModel(self.profile,seed=3,scale=0)
        noisy=realism.OdomModel(self.profile,seed=3,scale=1)
        repeat=realism.OdomModel(self.profile,seed=3,scale=1)
        for i in range(101):
            raw=(i*.02,0.,i*.01)
            ideal=zero.update(raw,i*.1+1)
            a=noisy.update(raw,i*.1+1); b=repeat.update(raw,i*.1+1)
            self.assertEqual(a,b)
        for expected,actual in zip(raw,ideal['pose']): self.assertAlmostEqual(expected,actual,places=9)
        self.assertGreater(math.dist(raw[:2],a['pose'][:2]),.001)
        self.assertIsNone(zero.update(raw,10.))

    def test_actuator_delays_limits_brakes_and_never_replays_stale_commands(self):
        model=realism.ActuatorModel(self.profile,seed=2,scale=1)
        model.submit((.2,0.),1.)
        self.assertEqual(model.update(1.01), (0.,0.))
        active=model.update(1.2)
        self.assertGreater(active[0],0.); self.assertLessEqual(active[0],.2)
        stopped=model.update(2.)
        self.assertEqual(stopped,(0.,0.))
        self.assertEqual(model.update(3.),(0.,0.))
        model.submit((.001,0.),3.1)
        self.assertEqual(model.update(3.3),(0.,0.))

    def test_configuration_requires_sources_and_assumed_intervals(self):
        p=copy.deepcopy(self.profile)
        p['parameters']['laser']['noise_sigma_m']['source']='measured'
        with self.assertRaises(ValueError): realism.validate_profile(p)
        p=copy.deepcopy(self.profile)
        p['parameters']['laser']['noise_sigma_m'].pop('interval')
        with self.assertRaises(ValueError): realism.validate_profile(p)
        with self.assertRaises(ValueError): realism.ScanModel(self.profile,seed=0,scale=float('nan'))

    def test_generated_model_bridge_nav_and_explorer_share_geometry(self):
        root=Path(__file__).resolve().parent
        original=(root/'models/wheeltec_reference/model.sdf').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            assets=realism.prepare_assets(root/'worlds/room_25m2.sdf',Path(directory)/'assets',self.profile,seed=4,scale=1)
            with self.assertRaises(FileExistsError):
                realism.prepare_assets(root/'worlds/room_25m2.sdf',Path(directory)/'assets',self.profile,seed=4,scale=1)
            model=ET.parse(assets['model']).getroot().find('model')
            self.assertEqual(model.find("plugin[@name='gz::sim::systems::DiffDrive']/odom_topic").text,'/simulation/raw_odom')
            self.assertEqual(model.find("plugin[@name='gz::sim::systems::DiffDrive']/tf_topic").text,'/simulation/raw_tf')
            import yaml
            bridge=yaml.safe_load(Path(assets['bridge']).read_text())
            self.assertNotIn('/tf',[x['ros_topic_name'] for x in bridge])
            self.assertIn('/simulation/ground_truth',[x['ros_topic_name'] for x in bridge])
            slam=yaml.safe_load(Path(assets['slam']).read_text())
            self.assertIs(type(slam['slam_toolbox']['ros__parameters']['max_laser_range']),float)
            nav=yaml.safe_load(Path(assets['nav2']).read_text())
            self.assertIs(type(nav['amcl']['ros__parameters']['laser_max_range']),float)
            footprint=nav['local_costmap']['local_costmap']['ros__parameters']['footprint']
            self.assertEqual(footprint,nav['global_costmap']['global_costmap']['ros__parameters']['footprint'])
            self.assertAlmostEqual(assets['robot_radius'],.35)
        self.assertEqual(original,(root/'models/wheeltec_reference/model.sdf').read_bytes())

if __name__=='__main__': unittest.main()
