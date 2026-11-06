import sys,time,threading,tempfile,unittest,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src/wheeltec_explore')]
from console.target.tasks import TaskController
class Process:
 def __init__(self):self.signals=[];self.exit=None
 def poll(self):return self.exit
 def send_signal(self,s):self.signals.append(s)
class StagedTests(unittest.TestCase):
 def wait(self,p):
  end=time.monotonic()+1
  while not p() and time.monotonic()<end:time.sleep(.003)
  self.assertTrue(p())
 def build(self,prepare,activate=lambda current:None):
  self.calls=[];self.p=Process()
  def spawn():self.calls.append('spawn');return self.p
  return TaskController(lambda:None,activate,spawn,lambda:self.calls.append('halt'),prepare=prepare,release=lambda p:self.calls.append('release'))
 def test_prepare_finishes_while_held_before_arm_then_release(self):
  def prepare(p,current):self.calls.append('prepare')
  c=self.build(prepare,lambda current:self.calls.append('activate'));c.start();self.wait(lambda:c.mode=='autonomous')
  self.assertEqual(self.calls,['halt','spawn','prepare','activate','release'])
 def test_space_during_prepare_signals_owned_child_and_never_arms(self):
  enter=threading.Event();finish=threading.Event()
  def prepare(p,current):enter.set();finish.wait(.5)
  c=self.build(prepare,lambda current:self.calls.append('activate'));c.start();self.assertTrue(enter.wait(.5));c.remote();finish.set();time.sleep(.02)
  self.assertEqual(c.mode,'remote');self.assertEqual(len(self.p.signals),1);self.assertNotIn('activate',self.calls);self.assertNotIn('release',self.calls)
 def test_prepare_failure_halts_and_signals_child(self):
  def prepare(p,current):raise ValueError('not ready')
  c=self.build(prepare);c.start();self.wait(lambda:c.mode=='remote');self.assertEqual(c.error,'not ready');self.assertEqual(len(self.p.signals),1)
 def test_space_during_activation_never_releases_prepared_child(self):
  enter=threading.Event();finish=threading.Event()
  def activate(current):enter.set();finish.wait(.5)
  c=self.build(lambda p,current:None,activate);c.start();self.assertTrue(enter.wait(.5));c.remote();finish.set();time.sleep(.02)
  self.assertNotIn('release',self.calls);self.assertEqual(len(self.p.signals),1)
 def test_child_exit_while_preparing_never_arms(self):
  def prepare(p,current):p.exit=2
  c=self.build(prepare,lambda current:self.calls.append('activate'));c.start();self.wait(lambda:c.mode=='remote');self.assertNotIn('activate',self.calls)
class GateTests(unittest.TestCase):
 def test_legacy_entry_without_console_gate_does_not_wait(self):
  from wheeltec_explore.startup import wait_for_console_start
  wait_for_console_start(lambda:self.fail('legacy entry should not spin'),environment={})
 def test_ready_is_announced_but_navigation_waits_for_explicit_release(self):
  from wheeltec_explore.startup import wait_for_console_start
  with tempfile.TemporaryDirectory() as d:
   gate=Path(d);calls=[]
   def spin():
    self.assertTrue((gate/'ready.json').is_file());calls.append(1)
    if len(calls)==3:(gate/'go').write_text('start')
   wait_for_console_start(spin,environment={'WHEELTEC_CONSOLE_START_GATE':d});self.assertEqual(len(calls),3)
 def test_missing_release_times_out_closed(self):
  from wheeltec_explore.startup import wait_for_console_start
  with tempfile.TemporaryDirectory() as d:
   now=[0.]
   def spin():now[0]+=.1
   with self.assertRaisesRegex(RuntimeError,'release'):
    wait_for_console_start(spin,environment={'WHEELTEC_CONSOLE_START_GATE':d},timeout=.25,clock=lambda:now[0])

class ActualMainTests(unittest.TestCase):
 def exercise(self, gated=True, interrupt=False):
  import ast
  from types import SimpleNamespace as NS
  from unittest.mock import patch
  from wheeltec_explore.startup import wait_for_console_start
  source=(ROOT/'src/wheeltec_explore/wheeltec_explore/node.py').read_text(encoding='utf8')
  fn=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=='main')
  with tempfile.TemporaryDirectory() as d:
   gate=Path(d);calls=[];spins=[]
   def spin(node,timeout_sec):
    calls.append('spin');spins.append(1)
    self.assertTrue((gate/'ready.json').is_file())
    if interrupt:raise KeyboardInterrupt()
    if len(spins)==2:(gate/'go').write_text('start')
   def run():
    if gated:self.assertTrue((gate/'go').is_file())
    calls.append('run');return 0
   node=NS(latest_map=object(),position=lambda:(0,0,0),last_scan_ros=1.,ros_seconds=lambda:1.,
    config={'scan_max_age':1.,'initialization_timeout':5.},nav=NS(server_is_ready=lambda:True),
    wait=lambda p,t:calls.append('warm') or p(),run=run,cancel_active=lambda:calls.append('cancel'),
    status=lambda *a,**kw:calls.append('status'),destroy_node=lambda:calls.append('destroy'))
   env={'rclpy':NS(init=lambda **kw:None,ok=lambda:True,shutdown=lambda:None,spin_once=spin),
    'SignalHandlerOptions':NS(NO=0),'Explorer':lambda:node,'os':os,
    'observation_fresh':lambda *a:True,'wait_for_console_start':wait_for_console_start,'MapUnstableError':type('HealthError',(Exception,),{})}
   exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual_explorer_main','exec'),env)
   with patch.dict(os.environ,{'WHEELTEC_CONSOLE_START_GATE':d if gated else ''}):code=env['main']()
   return code,calls
 def test_actual_console_main_cannot_run_before_release(self):
  code,calls=self.exercise();self.assertEqual(code,0);self.assertLess(calls.index('warm'),calls.index('spin'));self.assertLess(calls.index('spin'),calls.index('run'))
 def test_actual_main_space_during_barrier_never_runs_algorithm(self):
  code,calls=self.exercise(interrupt=True);self.assertEqual(code,130);self.assertNotIn('run',calls);self.assertIn('cancel',calls)
 def test_actual_legacy_main_preserves_entry_without_barrier(self):
  code,calls=self.exercise(gated=False);self.assertEqual(code,0);self.assertNotIn('warm',calls);self.assertNotIn('spin',calls)

if __name__=='__main__':unittest.main()
