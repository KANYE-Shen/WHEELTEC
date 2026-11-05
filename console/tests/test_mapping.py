import copy,tempfile,unittest,threading,time
from pathlib import Path
from console.target.mapping import fresh_parameters, mapping_command, MapReset

class MappingResetTests(unittest.TestCase):
 def test_fresh_reset_removes_restore_state_without_mutating_old_parameters(self):
  old={'slam_toolbox':{'ros__parameters':{'map_file_name':'old','map_start_pose':[1,2,3],'map_start_at_dock':True,'base_frame':'base_footprint','minimum_travel_distance':0.}}}
  before=copy.deepcopy(old);new=fresh_parameters(old)
  self.assertEqual(old,before)
  self.assertEqual(new['slam_toolbox']['ros__parameters'],{'base_frame':'base_footprint','minimum_travel_distance':0.})
 def test_rewrite_only_parameters_preserves_owned_command(self):
  command='source /opt/ros/humble/setup.bash && exec /owned/motion_gated_slam --ros-args --params-file /old/slam.yaml'
  self.assertEqual(mapping_command(command,Path('/new/slam.yaml')),command.replace('/old/slam.yaml','/new/slam.yaml'))
 def test_refuse_non_mapping_and_ambiguous_command(self):
  for command in ('exec /bin/true --params-file /old', 'exec /owned/motion_gated_slam --params-file /one --params-file /two'):
   with self.assertRaises(ValueError):mapping_command(command,Path('/new'))
 def test_reset_halts_before_worker_and_serializes_requests(self):
  events=[];started=threading.Event();release=threading.Event()
  def work():
   events.append('work');started.set();release.wait(2.)
  reset=MapReset(lambda:events.append('halt'),work)
  reset.start();self.assertTrue(started.wait(1.));self.assertEqual(events,['halt','work'])
  with self.assertRaises(ValueError):reset.start()
  release.set();deadline=time.monotonic()+1.
  while reset.snapshot()['busy'] and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(reset.snapshot(),{'busy':False,'error':'','sequence':1})
 def test_failed_reset_stays_stopped_and_exposes_error(self):
  halted=[]
  def work():raise ValueError('archive failed')
  reset=MapReset(lambda:halted.append(True),work);reset.start();deadline=time.monotonic()+1.
  while reset.snapshot()['busy'] and time.monotonic()<deadline:time.sleep(.005)
  self.assertEqual(halted,[True]);self.assertEqual(reset.snapshot()['error'],'archive failed')
if __name__=='__main__':unittest.main()
