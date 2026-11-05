"""Exercise adapter error/stop paths without ROS or a robot connection."""
import ast,json,math,sys,tempfile,threading,unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace as NS

REPO=Path(__file__).resolve().parents[2]
if not (REPO/'console/target/adapter.py').exists():REPO=Path('D:/虚拟c盘/WHEELTEC')
sys.path.insert(0,str(REPO))
from console.target.data import tf_chain_fresh
try:
 from console.target.diagnostics import tf_failure_context,write_task_stop
except ImportError:
 tf_failure_context=write_task_stop=None

def methods(node,env):
 tree=ast.parse((REPO/'console/target/adapter.py').read_text(encoding='utf-8'))
 cls=next(x for x in ast.walk(tree) if isinstance(x,ast.ClassDef) and x.name=='Adapter')
 selected=[x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name in ('transform','tf_failure','tf_received','record_task_stop','tick')]
 exec(compile(ast.Module(body=selected,type_ignores=[]),'actual_adapter_methods','exec'),env)
 for method in selected:setattr(node,method.name,env[method.name].__get__(node))

def base_node():
 n=NS(lock=threading.RLock(),tf_edges={('odom_combined','base_footprint'):(9.99,False)},
      tf_history={('odom_combined','base_footprint'):deque([(9.94,8.94),(9.99,8.99)],maxlen=4)},
      tf_error=None,get_clock=lambda:NS(now=lambda:NS(nanoseconds=10_000_000_000)))
 t=NS(header=NS(stamp=NS(sec=8,nanosec=990_000_000)),transform=NS(translation=NS(x=0.,y=0.),rotation=NS(x=0.,y=0.,z=0.,w=1.)))
 n.tf=NS(lookup_transform=lambda *a:t)
 env={'time':NS(monotonic=lambda:10.,time=lambda:100.),'math':math,'json':json,'deque':deque,
      'rclpy':NS(time=NS(Time=lambda **kw:None)),'tf_chain_fresh':tf_chain_fresh,
      'tf_failure_context':tf_failure_context,'write_task_stop':write_task_stop,
      'real_config':{'safety':{}},'args':NS(kind='robot')}
 methods(n,env)
 return n,env

