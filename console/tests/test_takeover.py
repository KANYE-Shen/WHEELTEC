import unittest
from robot.safety import CommandSelector


class TakeoverTests(unittest.TestCase):
    def test_autonomy_is_forwarded_without_manual_messages(self):
        p=CommandSelector(.5);p.set_gear(2);p.select('autonomy')
        p.command('autonomy',(.08,.2),1.)
        self.assertEqual(p.output(1.1),(.08,.2))

    def test_manual_takeover_prevents_autonomous_commands_from_overwriting_wasd(self):
        p=CommandSelector(.5);p.set_gear(2);p.select('autonomy')
        p.command('autonomy',(.08,.2),1.)
        p.select('manual')
        self.assertEqual(p.output(1.1),(0.,0.))
        p.command('manual',(.03,-.1),1.2)
        p.command('autonomy',(.09,.3),1.3)
        self.assertEqual(p.output(1.4),(.03,-.1))

    def test_release_and_space_latch_hold_despite_new_autonomous_commands(self):
        for mode in ('manual','autonomy'):
            p=CommandSelector(.5);p.set_gear(2);p.select(mode)
            p.command(mode,(.05,.1),1.)
            p.select('hold')
            p.command('autonomy',(.1,.2),1.1)
            self.assertEqual(p.output(1.2),(0.,0.))

    def test_stale_manual_input_never_falls_back_to_autonomy_or_resumes(self):
        p=CommandSelector(.5);p.set_gear(2);p.select('manual')
        p.command('manual',(.05,0.),1.)
        p.command('autonomy',(.1,0.),1.49)
        self.assertEqual(p.output(1.51),(0.,0.))
        self.assertEqual(p.mode,'hold')
        p.command('manual',(.05,0.),1.6)
        p.command('autonomy',(.1,0.),1.6)
        self.assertEqual(p.output(1.61),(0.,0.))

    def test_switch_discards_previous_commands_and_bad_data_holds(self):
        p=CommandSelector(.5);p.set_gear(2);p.select('autonomy')
        p.command('autonomy',(.05,0.),1.)
        p.select('manual');p.select('autonomy')
        self.assertEqual(p.output(1.1),(0.,0.))
        p.command('autonomy',(float('nan'),0.),1.2)
        self.assertEqual(p.mode,'hold')
        self.assertEqual(p.output(1.3),(0.,0.))

    def test_invalid_mode_and_clock_fail_closed(self):
        p=CommandSelector(.5);p.set_gear(2);p.select('autonomy')
        with self.assertRaises(ValueError):p.select('anything')
        p.command('autonomy',(.05,0.),2.)
        self.assertEqual(p.output(1.),(0.,0.))
        self.assertEqual(p.mode,'hold')

class TakeoverReadinessTests(unittest.TestCase):
    def test_requires_acknowledged_source_hold_and_disarmed_final_watchdog(self):
        from console.backend.policy import takeover_blocker
        self.assertIsNone(takeover_blocker('hold',True,False))
        for mode,fresh,armed in [('autonomy',True,True),('manual',True,False),('hold',False,False),('hold',True,True),(None,True,False)]:
            with self.subTest(mode=mode,fresh=fresh,armed=armed):
                self.assertIsNotNone(takeover_blocker(mode,fresh,armed))
