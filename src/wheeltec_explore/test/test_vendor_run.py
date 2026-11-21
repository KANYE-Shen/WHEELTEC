"""Exercise the actual task loop without ROS nodes or robot movement."""
import ast
import math
import sys
import types
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from wheeltec_explore.defaults import DEFAULTS
from wheeltec_explore.frontiers import FrontierCensus, FrontierGoal, Grid
from wheeltec_explore.health import MapUnstableError
from wheeltec_explore.policy import completion_state


class ReachedNavigation(Exception):
    pass


class WaitedForVendor(Exception):
    pass


class VendorTaskTests(unittest.TestCase):
    def test_cli_defaults_to_managed_vendor_exploration(self):
        self.assertEqual(DEFAULTS['frontier_backend'], 'vendor')
        self.assertTrue(DEFAULTS['vendor_managed'])
        self.assertEqual(DEFAULTS['base_frame'], 'base_footprint')

    def test_map_census_exposes_eligibility_without_navigation_goals(self):
        from wheeltec_explore.frontiers import Grid, census_frontiers
        grid = Grid(24, 20, .1, 0., 0., 0., [0 if x < 12 else -1
                    for _ in range(20) for x in range(24)])
        census = census_frontiers(grid, (.45, .8))
        self.assertTrue(census.approaches)
        self.assertFalse(hasattr(census, 'goals'))
        self.assertEqual(census.frontier_clusters, 1)

    def test_launch_requires_output_path_and_does_not_update_latest(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/'launch'/'vendor_rrt.launch.py').read_text(encoding='utf-8'))
        declarations=[n for n in ast.walk(source) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
                      and n.func.id=='DeclareLaunchArgument' and n.args and isinstance(n.args[0],ast.Constant)]
        output=next(n for n in declarations if n.args[0].value=='map_output')
        self.assertFalse(any(k.arg=='default_value' for k in output.keywords))
        dicts=[n for n in ast.walk(source) if isinstance(n,ast.Dict)]
        task=next(n for n in dicts if any(isinstance(k,ast.Constant) and k.value=='frontier_backend' for k in n.keys))
        pairs={k.value:v for k,v in zip(task.keys,task.values) if isinstance(k,ast.Constant)}
        self.assertFalse(pairs['update_latest'].value)
        self.assertIn("LaunchConfiguration('map_output')",ast.unparse(pairs['map_output']))

    def make_node(self, vendor_goals):
        result = FrontierCensus([(1, 0)], 10, 1, 0, 0)
        node = SimpleNamespace(config={**DEFAULTS, 'vendor_managed':False},
            latest_map=object(), last_scan_ros=100., started_ros=None,
            health_active=False, report={'goals':[]}, map_updates=0, vendor_revision=0, vendor_initialized=False,
            spin_action=None, nav=SimpleNamespace(server_is_ready=lambda: True),
            retry=SimpleNamespace(available=lambda *a: True,exhausted=lambda *a: False),
            wait_reason='', calls=[],history=[],visited=[],observations=[])
        node.ros_seconds=lambda:100.
        node.wait_status_observers=lambda:True
        node.status=lambda *a,**k:node.calls.append(('status',a))
        node.position=lambda:(0.,0.,0.)
        node.health_tick=lambda:{'healthy':True}
        node.require_health=lambda:True
        node.initialize_vendor=lambda pose:node.calls.append(('initialize',pose))
        node.plan_vendor_frontiers=lambda pose:vendor_goals
        node.census_frontiers=lambda pose:result
        node.grid=lambda:Grid(1,1,.1,0.,0.,0.,[0])
        node.save_map=lambda:True
        def wait(predicate, timeout, **kwargs):
            if kwargs.get('check_task'):
                raise WaitedForVendor()
            return True
        node.wait=wait
        def navigate(*args):
            raise ReachedNavigation()
        node.navigate=navigate
        source=ast.parse((Path(__file__).resolve().parents[1]/'wheeltec_explore'/'node.py').read_text(encoding='utf-8'))
        explorer=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Explorer')
        methods=[n for n in explorer.body if isinstance(n,ast.FunctionDef) and n.name in ('run','check_vendor_full_map','report_census')]
        env={'rclpy':SimpleNamespace(ok=lambda:True), 'observation_fresh':lambda *a:True,
             'math':math, 'completion_state':completion_state, 'MapUnstableError':MapUnstableError}
        exec(compile(ast.Module(body=methods,type_ignores=[]),'actual_vendor_task','exec'),env)
        for method in methods:
            setattr(node, method.name, env[method.name].__get__(node))
        return node

    def test_empty_vendor_waits_when_grid_finds_frontiers(self):
        node=self.make_node([])
        with self.assertRaises(WaitedForVendor):node.run()
        self.assertTrue(any(item[0]=='initialize' for item in node.calls))
        self.assertTrue(any('Waiting for a fresh vendor frontier' in item[1] for item in node.calls if item[0]=='status'))

    def test_valid_vendor_goal_reaches_navigation(self):
        node=self.make_node([FrontierGoal(1,0,0)])
        with self.assertRaises(ReachedNavigation):node.run()

    def test_managed_vendor_uses_map_after_optional_startup_observation(self):
        node = self.make_node([FrontierGoal(1, 0, 0)])
        node.config.update(vendor_managed=True, initial_rotation_assumed_safe=True)
        node.spin_action = object()
        order = []
        node.active_observe = lambda pose, initial: order.append('observe') or (True, 'succeeded')
        def prepare(pose):
            if not node.vendor_initialized:
                order.append('initialize')
                node.vendor_initialized = True
        node.prepare_managed_vendor = prepare
        with self.assertRaises(ReachedNavigation):
            node.run()
        self.assertEqual(order, ['observe', 'initialize'])

    def test_exhausted_vendor_batch_waits_when_other_grid_frontiers_exist(self):
        node=self.make_node([FrontierGoal(1,0,0)])
        node.retry.available=lambda *args:False
        with self.assertRaises(WaitedForVendor):node.run()
        self.assertTrue(any('Waiting for another vendor frontier' in item[1] for item in node.calls if item[0]=='status'))

    def test_locally_observed_batch_waits_if_other_full_map_goal_remains(self):
        node=self.make_node([FrontierGoal(1,0,0)])
        node.census_frontiers=lambda pose:FrontierCensus([(2,0)],10,1,0,0)
        node.report={'goals':[]}
        node.visited=[];node.observations=[]
        node.navigate=lambda *args:(False,'locally_observed')
        calls=[]
        def wait(predicate, timeout, **kwargs):
            if kwargs.get('check_task'):
                calls.append(1)
                if len(calls)>1:raise WaitedForVendor()
            return True
        node.wait=wait
        with self.assertRaises(WaitedForVendor):node.run()
        self.assertTrue(any('Waiting for another vendor frontier' in item[1] for item in node.calls if item[0]=='status'))

    def test_full_map_retry_exhaustion_reports_incomplete(self):
        node=self.make_node([])
        node.retry.available=lambda *args:False
        node.retry.exhausted=lambda *args:True
        self.assertEqual(node.run(),2)
        self.assertTrue(any(item[1][:2]==('incomplete','frontier_retries_exhausted') for item in node.calls if item[0]=='status'))

    def test_full_map_locally_observed_reports_incomplete(self):
        node=self.make_node([FrontierGoal(1,0,0)])
        node.report={'goals':[]}
        node.navigate=lambda *args:(False,'locally_observed')
        node.wait=lambda *args,**kwargs:True
        self.assertEqual(node.run(),2)
        self.assertTrue(any(item[1][:2]==('incomplete','local_observation_residuals') for item in node.calls if item[0]=='status'))

    def test_completion_uses_distinct_maps_and_unrounded_floor_area(self):
        node = self.make_node([])
        censused = []
        def census(pose):
            censused.append(node.map_updates)
            return FrontierCensus([], 7.9999, 0, 0, 0)
        def wait(predicate, timeout, **kwargs):
            if kwargs.get('check_task'):
                self.assertFalse(predicate())
                node.map_updates += 1
                return predicate()
            return True
        node.census_frontiers = census
        node.wait = wait
        self.assertEqual(node.run(), 2)
        self.assertEqual(censused, [0, 1, 2])
        self.assertEqual(node.report['known_free_area_m2'], 8.0)

    def test_three_empty_maps_save_then_return_to_start(self):
        node = self.make_node([])
        node.census_frontiers = lambda pose: FrontierCensus([], 8., 0, 0, 0)
        def wait(predicate, timeout, **kwargs):
            if kwargs.get('check_task'):
                node.map_updates += 1
                return predicate()
            return True
        node.wait = wait
        poses = iter([(0., 0., 0.)] * 2 + [(1., 0., 0.)] * 4)
        node.position = lambda: next(poses)
        events = []
        node.save_map = lambda: events.append('save') or True
        def navigate(x, y, yaw, *, returning):
            events.append((x, y, yaw, returning))
            return True, 'succeeded'
        node.navigate = navigate
        self.assertEqual(node.run(), 0)
        self.assertEqual(events, ['save', (0., 0., 0., True)])

    def test_boundary_initialization_requires_unique_graph_and_sends_exactly_five_points(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/'wheeltec_explore'/'node.py').read_text(encoding='utf-8'))
        explorer=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Explorer')
        method=next(n for n in explorer.body if isinstance(n,ast.FunctionDef) and n.name=='initialize_vendor')
        env={'math':math}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'actual_vendor_init','exec'),env)
        class PointStamped:
            def __init__(self):
                self.header=SimpleNamespace(frame_id='',stamp=None)
                self.point=SimpleNamespace(x=0.,y=0.)
        geom=types.ModuleType('geometry_msgs');msg=types.ModuleType('geometry_msgs.msg');msg.PointStamped=PointStamped
        sent=[]
        node=SimpleNamespace(config={**DEFAULTS,'vendor_bounds':'-1,-2,3,4'},
            boundary_pub=SimpleNamespace(get_subscription_count=lambda:2,publish=sent.append),
            get_publishers_info_by_topic=lambda name:[1],
            get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(to_msg=lambda:123)))
        node.wait=lambda predicate,*args,**kwargs:predicate()
        with patch.dict(sys.modules,{'geometry_msgs':geom,'geometry_msgs.msg':msg}):
            env['initialize_vendor'](node,(0.,0.,0.))
            self.assertEqual([(p.point.x,p.point.y) for p in sent],[(-1.,-2.),(3.,-2.),(3.,4.),(-1.,4.),(0.,0.)])
            sent.clear()
            node.get_publishers_info_by_topic=lambda name:[1,2]
            with self.assertRaisesRegex(RuntimeError,'ownership'):
                env['initialize_vendor'](node,(0.,0.,0.))
            self.assertEqual(sent,[])


if __name__ == '__main__':unittest.main()