class StopDiagnosticsTests(unittest.TestCase):
 def test_actual_transform_records_old_source_despite_recent_receipt(self):
  n,_=base_node()
  self.assertIsNone(n.transform('odom_combined','base_footprint'))
  self.assertEqual(n.tf_error['reason'],'source_age')
  self.assertAlmostEqual(n.tf_error['age'],1.01)
  self.assertIn('source_stamp',n.tf_error)
  edge=n.tf_error['tf_chain'][0]
  self.assertAlmostEqual(edge['source_age_s'],1.01)
  self.assertAlmostEqual(edge['receipt_age_s'],.01)
  self.assertAlmostEqual(edge['source_interval_s'],.05)

 def test_actual_transform_still_rejects_missing_or_expired_tf(self):
  n,_=base_node();n.tf_edges.clear()
  self.assertIsNone(n.transform('odom_combined','base_footprint'))
  self.assertEqual(n.tf_error['reason'],'receipt_stale_or_missing')
  self.assertIn('tf_chain',n.tf_error)
  n.tf_edges[('odom_combined','base_footprint')]=(8.,False)
  self.assertIsNone(n.transform('odom_combined','base_footprint'))
  self.assertEqual(n.tf_error['reason'],'receipt_stale_or_missing')

 def test_fresh_and_static_transforms_keep_their_existing_contract(self):
  n,_=base_node()
  n.tf.lookup_transform=lambda *a:NS(header=NS(stamp=NS(sec=10,nanosec=0)),transform=NS(translation=NS(x=1.,y=2.),rotation=NS(x=0.,y=0.,z=0.,w=1.)))
  self.assertEqual(n.transform('odom_combined','base_footprint')['x'],1.)
  n.tf_edges={('base_footprint','laser'):(1.,True)}
  n.tf.lookup_transform=lambda *a:NS(header=NS(stamp=NS(sec=0,nanosec=0)),transform=NS(translation=NS(x=0.,y=0.),rotation=NS(x=0.,y=0.,z=0.,w=1.)))
  self.assertEqual(n.transform('base_footprint','laser')['age'],0.)

 def test_actual_receipt_history_is_bounded_and_keeps_source_stamps(self):
  n,_=base_node();n.tf_history={};n.stamp=lambda t:t.source_stamp
  for i in range(6):n.tf_received(NS(header=NS(frame_id='odom_combined'),child_frame_id='base_footprint',source_stamp=float(i)),False)
  self.assertTrue(hasattr(n,'tf_history'))
  self.assertIn(('odom_combined','base_footprint'),n.tf_history)
  history=n.tf_history[('odom_combined','base_footprint')]
  self.assertEqual([stamp for _,stamp in history],[2.,3.,4.,5.])

 def test_chain_context_separates_static_and_old_dynamic_edges(self):
  self.assertIsNotNone(tf_failure_context)
  edges={('map','odom'):(9.98,False),('odom','base'):(9.99,False),('base','laser'):(1.,True)}
  history={('map','odom'):[(9.98,10.1)],('odom','base'):[(9.99,8.99)],('base','laser'):[(1.,0.)]}
  result=tf_failure_context(edges,history,'map','laser',10.,10.)
  self.assertTrue(result['tf_chain_found'])
  self.assertEqual(len(result['tf_chain']),3)
  self.assertIsNone(result['tf_chain'][-1]['source_age_s'])
  self.assertAlmostEqual(result['tf_chain'][1]['source_age_s'],1.01)

 def test_repeated_source_does_not_masquerade_as_source_progress(self):
  self.assertIsNotNone(tf_failure_context)
  result=tf_failure_context({('odom','base'):(9.99,False)},
    {('odom','base'):[(9.8,8.99),(9.99,8.99)]},'odom','base',10.,10.)
  self.assertEqual(result['tf_chain'][0]['source_interval_s'],0.)
  self.assertAlmostEqual(result['tf_chain'][0]['receipt_interval_s'],.19)

 def run_stop(self,folder,fail_write=False):
  n,env=base_node();order=[]
  n.allowed=True;n.lease=NS(owner=None,reason='operator_hold',output=lambda now:(0.,0.))
  n.handshake=NS(ready=False);n.motion=NS(stop=lambda reason:None,output=lambda now:(0.,0.))
  n.tasks=NS(mode='autonomous');n.tasks.remote=lambda reason:order.append('halt') or setattr(n.tasks,'mode','remote')
  n.blockers=lambda:'tf_stale';n.robot_status={'armed':True,'reason':'armed','timeout_detail':None}
  n.tf_error={'target':'odom_combined','source':'base_footprint','reason':'source_age','age':1.01,'at':100.}
  n.logs=deque(maxlen=400);n.seq=0;n.latest={};n.received={'odom':9.99};n.stamps={'odom':9.98}
  n.selection_mode='autonomy';n.task_run_dir=folder;n.requested=(0.,0.);n.actual=(0.,0.)
  n.get_logger=lambda:NS(warning=lambda text:order.append('write_failed'))
  n.pub=NS(publish=lambda msg:self.fail('unexpected local command publish'))
  env['Twist']=lambda:NS(linear=NS(x=0.),angular=NS(z=0.))
  def write(folder,data):
   order.append('write')
   if fail_write:raise OSError('disk full')
   self.assertIsNotNone(write_task_stop)
   return write_task_stop(folder,data)
  env['write_task_stop']=write
  n.tick()
  return n,order

 def test_actual_tick_persists_stop_after_halt_and_survives_log_ring_wrap(self):
  with tempfile.TemporaryDirectory() as folder:
   n,order=self.run_stop(Path(folder))
   self.assertEqual(order[:2],['halt','write'])
   n.logs.extend({'name':'other'} for _ in range(500))
   path=Path(folder)/'console-stop.json'
   self.assertTrue(path.exists())
   data=json.loads(path.read_text(encoding='utf-8'))
   self.assertEqual(data['tf_error']['source'],'base_footprint')
   self.assertEqual(data['watchdog']['reason'],'armed')
   self.assertIn('source_age',data['message'])

 def test_diagnostic_disk_failure_does_not_undo_safety_stop(self):
  with tempfile.TemporaryDirectory() as folder:
   n,order=self.run_stop(Path(folder),fail_write=True)
   self.assertEqual(n.tasks.mode,'remote')
   self.assertEqual(order,['halt','write','write_failed'])

if __name__=='__main__':unittest.main()
