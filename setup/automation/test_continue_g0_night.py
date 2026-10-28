import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('night',Path(__file__).with_name('continue_g0_night.py'))
class NightGuardTests(unittest.TestCase):
 def test_only_quota_failure_resumes_unfinished_idle_thread(self):
  m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  for completed,locked,quota in [(True,False,True),(False,True,True),(False,False,False)]:
   self.assertFalse(m.should_resume(completed,locked,quota))
  self.assertTrue(m.should_resume(False,False,True))
 def test_task_text_containing_quota_does_not_count_as_error(self):
  m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertFalse(m.quota_failure([{'type':'event_msg','payload':{'type':'user_message','message':'quota exhausted'}}]))
  self.assertTrue(m.quota_failure([{'type':'event_msg','payload':{'type':'error','message':"You've hit your usage limit"}}]))
  self.assertFalse(m.quota_failure([{'type':'error','message':'usage limit reached'},{'type':'event_msg','payload':{'type':'task_started'}}]))
