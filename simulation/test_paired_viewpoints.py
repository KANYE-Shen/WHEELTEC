import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import unittest
import paired_viewpoint_batch as batch
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

    def test_resume_preserves_log_only_failure_and_executes_next_trial(self):
        plan=paired_plan(['irregular_arc'],5)[:2]
        source={'sha256':{}}
        settings=dict(realism='on',task_timeout=300.,timeout=460.)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'plan.json').write_text(json.dumps(dict(plan=plan,source=source,settings=settings)))
            original=root/'000_irregular_arc_seed0_centroid-console.log'
            original.write_text('original interrupted launch evidence')
            def finish(command,**kwargs):
                run=Path(command[-1]);run.mkdir()
                (run/'result.json').write_text(json.dumps(dict(success=False,explorer={'state':'incomplete','goals':[]})))
                return subprocess.CompletedProcess(command,1)
            with patch('sys.argv',['paired_viewpoint_batch','--output',str(root),'--resume']), \
                 patch.object(batch,'paired_plan',return_value=plan), \
                 patch.object(batch,'source_manifest',return_value=source), \
                 patch.object(batch.subprocess,'run',side_effect=finish) as launch:
                batch.main()
            self.assertEqual(launch.call_count,1)
            self.assertTrue(launch.call_args.args[0][-1].endswith('001_irregular_arc_seed0_visibility'))
            self.assertEqual(original.read_text(),'original interrupted launch evidence')
            summary=json.loads((root/'summary.json').read_text())
            self.assertEqual(summary['executed_trials'],2)
            self.assertTrue(summary['complete'])
            self.assertFalse(summary['rows'][0]['success'])
            self.assertTrue(summary['rows'][0]['failures'])
            self.assertFalse((root/'000_irregular_arc_seed0_centroid').exists())

    def test_off_control_keeps_mode_equal_in_every_pair(self):
        plan=paired_plan(['irregular_arc','irregular_frame'],5,realism='off')
        self.assertTrue(all(x['realism']=='off' for x in plan))
        self.assertEqual(len(plan),20)
        with self.assertRaises(ValueError): paired_plan(['irregular_arc'],5,realism='invalid')

    def test_partial_summary_before_other_arm_runs_is_valid(self):
        cells=summarize([dict(scenario='irregular_arc',strategy='centroid',success=False)])
        self.assertEqual(len(cells),2)
        pending=next(c for c in cells if c['strategy']=='visibility')
        self.assertEqual(pending['trials'],0)
        self.assertIsNone(pending['success_rate'])
        self.assertEqual(pending['wilson_95'],(None,None))

    def test_missing_and_failed_trials_count_as_failures(self):
        rows=[dict(scenario='irregular_arc',strategy=s,success=False) for s in ('centroid','visibility') for _ in range(5)]
        for cell in summarize(rows):
            self.assertEqual(cell['trials'],5)
            self.assertEqual(cell['successes'],0)
            self.assertAlmostEqual(cell['wilson_95'][1],.4344824648)

if __name__=='__main__': unittest.main()
