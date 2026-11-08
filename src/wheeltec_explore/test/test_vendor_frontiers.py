import math
import tempfile
from pathlib import Path
import unittest

from wheeltec_explore.frontiers import Grid
from wheeltec_explore.vendor_frontiers import safe_vendor_goals, validate_vendor_geometry, validate_vendor_output


class VendorFrontiersTests(unittest.TestCase):
    def test_output_must_not_overwrite_existing_map_or_task_artifacts(self):
        with self.assertRaises(ValueError):validate_vendor_output('  ')
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'room'
            self.assertEqual(validate_vendor_output(str(base)),base.resolve())
            for suffix in ('.yaml','.pgm','.posegraph','.data','.metadata.json','.exploration.json'):
                target=base.with_suffix(suffix); target.write_text('old')
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    validate_vendor_output(str(base))
                target.unlink()

    def test_new_backend_rejects_unsafe_radius_and_exclusion(self):
        for radius, exclusion in [(0.,0.),(-1.,0.),(float('nan'),0.),(float('inf'),0.),(.3,-.1),(.3,.31),(.3,float('nan')),(.3,float('inf'))]:
            with self.subTest(radius=radius,exclusion=exclusion), self.assertRaises(ValueError):
                validate_vendor_geometry(radius,exclusion)
        validate_vendor_geometry(.3,0.)
        validate_vendor_geometry(.3,.3)

    def test_sample_yields_reachable_known_free_approach(self):
        grid = Grid(20, 20, .1, 0., 0., 0., [0 if x < 12 else -1 for y in range(20) for x in range(20)])
        goals = safe_vendor_goals(grid, (.55, 1.05), [(1.25, 1.05)], .15, .1, .6, .1, (), .3)
        self.assertTrue(goals)
        x, y = grid.world_to_cell(goals[0].x, goals[0].y)
        self.assertEqual(grid.value(x, y), 0)
        self.assertLess(goals[0].x, 1.05)

    def test_invalid_stale_geometry_and_outside_samples_cannot_become_goals(self):
        grid = Grid(20, 20, .1, 0., 0., 0., [0]*400)
        goals = safe_vendor_goals(grid, (.55, 1.05), [(1.25, 1.05), (9., 9.), (math.nan, 0.)], .15, .1, .6, .1, (), .3)
        self.assertEqual(goals, [])

    def test_disconnected_sample_never_yields_goal_across_wall(self):
        grid = Grid(30, 20, .1, 0., 0., 0., [100 if x == 10 else (0 if x < 24 else -1) for y in range(20) for x in range(30)])
        self.assertEqual(safe_vendor_goals(grid, (.55, 1.05), [(2.45, 1.05)], .15, .1, .6, .1, (), .3), [])


if __name__ == '__main__':
    unittest.main()
