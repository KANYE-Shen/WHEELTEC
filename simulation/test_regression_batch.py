import importlib
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))

class RegressionBatchTests(unittest.TestCase):
    def setUp(self):
        self.batch=importlib.import_module('regression_batch')
    def test_wilson_includes_zero_failures_and_missing_results(self):
        low,high=self.batch.wilson(0,5)
        self.assertAlmostEqual(low,0.)
        self.assertAlmostEqual(high,.4344824648)
        self.assertEqual(self.batch.wilson(0,0),(None,None))
        rows=[{'scenario':'baseline','spawn':0,'seed':i,'scale':1,'success':i==0} for i in range(5)]
        summary=self.batch.summarize(rows)[0]
        self.assertEqual(summary['trials'],5); self.assertEqual(summary['successes'],1)
    def test_seed_plan_is_complete_paired_and_stable(self):
        plan=self.batch.make_plan(['baseline'],[0],list(range(5)),[0,.5,1,2])
        self.assertEqual(len(plan),20)
        for seed in range(5):
            trials=[x for x in plan if x['seed']==seed]
            self.assertEqual(len({tuple(x['pose']) for x in trials}),1)
        self.assertEqual(plan,self.batch.make_plan(['baseline'],[0],list(range(5)),[0,.5,1,2]))
        self.assertGreater(len({tuple(x['pose']) for x in plan}),1)
    def test_world_uses_declared_perturbation_and_rejects_unsafe_pose(self):
        from scenarios import load_scenario,generate_world
        import tempfile,xml.etree.ElementTree as ET
        scene=load_scenario('baseline'); pose=self.batch.make_plan(['baseline'],[0],[0],[1])[0]['pose']
        with tempfile.TemporaryDirectory() as directory:
            p=generate_world(scene,0,Path(directory)/'world.sdf',pose_override=pose)
            actual=list(map(float,ET.parse(p).getroot().find('world/include/pose').text.split()))
            self.assertEqual(actual[:2],pose[:2]); self.assertEqual(actual[-1],pose[-1])
            with self.assertRaises(ValueError): generate_world(scene,0,Path(directory)/'bad.sdf',pose_override=[20,20,0])

if __name__=='__main__': unittest.main()
