import json
from pathlib import Path
import tempfile
import unittest
from collect_results import run_summary

class CollectorTests(unittest.TestCase):
    def audit(self,terminal,code=2,forced=False,launch_log=''):
        data=dict(functional_success=True,success=True,scenario='synthetic',seed=0,realism_mode='on',source={},explorer=terminal,
            shutdown={'explorer':dict(returncode=code,forced_kill=forced,remaining_live_group_members=[])})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.json';path.write_text(json.dumps(data))
            path.with_name('launch.log').write_text(launch_log)
            return run_summary(path)

    def test_rc2_without_confirmed_terminal_is_abnormal_even_when_reaped(self):
        row=self.audit({})
        self.assertFalse(row['clean_shutdown'])
        self.assertTrue(row['cleanup_complete'])

    def test_nested_launcher_sigkill_is_not_hidden_by_zero_wrapper_return(self):
        row=self.audit({'state':'incomplete'},code=0,launch_log="sending signal 'SIGKILL' to process[lifecycle_manager-14]\n")
        self.assertFalse(row['clean_shutdown'])
        self.assertFalse(row['strict_functional_success'])
        self.assertTrue(row['functional_success'])
        self.assertFalse(row['cleanup_complete'])
        self.assertTrue(row['nested_sigkill_detected'])
        self.assertTrue(row['no_live_group_members'])

    def test_confirmed_incomplete_rc2_is_normal_but_forced_kill_is_not(self):
        self.assertTrue(self.audit({'state':'incomplete'})['clean_shutdown'])
        self.assertTrue(self.audit({'state':'completed'},code=0)['strict_functional_success'])
        row=self.audit({'state':'incomplete'},forced=True)
        self.assertFalse(row['clean_shutdown'])
        self.assertFalse(row['cleanup_complete'])

if __name__=='__main__':unittest.main()
