import unittest
from paired_active_scan_batch import paired_plan, summarize
class ActiveScanBatchTests(unittest.TestCase):
 def test_same_seed_start_and_config_are_shared_by_all_angles(self):
  plan=paired_plan(['irregular_arc','recess'],5)
  self.assertEqual(len(plan),40)
  for pair in range(10):
   rows=[r for r in plan if r['pair']==pair]
   self.assertEqual({r['angle'] for r in rows},{0.,90.,180.,360.})
   self.assertTrue(all(r['pose']==rows[0]['pose'] for r in rows))
 def test_failures_count_and_wilson_uses_all_rows(self):
  rows=[{'scenario':'recess','spawn':0,'angle':90.,'success':i==0,'first_goal':False} for i in range(5)]
  row=summarize(rows)[0]
  self.assertEqual(row['trials'],5);self.assertEqual(row['successes'],1)
  self.assertAlmostEqual(row['success_rate'],.2);self.assertEqual(row['first_goal_rate'],0.)
 def test_less_than_five_seeds_is_rejected(self):
  with self.assertRaises(ValueError):paired_plan(['recess'],4)
