import unittest
from console.backend.policy import manual_command_blocker, require_control_epoch

class ManualWaitTests(unittest.TestCase):
 def test_zero_renews_while_waiting_but_cannot_authorize_motion(self):
  self.assertIsNone(manual_command_blocker('hold',False,0.,0.))
  self.assertIsNotNone(manual_command_blocker('hold',False,.03,0.))
  self.assertIsNotNone(manual_command_blocker('manual',False,.03,0.))
  self.assertIsNone(manual_command_blocker('manual',True,.03,0.))
 def test_space_generation_invalidates_queued_claims_and_commands(self):
  require_control_epoch(7,7)
  with self.assertRaisesRegex(ValueError,'stale_control_epoch'):require_control_epoch(7,8)
 def test_missing_or_invalid_generation_is_rejected(self):
  for epoch in (None,False,'8',7,9):
   with self.subTest(epoch=epoch),self.assertRaises(ValueError):require_control_epoch(epoch,8)
