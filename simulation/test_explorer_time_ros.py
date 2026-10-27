"""Exercise Explorer methods with controlled ROS and supervisor clocks."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/wheeltec_explore'))
from wheeltec_explore.node import Explorer

class ExplorerTimeTests(unittest.TestCase):
    def fake(self, now=10):
        return NS(ros_seconds=lambda:now,started_ros=10.,
                  config={'task_timeout':100.,'tf_max_age':1.,'future_tolerance':.1,
                          'map_frame':'map','base_frame':'base_link'},wait_reason=None,
                  started=0.,require_health=lambda:True)

    def test_wall_clock_advance_does_not_consume_paused_ros_budget(self):
        node=self.fake(); ticks=[]
        with patch('wheeltec_explore.node.rclpy.ok',return_value=True), \
             patch('wheeltec_explore.node.rclpy.spin_once',side_effect=lambda *a,**kw:ticks.append(1)), \
             patch('wheeltec_explore.node.time.monotonic',side_effect=[0.,2.,3.,4.,5.,6.]):
            self.assertTrue(Explorer.wait(node,lambda:len(ticks)>=4,1.))

    def test_task_budget_reports_task_timeout_instead_of_map_timeout(self):
        node=self.fake(now=20.); node.config['task_timeout']=5.
        with patch('wheeltec_explore.node.rclpy.ok',return_value=True), \
             patch('wheeltec_explore.node.time.monotonic',side_effect=[0.,.1,10.2]):
            self.assertFalse(Explorer.wait(node,lambda:False,15.,check_task=True))
            self.assertEqual(node.wait_reason,'task_timeout')

    def test_position_rejects_stale_tf_and_accepts_fresh_tf(self):
        node=self.fake(now=20.)
        t=NS(header=NS(stamp=NS(sec=1,nanosec=0)),transform=NS(
            translation=NS(x=1.,y=2.),rotation=NS(x=0.,y=0.,z=0.,w=1.)))
        node.tf=NS(lookup_transform=lambda *a:t)
        self.assertIsNone(Explorer.position(node))
        t.header.stamp.sec=20
        self.assertEqual(Explorer.position(node),(1.,2.,0.))
        t.header.stamp.sec=25
        self.assertIsNone(Explorer.position(node))

if __name__=='__main__': unittest.main()
