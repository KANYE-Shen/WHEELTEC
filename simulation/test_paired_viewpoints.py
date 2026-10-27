import unittest
from paired_viewpoint_batch import paired_plan,summarize

class PairedTests(unittest.TestCase):
    def test_pairs_change_only_strategy_and_keep_all_seeds(self):
        plan=paired_plan(['irregular_arc','irregular_frame'],5)
        self.assertEqual(len(plan),20)
        for i in range(0,len(plan),2):
            a,b=(dict(plan[i]),dict(plan[i+1]))
            self.assertNotEqual(a.pop('strategy'),b.pop('strategy'))
            self.assertEqual(a,b)
        with self.assertRaises(ValueError): paired_plan(['irregular_arc'],4)

    def test_missing_and_failed_trials_count_as_failures(self):
        rows=[dict(scenario='irregular_arc',strategy=s,success=False) for s in ('centroid','visibility') for _ in range(5)]
        for cell in summarize(rows):
            self.assertEqual(cell['trials'],5)
            self.assertEqual(cell['successes'],0)
            self.assertAlmostEqual(cell['wilson_95'][1],.4344824648)

if __name__=='__main__': unittest.main()
