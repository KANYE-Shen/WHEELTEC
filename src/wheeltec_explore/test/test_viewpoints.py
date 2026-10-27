"""Occlusion-aware goals must respect the same safety and completion rules."""
import math
from pathlib import Path
import random
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/wheeltec_explore'))
sys.path.insert(0,str(ROOT/'simulation'))
from irregular_fixtures import fixture,frontier_cells,ray_clear_oracle
from wheeltec_explore.frontiers import Grid,select_frontiers
from wheeltec_explore.viewpoints import line_of_sight,choose_viewpoint


class ViewpointTests(unittest.TestCase):
    def test_ray_blocks_unknown_solids_and_exact_corner_touches(self):
        free={(x,y) for x in range(6) for y in range(6)}
        self.assertTrue(line_of_sight((1,1),(4,4),free))
        self.assertFalse(line_of_sight((1,1),(4,4),free-{(2,1)}))
        self.assertFalse(line_of_sight((4,4),(1,1),free-{(2,1)}))
        self.assertFalse(line_of_sight((0,0),(5,0),free-{(3,0)}))
        self.assertFalse(line_of_sight((0,0),(-1,0),free))

    def test_all_small_grid_rays_match_independent_closed_square_oracle(self):
        rng=random.Random(713)
        data=[0 if rng.random()>.2 else -1 for _ in range(49)]
        grid=Grid(7,7,.1,0,0,0,data)
        free={(x,y) for y in range(7) for x in range(7) if grid.value(x,y)==0}
        for a in sorted(free):
            for b in sorted(free):
                self.assertEqual(line_of_sight(a,b,free),ray_clear_oracle(grid,a,b),(a,b))

    def test_wavy_and_frame_gain_beats_centroid_without_smaller_clearance(self):
        for name in ('curved_c','wavy_edge','thin_frame'):
            grid,robot=fixture(name)
            before=select_frontiers(grid,robot,frontier_viewpoint_strategy='centroid')
            after=select_frontiers(grid,robot,frontier_viewpoint_strategy='visibility')
            fs=frontier_cells(grid)
            def gain(result):
                return max(sum(ray_clear_oracle(grid,grid.world_to_cell(g.x,g.y),b) for b in fs)/(.5+g.distance) for g in result.goals)
            self.assertGreater(gain(after),gain(before),name)
            for goal in after.goals:
                cell=grid.world_to_cell(goal.x,goal.y)
                self.assertTrue(any(ray_clear_oracle(grid,cell,b) for b in fs))
                unsafe=[(x,y) for y in range(grid.height) for x in range(grid.width) if grid.value(x,y)!=0]
                self.assertGreaterEqual(min(math.dist(cell,p)*grid.resolution for p in unsafe),.35)
            self.assertEqual(after.frontier_clusters,before.frontier_clusters)
            self.assertIn('viewpoint_diagnostics',vars(after))

    def test_no_visible_sample_is_unexplored_not_completed(self):
        free={(1,1),(3,1)}
        selected,diagnostics=choose_viewpoint([(1,1)],[(3,1)],free,{(1,1):1},.1,.5,.1,48,96)
        self.assertIsNone(selected)
        self.assertEqual(diagnostics['visible_sample_count'],0)
        self.assertFalse(diagnostics['visibility_is_completion_evidence'])

    def test_visibility_does_not_change_pocket_or_multiview_classification(self):
        from test_residuals import pocket
        for width in (.6,.8):
            grid=pocket(width)
            a=select_frontiers(grid,(.8,1.2),frontier_viewpoint_strategy='centroid')
            b=select_frontiers(grid,(.8,1.2),frontier_viewpoint_strategy='visibility')
            self.assertEqual(a.residual_counts,b.residual_counts)
            self.assertEqual(bool(a.goals),bool(b.goals))
        grid=pocket(.8)
        visited=[grid.cell_to_world(x,y) for y in range(50,70) for x in range(30,46)]
        args=dict(visited=visited,observations=[(1.875,2.875,10),(1.875,3.225,11)])
        a=select_frontiers(grid,(1.875,3.225),**args)
        b=select_frontiers(grid,(1.875,3.225),frontier_viewpoint_strategy='visibility',**args)
        self.assertEqual(a.residual_counts,b.residual_counts)

    def test_visibility_sampling_failure_remains_unexplored_in_selector(self):
        from unittest.mock import patch
        grid,robot=fixture('straight')
        with patch('wheeltec_explore.frontiers.choose_viewpoint',return_value=(None,{'visible_sample_count':0})):
            result=select_frontiers(grid,robot,frontier_viewpoint_strategy='visibility')
        self.assertFalse(result.goals)
        self.assertGreater(result.unreachable_clusters,0)
        self.assertEqual(result.residual_counts['footprint_excluded'],0)
        self.assertEqual(result.residual_counts['multiview_observed'],0)

    def test_rotated_origin_preserves_selected_cells(self):
        grid,robot=fixture('wavy_edge')
        a=select_frontiers(grid,robot,frontier_viewpoint_strategy='visibility')
        rotated=Grid(grid.width,grid.height,grid.resolution,8,-3,1.2,grid.data)
        cell=grid.world_to_cell(*robot)
        b=select_frontiers(rotated,rotated.cell_to_world(*cell),frontier_viewpoint_strategy='visibility')
        self.assertEqual([grid.world_to_cell(g.x,g.y) for g in a.goals],[rotated.world_to_cell(g.x,g.y) for g in b.goals])

    def test_unknown_strategy_and_invalid_budgets_are_rejected(self):
        grid,robot=fixture('straight')
        for kwargs in ({'frontier_viewpoint_strategy':'typo'}, {'viewpoint_candidate_budget':0}, {'viewpoint_frontier_budget':0}):
            with self.assertRaises(ValueError): select_frontiers(grid,robot,**kwargs)

if __name__=='__main__': unittest.main()
