"""Exercise the real exploration run/wait path without ROS or movement."""
import ast
from concurrent.futures import ThreadPoolExecutor
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wheeltec_explore.defaults import DEFAULTS
from wheeltec_explore.frontiers import Grid, FrontierResult, FrontierGoal
from wheeltec_explore.health import MapHealth, MapUnstableError


class ReachedNavigation(Exception):
    pass


class PlanningCallbacksTests(unittest.TestCase):
    def make_node(self, fail_inputs=False, task_timeout=30., selection_error=False):
        start = time.monotonic()
        node = SimpleNamespace(config={**DEFAULTS, 'task_timeout':task_timeout},
            latest_map=object(), last_scan_ros=100., started_ros=None,
            health=MapHealth(), health_latched={}, health_active=False,
            visited=[], observations=[], report={}, map_updates=0,
            spin_action=None, nav=SimpleNamespace(server_is_ready=lambda:True),
            nav_calls=0, feed=True, polls=0)
        node.ros_seconds=lambda:100.+time.monotonic()-start
        def receive():
            now=node.ros_seconds()
            node.health.map(now,now);node.health.scan(now,now)
            node.health.transform(now,now,(0.,0.,0.));node.health.slam(True)
            node.last_scan_ros=now
        receive()
        def tick():
            now=node.ros_seconds();snapshot=node.health.snapshot(now)
            if node.health_active and not snapshot['healthy']:
                for issue in snapshot['issues']:node.health_latched.setdefault(issue,now)
            return snapshot
        node.health_tick=tick
        def spin(n, timeout_sec):
            time.sleep(.005);n.polls+=1
            if n.feed:receive()
            tick()
        def select(*args, **kwargs):
            if selection_error:raise ValueError('invalid candidate input')
            if fail_inputs:node.feed=False
            # Longer than the unchanged one-second health threshold.
            time.sleep(1.15)
            return FrontierResult([FrontierGoal(1.,0.,0.,1.,10,1.)],10.,1,0,0)
        node.wait_status_observers=lambda:True
        node.status=lambda *a,**k:None
        node.position=lambda:(0.,0.,0.)
        node.grid=lambda:Grid(10,10,.1,0.,0.,0.,[0]*100)
        node.retry=SimpleNamespace(available=lambda *a:True)
        def navigate(*a,**k):
            node.require_health();node.nav_calls+=1
            raise ReachedNavigation()
        node.navigate=navigate
        source=ast.parse((Path(__file__).resolve().parents[1]/'wheeltec_explore/node.py').read_text(encoding='utf-8'))
        explorer=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Explorer')
        methods=[n for n in explorer.body if isinstance(n,ast.FunctionDef) and n.name in ('run','wait','require_health','plan_frontiers')]
        env={'rclpy':SimpleNamespace(ok=lambda:True,spin_once=spin),
             'ThreadPoolExecutor':ThreadPoolExecutor,'select_frontiers':select,
             'MapUnstableError':MapUnstableError,'observation_fresh':lambda *a:True,
             'math':math,'Grid':Grid}
        exec(compile(ast.Module(body=methods,type_ignores=[]),'actual_explorer_methods','exec'),env)
        for m in methods:setattr(node,m.name,env[m.name].__get__(node))
        return node

    def test_slow_selection_keeps_callbacks_fresh_before_navigation(self):
        node=self.make_node()
        with self.assertRaises(ReachedNavigation):node.run()
        self.assertGreater(node.polls,10)
        self.assertEqual(node.nav_calls,1)
        self.assertFalse(node.health_latched)

    def test_real_input_timeout_during_selection_prevents_goal(self):
        node=self.make_node(fail_inputs=True)
        with self.assertRaisesRegex(MapUnstableError,'scan_stale'):node.run()
        self.assertEqual(node.nav_calls,0)

    def test_task_timeout_during_selection_prevents_goal(self):
        node=self.make_node(task_timeout=.15)
        with self.assertRaisesRegex(RuntimeError,'task_timeout'):node.run()
        self.assertEqual(node.nav_calls,0)

    def test_worker_exception_is_propagated_without_goal(self):
        node=self.make_node(selection_error=True)
        with self.assertRaisesRegex(ValueError,'invalid candidate input'):node.run()
        self.assertEqual(node.nav_calls,0)

if __name__=='__main__':unittest.main()
