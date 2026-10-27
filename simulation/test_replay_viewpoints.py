import unittest
from replay_viewpoints import snapshot

class ReplayTests(unittest.TestCase):
    def test_snapshot_does_not_skip_a_stale_frame_for_a_better_one(self):
        grid={'width':2,'height':2,'resolution':.1,'origin':[0,0,0],'data':[0]*4}
        frame=dict(t=5.,pose=[.1,.1,0],pose_age_s=.2,scan_age_s=.1,map=0)
        doc=dict(maps=[grid],frames=[dict(frame,t=0.),dict(frame,pose=None),dict(frame,t=6.)])
        self.assertEqual(snapshot(doc,5.)[1],'missing_or_stale_pose')
        self.assertEqual(snapshot(doc,20.)[1],'timestamp_not_recorded')
        self.assertEqual(snapshot(doc,6.)[1],'ready')

if __name__=='__main__': unittest.main()
