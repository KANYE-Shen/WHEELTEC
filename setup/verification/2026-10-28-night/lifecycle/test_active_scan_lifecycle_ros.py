"""Synthetic maps/futures: action lifetime tests, no ROS publishers or robot."""
from concurrent.futures import Future
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'src/wheeltec_explore'))
from wheeltec_explore.node import Explorer
from wheeltec_explore.defaults import DEFAULTS
from wheeltec_explore.health import MapUnstableError

def finished(value):
 f=Future();f.set_result(value);return f

class ScanLifecycleTests(unittest.TestCase):
 def node(self,accepted=None,result=None):
  handle=NS(accepted=True,cancel_goal_async=Mock(return_value=finished(None)),
            get_result_async=Mock(return_value=result or finished(NS(status=4))))
  future=accepted if accepted is not None else finished(handle)
  node=NS(config=dict(DEFAULTS,active_scan_angle_deg=90.),report={},grid=lambda:None,
          ros_seconds=lambda:10.,started_ros=0.,map_updates=1,wait_reason=None,
          status=Mock(),position=Mock(return_value=(0.,0.,0.)),wait=Mock(return_value=True),
          spin_action=NS(server_is_ready=lambda:True,send_goal_async=Mock(return_value=future)),
          active_goal=None,active_result=None,require_health=lambda:True,cancel_active=Mock(return_value=True))
  return node,handle,future

 def observe(self,node,plan=None):
  selected=plan or dict(safe=True,angle_rad=1.57,reason='new_direction_opportunity')
  with patch('wheeltec_explore.node.choose_scan',return_value=selected),patch('wheeltec_explore.node.rotation_clearance',return_value={'safe':True}),patch('wheeltec_explore.node.rclpy.ok',return_value=True),patch('wheeltec_explore.node.rclpy.spin_once'):
   return Explorer.active_observe(node,(0.,0.,0.),True)

 def test_unknown_envelope_never_sends_spin(self):
  node,_,_=self.node()
  self.assertEqual(self.observe(node,dict(safe=False,angle_rad=None,reason='unknown_swept_space')),(False,'active_scan_clearance_unproven'))
  node.spin_action.send_goal_async.assert_not_called()

 def test_success_clears_live_handle(self):
  node,_,_=self.node()
  self.assertEqual(self.observe(node),(True,'succeeded'))
  self.assertIsNone(node.active_goal)
  self.assertTrue(node.report['active_scans'][0]['motion_requested'])

 def test_rejection_is_not_motion_success(self):
  node,handle,_=self.node();handle.accepted=False
  self.assertEqual(self.observe(node),(False,'active_scan_rejected'))

 def test_tf_loss_cancels_active_action(self):
  pending=Future();node,_,_=self.node(result=pending)
  node.position.side_effect=[(0.,0.,0.),None]
  self.assertEqual(self.observe(node),(False,'active_scan_tf_unavailable'))
  node.cancel_active.assert_called_once()

 def test_response_timeout_cancels_late_acceptance(self):
  pending=Future();node,handle,_=self.node(accepted=pending)
  node.wait.side_effect=[True,False]
  with self.assertRaises(RuntimeError):self.observe(node)
  pending.set_result(handle)
  handle.cancel_goal_async.assert_called_once()

 def test_health_exception_during_pending_response_cancels_late_acceptance(self):
  pending=Future();node,handle,_=self.node(accepted=pending)
  node.wait.side_effect=[True,MapUnstableError('scan_timeout')]
  with self.assertRaises(MapUnstableError):self.observe(node)
  pending.set_result(handle)
  handle.cancel_goal_async.assert_called_once()

if __name__=='__main__':unittest.main(verbosity=2)

