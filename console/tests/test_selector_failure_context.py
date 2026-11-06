"""Exercise the actual safety blocker; no ROS connection or control output."""
import ast,unittest
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[2]
def bind(n,clock):
 tree=ast.parse((ROOT/'console/target/adapter.py').read_text(encoding='utf8'))
 cls=next(x for x in ast.walk(tree) if isinstance(x,ast.ClassDef) and x.name=='Adapter')
 method=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='blockers')
 env={'time':NS(monotonic=clock),'real_config':{'odom_frame':'odom','driver_command_topic':'/driver'},'args':NS(base_frame='base')}
 exec(compile(ast.Module(body=[method],type_ignores=[]),'actual_blocker','exec'),env)
 n.blockers=env['blockers'].__get__(n)
class SelectorEvidenceTests(unittest.TestCase):
 def node(self,age,ready=True,delay=0.):
  now=[10.]
  def publishers(topic):
   if topic=='/manual':now[0]+=delay
   return [NS(node_name={'/manual':'adapter','/safety/nav_cmd_vel':'wheeltec_command_selector','/driver':'wheeltec_watchdog'}[topic])]
  n=NS(allowed=True,scan_frame="laser",fresh=lambda key:True,transform=lambda *a:True,
   command_topic='/manual',get_publishers_info_by_topic=publishers,selection_time=10.-age,
   autonomy_source=NS(service_is_ready=lambda:ready),robot_status_time=10.,arm=NS(service_is_ready=lambda:True))
  bind(n,lambda:now[0]);return n
 def test_stale_status_records_age_separately_from_ready_service(self):
  n=self.node(.6);self.assertEqual(n.blockers(),'command_selector_unavailable')
  self.assertAlmostEqual(n.selector_check['receipt_age_s'],.6);self.assertTrue(n.selector_check['service_ready'])
 def test_missing_service_with_fresh_status_is_distinguishable(self):
  n=self.node(.05,False);self.assertEqual(n.blockers(),'command_selector_unavailable')
  self.assertFalse(n.selector_check['service_ready']);self.assertAlmostEqual(n.selector_check['receipt_age_s'],.05)
 def test_blocking_check_time_is_distinct_from_stale_at_entry(self):
  n=self.node(.05,delay=.6);self.assertEqual(n.blockers(),'command_selector_unavailable')
  self.assertAlmostEqual(n.selector_check['entry_receipt_age_s'],.05)
  self.assertAlmostEqual(n.selector_check['check_elapsed_s'],.6)
  self.assertAlmostEqual(n.selector_check['receipt_age_s'],.65)
 def test_healthy_checks_still_pass_and_timeout_is_not_relaxed(self):
  self.assertIsNone(self.node(.05).blockers())
  self.assertEqual(self.node(.500001).blockers(),'command_selector_unavailable')
if __name__=='__main__':unittest.main()
