"""Frontiers must lead to safe, reachable known space; never use scene truth."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from wheeltec_explore.frontiers import Grid, select_frontiers
except ImportError:
    Grid = select_frontiers = None


class FrontierTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(select_frontiers, 'Frontier selection is not implemented yet')

    def test_goal_stays_in_known_free_space_with_robot_clearance(self):
        # Known room half, with unknown continuation east and a wall to the north.
        cells = [0 if x < 12 else -1 for y in range(16) for x in range(24)]
        for x in range(24):
            cells[x] = 100
        grid = Grid(24, 16, 0.1, 0., 0., 0., cells)
        result = select_frontiers(grid, (0.4, 0.8), robot_radius=0.25, min_frontier_size=0.25)
        self.assertGreater(len(result.goals), 0)
        goal = result.goals[0]
        gx, gy = grid.world_to_cell(goal.x, goal.y)
        self.assertEqual(grid.value(gx, gy), 0)
        self.assertGreater(goal.y, 0.25)
        self.assertLess(goal.x, 1.2)
        self.assertGreater(goal.distance, 0.2)

    def test_frontier_behind_solid_wall_is_reported_unreachable(self):
        cells = [0 if x < 12 else -1 for y in range(12) for x in range(18)]
        for y in range(12):
            cells[y*18+6] = 100
        grid = Grid(18, 12, 0.1, 0., 0., 0., cells)
        result = select_frontiers(grid, (0.25, 0.6), robot_radius=0.1, min_frontier_size=0.2)
        self.assertFalse(result.goals)
        self.assertGreater(result.unreachable_clusters, 0)

    def test_closed_room_has_no_frontier(self):
        cells = [100 if x in (0, 19) or y in (0, 19) else 0 for y in range(20) for x in range(20)]
        grid = Grid(20, 20, 0.1, 0., 0., 0., cells)
        result = select_frontiers(grid, (1., 1.), robot_radius=0.2)
        self.assertFalse(result.goals)
        self.assertEqual(result.unreachable_clusters, 0)
        self.assertAlmostEqual(result.known_free_area, 3.24)

    def test_rotated_map_origin_round_trip(self):
        grid = Grid(10, 10, 0.2, 4., -2., math.pi/2, [0]*100)
        for cell in [(0, 0), (5, 8), (9, 9)]:
            self.assertEqual(grid.world_to_cell(*grid.cell_to_world(*cell)), cell)

    def test_does_not_cut_diagonally_through_obstacle_corner(self):
        cells = [100]*49
        cells[1*7+1] = 0
        cells[2*7+2] = 0
        cells[2*7+3] = -1
        grid = Grid(7, 7, 0.1, 0., 0., 0., cells)
        result = select_frontiers(grid, (0.15, 0.15), robot_radius=0.0, min_frontier_size=0.05)
        self.assertFalse(result.goals)
        self.assertGreater(result.unreachable_clusters, 0)

    def test_default_clearance_keeps_corner_frontier_inside_reference_footprint_margin(self):
        # A frontier near a wall must not pull the center within 0.35 m of it.
        cells = [0]*2000
        for y in range(40):
            cells[y*50+40] = 100
            for x in range(35,40):
                if y>=25:
                    cells[y*50+x] = -1
        grid = Grid(50,40,0.05,0.,0.,0.,cells)
        result = select_frontiers(grid,(0.6,0.6))
        self.assertTrue(result.goals)
        wall = [grid.cell_to_world(40,y) for y in range(40)]
        for goal in result.goals:
            self.assertGreaterEqual(min(math.dist((goal.x,goal.y),p) for p in wall),0.35)

    def test_entire_goal_footprint_is_in_known_map_not_unknown_or_outside(self):
        # No measured wall at the map edge: free pixels are not permission to
        # put the robot footprint into unknown space or beyond the grid extent.
        cells = [0 if x<12 else -1 for y in range(16) for x in range(24)]
        grid = Grid(24,16,0.1,0.,0.,0.,cells)
        result = select_frontiers(grid,(0.45,0.8))
        self.assertTrue(result.goals)
        unknown = [grid.cell_to_world(x,y) for y in range(16) for x in range(12,24)]
        for goal in result.goals:
            self.assertGreaterEqual(goal.x,0.35)
            self.assertGreaterEqual(goal.y,0.35)
            self.assertGreaterEqual(2.4-goal.x,0.35)
            self.assertGreaterEqual(1.6-goal.y,0.35)
            self.assertGreaterEqual(min(math.dist((goal.x,goal.y),p) for p in unknown),0.35)

    def test_visited_approach_is_replaced_by_another_safe_viewpoint(self):
        cells = [0 if x < 12 else -1 for y in range(20) for x in range(24)]
        grid = Grid(24,20,0.1,0.,0.,0.,cells)
        first = select_frontiers(grid,(0.45,0.8)).goals[0]
        visited = [(first.x,first.y)]
        result = select_frontiers(grid,(first.x,first.y),visited=visited)
        self.assertTrue(result.goals)
        self.assertGreaterEqual(math.dist((result.goals[0].x,result.goals[0].y),visited[0]),0.30)
        self.assertEqual(grid.value(*grid.world_to_cell(result.goals[0].x,result.goals[0].y)),0)

    def test_malformed_grid_is_rejected(self):
        with self.assertRaises(ValueError):
            Grid(10, 10, 0.1, 0., 0., 0., [0])


if __name__ == '__main__':
    unittest.main()