import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from wheeltec_explore.frontiers import Grid
from wheeltec_explore.defaults import DEFAULTS
import wheeltec_explore.policy as policy


class LocalObservationTests(unittest.TestCase):
    def test_ratio_counts_occupied_as_observed_and_outside_as_unknown(self):
        self.assertTrue(hasattr(policy, 'local_known_ratio'), 'local coverage measure missing')
        grid = Grid(10, 10, 1., 0., 0., 0., [100]*85+[-1]*15)
        # A small disk wholly inside one cell: a real obstacle is known, not free.
        self.assertEqual(policy.local_known_ratio(grid, (.5, .5), .4), 1.)
        self.assertLess(policy.local_known_ratio(grid, (.5, .5), 2.), 1.)
        self.assertEqual(policy.local_known_ratio(grid, (5.5, 9.5), .4), 0.)

    def test_threshold_needs_near_target_and_distinct_maps(self):
        self.assertTrue(hasattr(policy, 'ObservationProgress'), 'bounded observation progress missing')
        progress = policy.ObservationProgress(0., 2., 0, DEFAULTS)
        self.assertIsNone(progress.update(1., 2., 1, .99))  # distant goal is never skipped
        self.assertIsNone(progress.update(2., .4, 2, .85))
        self.assertIsNone(progress.update(3., .4, 2, .85))  # same map is not a new view
        self.assertEqual(progress.update(4., .4, 3, .85), 'locally_observed')

    def test_no_progress_is_bounded_even_below_85_percent(self):
        self.assertTrue(hasattr(policy, 'ObservationProgress'), 'bounded observation progress missing')
        progress = policy.ObservationProgress(0., 1., 0, DEFAULTS)
        self.assertIsNone(progress.update(24., .98, 1, .5))
        self.assertEqual(progress.update(25., .98, 2, .5), 'goal_no_progress')

    def test_real_detour_displacement_is_progress_even_when_goal_is_farther(self):
        import inspect
        self.assertIn('position',inspect.signature(policy.ObservationProgress).parameters)
        progress=policy.ObservationProgress(0.,2.,0,DEFAULTS,position=(0.,0.))
        for tick in range(1,8):
            # Moving along an obstacle away from the goal is NOT being stuck.
            result=progress.update(tick*5.,2.+tick*.12,tick,.4,position=(0.,tick*.12))
            self.assertIsNone(result)
        self.assertIsNone(progress.update(59.,3.,8,.4,position=(0.,.84)))
        self.assertEqual(progress.update(60.,3.,9,.4,position=(0.,.84)),'goal_no_progress')

    def test_small_pose_jitter_does_not_renew_progress(self):
        import inspect
        self.assertIn('position',inspect.signature(policy.ObservationProgress).parameters)
        progress=policy.ObservationProgress(0.,1.,0,DEFAULTS,position=(0.,0.))
        for tick in range(1,5):
            self.assertIsNone(progress.update(tick*5.,1.,tick,.4,position=(.02*(-1)**tick,0.)))
        self.assertEqual(progress.update(25.,1.,5,.4,position=(.02,0.)),'goal_no_progress')

    def test_actual_run_moves_to_next_point_without_marking_target_reached(self):
        from test_planning_callbacks import PlanningCallbacksTests, ReachedNavigation
        from wheeltec_explore.frontiers import FrontierResult, FrontierGoal
        node=PlanningCallbacksTests().make_node()
        node.report={"goals":[]}
        goals=[FrontierGoal(1.,0.,0.,1.,10,1.),FrontierGoal(3.,0.,0.,3.,10,.5)]
        node.plan_frontiers=lambda pose:FrontierResult(goals,10.,2,0,0)
        def wait(predicate,timeout,**kw):
            node.map_updates+=1
            return predicate()
        node.wait=wait
        called=[]
        def navigate(x,y,*args,**kw):
            called.append((x,y))
            if len(called)==1:return False,'locally_observed'
            raise ReachedNavigation()
        node.navigate=navigate
        with self.assertRaises(ReachedNavigation):node.run()
        self.assertEqual(called,[(1.,0.),(3.,0.)])
        self.assertNotIn((1.,0.),node.visited)
        self.assertEqual(node.report['goals'][0]['success'],False)

    def test_approximately_observed_last_point_keeps_global_task_incomplete(self):
        from test_planning_callbacks import PlanningCallbacksTests
        from wheeltec_explore.frontiers import FrontierResult, FrontierGoal
        node=PlanningCallbacksTests().make_node()
        node.report={'goals':[]};node.history=[]
        node.run.__func__.__globals__['completion_state']=policy.completion_state
        node.plan_frontiers=lambda pose:FrontierResult([FrontierGoal(1.,0.,0.,1.,10,1.)],10.,1,0,0,residual_counts={'footprint_excluded':0,'multiview_observed':0,'reachable_unexplored':1})
        def wait(predicate,timeout,**kw):
            node.map_updates+=1
            return predicate()
        node.wait=wait
        node.navigate=lambda *a,**kw:(False,'locally_observed')
        node.save_map=lambda:True
        states=[]
        node.status=lambda state,reason,**kw:states.append((state,reason))
        self.assertEqual(node.run(),2)
        self.assertEqual(states[-1],('incomplete','local_observation_residuals'))

    def test_no_progress_cools_current_goal_and_tries_next(self):
        from test_planning_callbacks import PlanningCallbacksTests, ReachedNavigation
        from wheeltec_explore.frontiers import FrontierResult, FrontierGoal
        node=PlanningCallbacksTests().make_node()
        node.report={'goals':[]};node.retry=policy.RetryBook()
        node.plan_frontiers=lambda pose:FrontierResult([
            FrontierGoal(1.,0.,0.,1.,10,1.),FrontierGoal(3.,0.,0.,3.,10,.5)],10.,2,0,0)
        def wait(predicate,timeout,**kw):
            node.map_updates+=1
            return predicate()
        node.wait=wait
        targets=[]
        def navigate(x,y,*a,**kw):
            targets.append((x,y))
            if len(targets)==1:return False,'goal_no_progress'
            raise ReachedNavigation()
        node.navigate=navigate
        with self.assertRaises(ReachedNavigation):node.run()
        self.assertEqual(targets,[(1.,0.),(3.,0.)])
        self.assertFalse(node.retry.available((1.,0.),node.ros_seconds()))

    def test_ratio_is_local_not_global_completion(self):
        grid=Grid(20,20,1.,0.,0.,0.,[-1]*400)
        grid.data[5*20+5]=0
        self.assertEqual(policy.local_known_ratio(grid,(5.5,5.5),.4),1.)
        self.assertEqual(policy.completion_state(1.,0,0,True,True),'incomplete')

    def test_real_navigate_confirms_cancellation_and_does_not_fake_success(self):
        self.assertTrue(hasattr(policy, 'ObservationProgress'))
        source = Path(__file__).resolve().parents[1]/'wheeltec_explore/node.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=='Explorer')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name=='navigate']
        # Fake ROS messages/actions only; execute the actual navigation method.
        pose = lambda: SimpleNamespace(header=SimpleNamespace(), pose=SimpleNamespace(
            position=SimpleNamespace(), orientation=SimpleNamespace()))
        future = lambda value: SimpleNamespace(done=lambda: True, result=lambda: value)
        result = SimpleNamespace(done=lambda: False)
        handle = SimpleNamespace(accepted=True, get_result_async=lambda: result)
        clock = [0.]
        node = SimpleNamespace(config=dict(DEFAULTS), map_updates=0,
            get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: None)),
            nav=SimpleNamespace(send_goal_async=lambda goal: future(handle)),
            ros_seconds=lambda: clock[0], position=lambda: (.7, 0., 0.),
            grid=lambda: Grid(100,100,.1,-5.,-5.,0.,[0]*10000),
            report={}, active_goal=None, active_result=None, cancel_calls=0)
        def wait(predicate, timeout, **kwargs):
            for i in range(4):
                clock[0]+=1.; node.map_updates+=1
                if predicate(): return True
            node.wait_reason='wait_timeout'; return False
        node.wait=wait
        def cancel(): node.cancel_calls+=1; node.active_goal=None; return True
        node.cancel_active=cancel
        env={'NavigateToPose':SimpleNamespace(Goal=lambda:SimpleNamespace()),
             'PoseStamped':pose,'math':math,'GoalStatus':SimpleNamespace(STATUS_SUCCEEDED=4),
             'ObservationProgress':getattr(policy,'ObservationProgress',None),
             'local_known_ratio':getattr(policy,'local_known_ratio',None)}
        exec(compile(ast.Module(body=methods,type_ignores=[]),'actual_navigation','exec'),env)
        success, reason=env['navigate'](node,1.,0.,0.)
        self.assertEqual((success,reason),(False,'locally_observed'))
        self.assertEqual(node.cancel_calls,1)
        node.cancel_active=lambda:False
        with self.assertRaisesRegex(RuntimeError,'cancellation'):
            env['navigate'](node,1.,0.,0.)
