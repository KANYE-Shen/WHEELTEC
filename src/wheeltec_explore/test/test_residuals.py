"""Evidence-based residuals; unknown inflation is never relaxed for navigation."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wheeltec_explore.frontiers import Grid, select_frontiers
from wheeltec_explore.policy import completion_state


def pocket(width):
    n, resolution = 80, .05
    data = [100]*(n*n)
    for y in range(1, 51):
        for x in range(1, 79):
            data[y*n+x] = 0
    for y in range(50, 78):
        for x in range(30, 30+round(width/resolution)):
            data[y*n+x] = 0 if y < 70 else -1
    return Grid(n,n,resolution,0,0,0,data)


class ResidualTests(unittest.TestCase):
    def test_narrow_pocket_reports_footprint_exclusion_without_entering_unknown(self):
        result=select_frontiers(pocket(.6),(.8,1.2))
        self.assertFalse(result.goals)
        self.assertEqual(getattr(result,'residual_counts',{}).get('footprint_excluded'),1)
        self.assertEqual(result.unreachable_clusters,0)

    def test_wide_pocket_still_requires_exploration(self):
        result=select_frontiers(pocket(.8),(.8,1.2))
        self.assertTrue(result.goals)
        self.assertEqual(getattr(result,'residual_counts',{}).get('footprint_excluded'),0)

    def test_legacy_visit_proximity_alone_does_not_prove_multiview(self):
        grid=pocket(.8)
        visited=[grid.cell_to_world(x,y) for y in range(50,70) for x in range(30,46)]
        result=select_frontiers(grid,(1.9,3.0),visited=visited)
        self.assertFalse(result.goals)
        self.assertGreater(result.unreachable_clusters,0)

    def test_wide_static_shadow_needs_distinct_visible_observations(self):
        import inspect
        self.assertIn('observations',inspect.signature(select_frontiers).parameters)
        grid=pocket(.8)
        visited=[grid.cell_to_world(x,y) for y in range(50,70) for x in range(30,46)]
        observations=[(1.875,2.875,10),(1.875,3.225,11)]
        result=select_frontiers(grid,(1.875,3.225),visited=visited,observations=observations)
        self.assertFalse(result.goals)
        self.assertEqual(result.residual_counts['multiview_observed'],1)
        self.assertEqual(result.unreachable_clusters,0)
        duplicate=select_frontiers(grid,(1.875,3.225),visited=visited,
                                  observations=[(1.875,3.225,11)]*4)
        self.assertGreater(duplicate.unreachable_clusters,0)

    def test_residual_terminal_keeps_area_failure_save_and_return_requirements(self):
        import inspect
        self.assertIn('residual_clusters',inspect.signature(completion_state).parameters)
        self.assertEqual(completion_state(12,0,0,True,True,residual_clusters=1),
                         'completed_with_residual_frontiers')
        self.assertEqual(completion_state(12,1,0,True,True,residual_clusters=1),'incomplete')
        self.assertEqual(completion_state(12,0,1,True,True,residual_clusters=1),'incomplete')
        self.assertEqual(completion_state(2,0,0,True,True,residual_clusters=1),'incomplete')
        self.assertEqual(completion_state(12,0,0,False,True,residual_clusters=1),'failed')
        self.assertEqual(completion_state(12,0,0,True,False,residual_clusters=1),'failed')

if __name__=='__main__': unittest.main()
