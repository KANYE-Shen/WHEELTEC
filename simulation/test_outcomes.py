import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_exploration as runner

class OutcomeTests(unittest.TestCase):
    def test_launch_child_sigkill_is_not_a_clean_shutdown(self):
        self.assertFalse(runner.launch_shutdown_abnormal('[INFO] process has finished cleanly'))
        self.assertTrue(runner.launch_shutdown_abnormal("sending signal 'SIGKILL' to process[lifecycle_manager-14]"))
        self.assertTrue(runner.launch_shutdown_abnormal('process has died [pid 3, exit code -9, cmd lifecycle_manager]'))

    def test_exit_status_drain_uses_wall_deadline_not_twenty_callbacks(self):
        ticks=[0]
        def spin(timeout):
            ticks[0]+=1
        self.assertTrue(runner.drain_terminal_status(lambda:ticks[0]>=25,spin,
                          lambda:ticks[0]*.01,timeout=1.))
        self.assertEqual(ticks[0],25)

    def test_missing_exit_status_drain_is_bounded_and_not_success(self):
        ticks=[0]
        def spin(timeout):
            ticks[0]+=1
        self.assertFalse(runner.drain_terminal_status(lambda:False,spin,
                           lambda:ticks[0]*.1,timeout=1.))
        self.assertLessEqual(ticks[0],11)

    def test_viewpoint_strategy_is_explicit_and_recordable(self):
        self.assertEqual(runner.parse_arguments([]).viewpoint_strategy,'centroid')
        self.assertEqual(runner.parse_arguments(['--viewpoint-strategy','visibility']).viewpoint_strategy,'visibility')

    def test_rc2_requires_a_confirmed_terminal_and_clean_shutdown(self):
        self.assertTrue(hasattr(runner,'shutdown_abnormal'))
        clean={'returncode':2,'forced_kill':False,'remaining_live_group_members':[]}
        self.assertFalse(runner.shutdown_abnormal('explorer',clean,{'state':'incomplete'}))
        self.assertTrue(runner.shutdown_abnormal('explorer',clean,{}))
        self.assertTrue(runner.shutdown_abnormal('launch',clean,{'state':'incomplete'}))
        self.assertTrue(runner.shutdown_abnormal('explorer',{**clean,'forced_kill':True},{'state':'incomplete'}))
        self.assertTrue(runner.shutdown_abnormal('explorer',{**clean,'remaining_live_group_members':[4]},{'state':'incomplete'}))
        self.assertTrue(runner.shutdown_abnormal('explorer',{**clean,'returncode':1},{'state':'incomplete'}))

if __name__=='__main__': unittest.main()
