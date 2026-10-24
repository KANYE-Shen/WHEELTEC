"""Independent, ROS-free regression tests for validation geometry and scoring."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
from scenarios import load_scenario, scenario_ids, validate_scenario, generate_world
from map_metrics import truth_grid, score_map, initial_alignment, trajectory_safety, load_saved_grid
from process_capture import Timeline


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.scene = load_scenario('baseline')
        self.spawn = self.scene['spawns'][0]['pose']
        self.grid = truth_grid(self.scene)

    def test_all_scenes_have_safe_connected_starts_and_metric_area(self):
        self.assertEqual(len(scenario_ids()), 5)
        for name in scenario_ids():
            scene = load_scenario(name)
            validation = validate_scenario(scene)
            self.assertGreaterEqual(validation['room_area_m2'], 20)
            self.assertLessEqual(validation['room_area_m2'], 30)
            self.assertGreaterEqual(len(scene['spawns']), 3)

    def test_unsafe_spawn_is_rejected(self):
        self.scene['spawns'][0]['pose'] = [2.49, 0, 0]
        with self.assertRaisesRegex(ValueError, 'spawn'):
            validate_scenario(self.scene)

    def test_self_intersection_is_rejected(self):
        self.scene['room'] = [[-2,-2],[2,2],[-2,2],[2,-2]]
        with self.assertRaises(ValueError):
            validate_scenario(self.scene)

    def test_world_keeps_gui_sensor_identity_and_uses_selected_spawn(self):
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as folder:
            output = generate_world(self.scene, 1, Path(folder)/'room.sdf')
            world = ET.parse(output).getroot().find('world')
            self.assertEqual(world.get('name'), 'wheeltec_room')
            self.assertIsNotNone(world.find("gui/plugin[@filename='WheeltecRenderSync']"))
            self.assertEqual(world.find('include/name').text, 'wheeltec_reference')
            self.assertEqual([float(v) for v in world.find('include/pose').text.split()][:2], self.scene['spawns'][1]['pose'][:2])

    def score(self, grid=None, transform=(0,0,0)):
        return score_map(self.scene, grid or self.grid, transform, self.spawn)

    def test_exact_map_covers_all_reachable_safe_space(self):
        result = self.score()
        self.assertAlmostEqual(result['reachable_coverage'], 1)
        self.assertEqual(result['false_free_obstacle_cells'], 0)
        self.assertLess(result['observable_contour_symmetric_p95_m'], .08)
        self.assertGreater(result['observable_contour_coverage'], .95)

    def test_half_map_unknown_lowers_coverage(self):
        grid = copy.deepcopy(self.grid)
        data = np.asarray(grid['data']).reshape(grid['height'],grid['width'])
        data[:, :grid['width']//2] = -1
        grid['data'] = data.ravel().tolist()
        self.assertLess(self.score(grid)['reachable_coverage'], .65)
        self.assertGreater(self.score(grid)['physical_free_unknown_area_m2'], 5)

    def test_free_obstacle_cells_are_penalized(self):
        grid = copy.deepcopy(self.grid)
        grid['data'] = [0 if value == 100 else value for value in grid['data']]
        result = self.score(grid)
        self.assertGreater(result['false_free_obstacle_cells'], 0)
        self.assertEqual(result['observable_contour_coverage'], 0)
        self.assertIsNone(result['observable_contour_symmetric_p95_m'])

    def test_spurious_wall_direction_cannot_be_diluted_by_other_contour(self):
        grid=copy.deepcopy(self.grid)
        ox,oy,_=grid['origin']
        x=ox+(np.arange(grid['width'])+.5)*grid['resolution']
        y=oy+(np.arange(grid['height'])+.5)*grid['resolution']
        data=np.asarray(grid['data']).reshape(grid['height'],grid['width'])
        strip=(y[:,None]>=-1.05)&(y[:,None]<-1.0)&(x[None,:]>=-.9)&(x[None,:]<1.0)
        data[strip]=100
        grid['data']=data.ravel().tolist()
        result=self.score(grid)
        # The long false wall is >1m from truth. Concatenating both directions
        # can hide >5% bad map points behind the larger accurate truth contour.
        self.assertGreater(result['observable_contour_symmetric_p95_m'],1.0)
        self.assertGreater(result['observable_contour_map_to_truth_p95_m'],1.0)
        self.assertLess(result['observable_contour_truth_to_map_p95_m'],.08)
        self.assertEqual(result['observable_contour_symmetric_p95_m'],max(
            result['observable_contour_map_to_truth_p95_m'],result['observable_contour_truth_to_map_p95_m']))

    def test_translation_is_not_optimized_away(self):
        result = self.score(transform=(.2,0,0))
        self.assertGreater(result['false_free_solid_cells'], 0)
        self.assertGreater(result['observable_contour_symmetric_p95_m'], .14)

    def test_origin_yaw_and_rigid_initial_alignment(self):
        grid = copy.deepcopy(self.grid)
        angle = .7
        x,y,_ = grid['origin']
        grid['origin'] = [math.cos(angle)*x-math.sin(angle)*y+3,
                          math.sin(angle)*x+math.cos(angle)*y-1, angle]
        sx,sy,sa = self.spawn
        measured = [math.cos(angle)*sx-math.sin(angle)*sy+3,
                    math.sin(angle)*sx+math.cos(angle)*sy-1, sa+angle]
        transform = initial_alignment(self.spawn, measured)
        self.assertTrue(np.allclose(transform, [3,-1,angle]))
        result = self.score(grid, transform)
        self.assertAlmostEqual(result['reachable_coverage'], 1)

    def test_unknown_map_never_counts_as_free(self):
        grid = copy.deepcopy(self.grid)
        grid['data'] = [-1]*len(grid['data'])
        result = self.score(grid)
        self.assertEqual(result['reachable_coverage'], 0)
        self.assertIsNone(result['observable_contour_symmetric_p95_m'])
        self.assertEqual(result['observable_contour_missing_fraction'], 1)

    def test_rotating_actual_footprint_geometric_overlap(self):
        # At x=2.31 body fits at zero yaw, but the wheel hits the wall at 90deg.
        safe = trajectory_safety(self.scene, [[2.31,.5,0]])
        collision = trajectory_safety(self.scene, [[2.31,.5,math.pi/2]])
        self.assertEqual(safe['geometric_overlap_samples'], 0)
        self.assertGreater(collision['geometric_overlap_samples'], 0)
        self.assertEqual(collision['contact_measurement'], 'geometric_projection_only')

    def test_all_save_entry_thresholds_roundtrip_unknown_free_occupied(self):
        import ast
        import yaml
        from PIL import Image
        root=Path(__file__).resolve().parents[1]
        thresholds=[]
        for relative in ('simulation/save_map.py','src/wheeltec_explore/wheeltec_explore/node.py'):
            module=ast.parse((root/relative).read_text(encoding='utf-8-sig'))
            thresholds.extend(ast.literal_eval(node.value) for node in ast.walk(module)
                              if isinstance(node,ast.Assign) and any(isinstance(target,ast.Attribute) and target.attr=='free_thresh' for target in node.targets))
        module=ast.parse((root/'simulation/launch/room.launch.py').read_text())
        thresholds.extend(ast.literal_eval(value) for node in ast.walk(module) if isinstance(node,ast.Dict)
                          for key,value in zip(node.keys,node.values) if isinstance(key,ast.Constant) and key.value=='free_thresh_default')
        thresholds.append(yaml.safe_load((root/'simulation/config/nav2.yaml').read_text())['map_saver']['ros__parameters']['free_thresh_default'])
        self.assertEqual(len(thresholds),4)
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            Image.fromarray(np.array([[205,254,0]],dtype=np.uint8)).save(directory/'map.pgm')
            for threshold in thresholds:
                settings={'image':'map.pgm','mode':'trinary','resolution':.05,'origin':[0,0,0],
                          'negate':0,'free_thresh':threshold,'occupied_thresh':.65}
                (directory/'map.yaml').write_text(yaml.safe_dump(settings))
                loaded=load_saved_grid(directory/'map.yaml')
                self.assertEqual(loaded['data'],[-1,0,100], 'unsafe saved-map threshold '+str(threshold))

    def test_interpolated_trajectory_cannot_jump_over_obstacle(self):
        result = trajectory_safety(self.scene, [[-.5,.5,0],[1.1,.5,0]])
        self.assertGreater(result['geometric_overlap_samples'], 0)


class TimelineTests(unittest.TestCase):
    def test_map_versions_deduplicate_geometry_and_cells(self):
        timeline=Timeline({'id':'test'})
        grid={'width':2,'height':1,'resolution':.05,'origin':[0,0,.5],'data':[0,-1]}
        self.assertEqual(timeline.add_map(grid),0)
        self.assertEqual(timeline.add_map(copy.deepcopy(grid)),0)
        grid['origin'][2]=.7
        self.assertEqual(timeline.add_map(grid),1)
        self.assertEqual(timeline.document['maps'][0]['origin'][2],.5)

    def test_atomic_timeline_preserves_null_observations_and_terminal(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            timeline=Timeline({'id':'test'})
            timeline.append_frame({'t':1.0,'pose':None,'scan':None,'plan':[],
                                   'map':None,'issues':['missing_map_transform']})
            path=Path(directory)/'process.json'
            timeline.save(path,{'state':'failed'})
            result=json.loads(path.read_text())
            self.assertEqual(result['version'],1)
            self.assertIsNone(result['frames'][0]['pose'])
            self.assertEqual(result['terminal']['state'],'failed')
            self.assertFalse(path.with_suffix('.json.tmp').exists())


class TruthQualityTests(unittest.TestCase):
    @staticmethod
    def samples():
        return [{'t':i*.02,'wall_t':10+i*.02,'pose':[0,0,0]} for i in range(21)]

    def quality(self,samples,terminal_wall_t=10.4,terminal_sim_t=.4):
        from truth_capture import truth_quality
        return truth_quality(samples,terminal_wall_t,task_start_wall_t=10,
                             terminal_sim_t=terminal_sim_t)

    def test_regular_stationary_measurements_are_valid(self):
        self.assertTrue(self.quality(self.samples())['valid'])

    def test_one_start_sample_cannot_imply_return_and_collision_success(self):
        result=self.quality(self.samples()[:1])
        self.assertFalse(result['valid'])
        self.assertIn('insufficient_distinct_measurement_stamps',result['issues'])
        self.assertIn('terminal_measurement_stale_sim',result['issues'])

    def test_legacy_zero_stamps_and_backwards_time_are_invalid(self):
        samples=self.samples()
        for sample in samples:
            sample['t']=0
        self.assertFalse(self.quality(samples)['valid'])
        samples=self.samples()
        samples[5]['t']=samples[4]['t']-.01
        self.assertIn('measurement_time_regressed',self.quality(samples)['issues'])

    def test_gaps_and_stale_terminal_measurements_are_invalid(self):
        self.assertIn('measurement_gap_exceeded',self.quality(self.samples()[::15])['issues'])
        self.assertIn('terminal_measurement_stale_wall',self.quality(self.samples(),terminal_wall_t=11)['issues'])
        samples=self.samples()
        samples[10:]=[dict(sample,wall_t=sample['wall_t']+.6) for sample in samples[10:]]
        self.assertIn('arrival_gap_exceeded',self.quality(samples,terminal_wall_t=11)['issues'])

    def test_startup_gaps_are_excluded_from_task_and_shutdown_is_not_sample_time(self):
        samples=[{'t':-5,'wall_t':0,'pose':[0,0,0]}]+self.samples()
        self.assertTrue(self.quality(samples)['valid'])
        # The evaluator passes its frozen decision time, not a later cleanup time.
        self.assertFalse(self.quality(samples,terminal_wall_t=15)['valid'])

    def test_raw_pose_uses_message_stamp_and_rejects_missing_measurement_stamp(self):
        from truth_capture import parse_truth_message
        message={'header':{'stamp':{'sec':2,'nsec':50000000}},'pose':[
            {'name':'wheeltec_reference','header':{'stamp':{}},
             'position':{'x':1,'y':2},'orientation':{'w':1}}]}
        self.assertEqual(parse_truth_message(message),{'t':2.05,'pose':[1.0,2.0,0.0]})
        del message['header']
        with self.assertRaises(ValueError):
            parse_truth_message(message)


class PoseFreshnessTests(unittest.TestCase):
    def capture(self,now,stamp):
        from types import SimpleNamespace as NS
        from process_capture import ProcessCapture
        capture=ProcessCapture.__new__(ProcessCapture)
        transform=NS(translation=NS(x=1,y=2),rotation=NS(x=0,y=0,z=0,w=1))
        message=NS(header=NS(stamp=NS(sec=int(stamp),nanosec=int((stamp-int(stamp))*1e9))),transform=transform)
        capture.tf=NS(lookup_transform=lambda *args:message)
        capture.now=lambda:now
        capture.started=0
        capture.timeline=Timeline()
        capture.latest_scan=capture.latest_plan=None
        capture.scan_received=capture.plan_received=None
        capture.status={}
        capture.initial_pose=capture.initial_pose_time=None
        capture.issue_counts={}
        capture._pose_stamp_ns=capture._pose_stamp_seen_wall=None
        return capture

    def tick(self,capture,wall):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        fake_time=NS(Time=type('Time',(),{'from_msg':staticmethod(lambda stamp:stamp)}))
        with patch.dict(sys.modules,{'rclpy.time':fake_time}), patch('process_capture.time.monotonic',return_value=wall):
            capture.tick()
        return capture.timeline.document['frames'][-1]

    def test_cached_old_transform_is_null_and_does_not_enter_path(self):
        capture=self.capture(now=200,stamp=1)
        frame=self.tick(capture,10)
        self.assertIsNone(frame['pose'])
        self.assertIn('stale_pose_transform',frame['issues'])
        self.assertEqual(capture.timeline.document['path'],[])
        self.assertIsNone(capture.initial_pose)

    def test_repeated_stamp_becomes_stale_by_wall_time_even_when_sim_time_pauses(self):
        capture=self.capture(now=1,stamp=1)
        self.assertEqual(self.tick(capture,10)['pose'],[1,2,0])
        frame=self.tick(capture,12.1)
        self.assertIsNone(frame['pose'])
        self.assertIn('stale_pose_transform',frame['issues'])
        self.assertEqual(capture.timeline.document['path'],[[1,2]])

    def test_timestamped_scan_transform_keeps_working_with_fresh_pose(self):
        from types import SimpleNamespace as NS
        capture=self.capture(now=200,stamp=200)
        capture.latest_scan=NS(header=NS(frame_id='laser',stamp=NS(sec=200,nanosec=0)),
                               ranges=[1.0],angle_min=0,angle_increment=1,range_min=.08,range_max=10)
        capture.scan_received=10
        frame=self.tick(capture,10)
        self.assertEqual(frame['pose'],[1,2,0])
        self.assertEqual(frame['scan'],[[2,2]])


class RunnerInterfaceTests(unittest.TestCase):
    def test_nonfinite_timeouts_and_out_of_range_domains_are_rejected(self):
        import contextlib
        import io
        from check_exploration import parse_arguments
        for arguments in (['--task-timeout','nan'],['--timeout','inf'],['--domain','-1'],['--domain','233']):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_arguments(arguments)

    def test_existing_timeouts_and_new_validation_flags_are_documented(self):
        import subprocess
        import sys
        process=subprocess.run([sys.executable,str(Path(__file__).with_name('check_exploration.py')),'--help'],
                               capture_output=True,text=True,check=True)
        for flag in ('--scenario','--spawn','--output','--record','--no-record','--task-timeout','--timeout'):
            self.assertIn(flag,process.stdout)


if __name__ == '__main__':
    unittest.main()
