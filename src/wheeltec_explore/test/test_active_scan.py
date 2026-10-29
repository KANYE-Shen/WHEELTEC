"""Safety-first initial observation: unknown swept space is never traversable."""
import math
import unittest
from wheeltec_explore.frontiers import Grid
from wheeltec_explore.active_scan import rotation_clearance, choose_scan, ScanBudget

def room():
    return Grid(60,60,.05,-1.5,-1.5,0,[0]*3600)

class ActiveScanSafetyTests(unittest.TestCase):
    def test_runtime_refuses_physical_board_or_nonlocal_ros(self):
        from wheeltec_explore.active_scan import simulation_observation_allowed
        self.assertTrue(simulation_observation_allowed(True,'1',''))
        self.assertFalse(simulation_observation_allowed(False,'1',''))
        self.assertFalse(simulation_observation_allowed(True,'0',''))
        self.assertFalse(simulation_observation_allowed(True,'1','D-Robotics RDK X5'))

    def test_known_free_full_sweep_is_accepted(self):
        self.assertTrue(rotation_clearance(room(),(0,0,0),.35)['safe'])

    def test_unknown_inside_rotation_envelope_is_rejected(self):
        grid=room();x,y=grid.world_to_cell(-.25,-.20);grid.data[y*grid.width+x]=-1
        report=rotation_clearance(grid,(0,0,0),.35)
        self.assertFalse(report['safe']);self.assertEqual(report['reason'],'unknown_swept_space')

    def test_obstacle_cell_intersecting_sweep_and_map_edge_are_rejected(self):
        grid=room();x,y=grid.world_to_cell(.35,0);grid.data[y*grid.width+x]=100
        self.assertFalse(rotation_clearance(grid,(0,0,0),.35)['safe'])
        self.assertFalse(rotation_clearance(room(),(1.4,0,0),.35)['safe'])

    def test_rotated_grid_origin_does_not_change_safety(self):
        grid=room();grid.origin_yaw=math.pi/3
        x,y=grid.cell_to_world(30,30)
        self.assertTrue(rotation_clearance(grid,(x,y,.9),.35)['safe'])

    def test_gain_comes_from_unknown_outside_current_fov_not_ground_truth(self):
        grid=room()
        for x in range(5,15):
            for y in range(25,35):grid.data[y*grid.width+x]=-1
        result=choose_scan(grid,(0,0,0),.35,90,270)
        self.assertTrue(result['safe']);self.assertGreater(result['expected_new_directions'],0)
        self.assertAlmostEqual(abs(result['angle_rad']),math.pi/2)

    def test_no_information_gain_does_not_cause_pointless_spin(self):
        self.assertEqual(choose_scan(room(),(0,0,0),.35,360,270)['reason'],'no_expected_gain')

    def test_unknown_clearance_blocks_even_high_expected_gain(self):
        grid=room();x,y=grid.world_to_cell(-.2,0);grid.data[y*grid.width+x]=-1
        self.assertIsNone(choose_scan(grid,(0,0,0),.35,360,270)['angle_rad'])

    def test_scan_attempts_are_finite_even_if_observation_does_not_help(self):
        budget=ScanBudget(1)
        self.assertTrue(budget.take())
        self.assertFalse(budget.take())
        self.assertFalse(budget.take())

if __name__=='__main__':unittest.main()

class StartupAssumptionTests(unittest.TestCase):
    def test_startup_assumption_skips_unknown_and_returns_full_turn(self):
        grid=room();grid.data[:]=[-1]*len(grid.data)
        import inspect
        self.assertIn('assume_start_safe',inspect.signature(choose_scan).parameters)
        result=choose_scan(grid,(0,0,0),.35,90,270,assume_start_safe=True)
        self.assertAlmostEqual(result['angle_rad'],2*math.pi)
        self.assertEqual(result['clearance_source'],'assumed_start')
        self.assertFalse(result['clearance_proven'])
        self.assertEqual(result['checked_cells'],0)
    def test_exception_requires_first_call_before_any_navigation(self):
        import wheeltec_explore.active_scan as policy
        startup_assumption_allowed=getattr(policy,'startup_assumption_allowed',None)
        self.assertTrue(callable(startup_assumption_allowed),'startup permission policy missing')
        self.assertTrue(startup_assumption_allowed(True,True,[],[]))
        self.assertFalse(startup_assumption_allowed(True,False,[],[]))
        self.assertFalse(startup_assumption_allowed(False,True,[],[]))
        self.assertFalse(startup_assumption_allowed(True,True,[{}],[]))
        self.assertFalse(startup_assumption_allowed(True,True,[],[{}]))
    def test_regular_scan_still_rejects_unknown(self):
        grid=room();grid.data[:]=[-1]*len(grid.data)
        self.assertFalse(choose_scan(grid,(0,0,0),.35,360,270)['safe'])
