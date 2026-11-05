import ast
import json
from pathlib import Path
import math
import unittest
from preflight import calibrated_geometry
import preflight


class PlanningEnvelopeTests(unittest.TestCase):
    def test_planning_covers_stop_zone_without_changing_body(self):
        profile = {'parameters': {'geometry': {
            'length_m': {'value': .30, 'source': 'measured', 'evidence': 'fixture'},
            'width_m': {'value': .25, 'source': 'measured', 'evidence': 'fixture'},
            'safety_margin_m': {'value': .05}}}}
        config = {'measured_braking_distance_m': None, 'safety': {
            'max_linear_m_s': .1, 'command_timeout_s': .5, 'obstacle_margin_m': .1}}
        body, old_radius = calibrated_geometry(profile)
        self.assertTrue(hasattr(preflight, 'planning_geometry'), 'shared planning/StopZone geometry missing')
        stop, footprint, radius = preflight.planning_geometry(profile, config)
        self.assertEqual(body[0], [.15, .125])
        self.assertAlmostEqual(old_radius, .24525624189766637)
        self.assertAlmostEqual(stop[0][0], .300)
        self.assertAlmostEqual(stop[0][1], .275)
        self.assertAlmostEqual(footprint[0][0], .350)
        self.assertAlmostEqual(footprint[0][1], .325)
        self.assertGreaterEqual(radius, max(math.hypot(*p) for p in footprint))
        config['measured_braking_distance_m'] = .08
        measured, _, _ = preflight.planning_geometry(profile, config)
        self.assertAlmostEqual(measured[0][0], .33)


    def test_actual_launch_uses_same_radius_and_preserves_stop_zone(self):
        root=Path(__file__).resolve().parent
        tree=ast.parse((root/'launch/robot.launch.py').read_text(encoding='utf-8'))
        configure=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='configure')
        # Geometry assignment + costmap loop are the real launch source.
        statements=[n for n in configure.body if isinstance(n,ast.For)][:1]
        nav={k:{k:{'ros__parameters':{'footprint':'old body', 'resolution':.05,
              'inflation_layer':{'inflation_radius':.45},'obstacle_layer':{'scan':{}}}}}
              for k in ('local_costmap','global_costmap')}
        env={'nav':nav,'radius':.47762432936357,'config':{'base_frame':'base_footprint','scan_topic':'/scan'}}
        exec(compile(ast.Module(body=statements,type_ignores=[]),'actual_launch_geometry','exec'),env)
        for name in nav:
            params=nav[name][name]['ros__parameters']
            self.assertNotIn('footprint',params)
            self.assertEqual(params['robot_radius'],env['radius'])
            self.assertGreater(params['inflation_layer']['inflation_radius'],env['radius'])
        assignment=next(n for n in configure.body if isinstance(n,ast.Assign) and
                        ast.unparse(n.targets[0])=="c['StopZone']['points']")
        env={'c':{'StopZone':{}},'stop_zone':[[.3,.275],[.3,-.275],[-.3,-.275],[-.3,.275]]}
        exec(compile(ast.Module(body=[assignment],type_ignores=[]),'actual_stop_zone','exec'),env)
        self.assertEqual(env['c']['StopZone']['points'],[.3,.275,.3,-.275,-.3,-.275,-.3,.275])
