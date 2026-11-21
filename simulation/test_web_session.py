import math
import unittest

from web_session import RequestError, goal_options, start_options


class WebSimulationRequestTests(unittest.TestCase):
    def test_start_settings_are_typed_and_preserve_scenario_identity(self):
        self.assertEqual(start_options({}), {
            'mode': 'mapping', 'scenario': 'baseline', 'spawn': 0,
            'seed': 0, 'lidar_noise_stddev': .01, 'map_id': None,
        })
        options = start_options({'mode': 'localization', 'map_id': 'saved'})
        self.assertIsNone(options['scenario'])
        self.assertIsNone(options['spawn'])
        for bad in ({'scenario': '../robot'}, {'seed': True}, {'seed': -1},
                    {'lidar_noise_stddev': math.nan}, {'lidar_noise_stddev': .04},
                    {'mode': 'interfaces'}, {'mode': 'localization'},
                    {'mode': 'mapping', 'map_id': 'saved'},
                    {'mode': 'localization', 'map_id': 'saved', 'spawn': 1},
                    {'ros_domain_id': 77}, {'world': '/tmp/custom.sdf'}):
            with self.subTest(bad=bad), self.assertRaises(RequestError):
                start_options(bad)

    def test_goal_accepts_compatible_revision_and_checks_latest_grid(self):
        state = {'run_id': 'current', 'navigation_ready': True, 'map': {
            'revision': 5, 'frame': 'map', 'origin': [2., 3., math.pi / 2],
            'resolution': 1., 'width': 2, 'height': 2, 'data': [0, 100, -1, 0],
        }}
        candidate = {'run_id': 'current', 'map_revision': 4, 'frame': 'map',
                     'x': 1.5, 'y': 3.5, 'yaw': 0.0}
        self.assertEqual(goal_options(candidate, state, 4), (1.5, 3.5, 0.0))
        for patch in ({'run_id': 'previous'}, {'frame': 'odom'}, {'map_revision': 3},
                      {'map_revision': 6}, {'map_revision': False}, {'y': 4.5},
                      {'x': 0.5}, {'x': 3}, {'yaw': math.inf}):
            with self.subTest(patch=patch), self.assertRaises(RequestError):
                goal_options(candidate | patch, state, 4)


if __name__ == '__main__':
    unittest.main()
