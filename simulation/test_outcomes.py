import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_exploration as runner

class OutcomeTests(unittest.TestCase):
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
