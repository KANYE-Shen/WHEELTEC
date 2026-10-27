import unittest
class BagStatisticsTests(unittest.TestCase):
    def test_static_noise_and_invalid_values(self):
        from bag_statistics import scan_statistics
        result=scan_statistics([[1.,2.,float('inf')],[1.1,2.1,float('nan')],[.9,1.9,3.]],[1.,1.1,1.2],.1,8.)
        self.assertEqual(result['frames'],3)
        self.assertAlmostEqual(result['invalid_fraction'],2/9)
        self.assertAlmostEqual(result['median_temporal_sigma_m'],.1)
        self.assertAlmostEqual(result['measurement_hz'],10.)
    def test_static_marker_and_repeated_timestamps_are_required(self):
        from bag_statistics import scan_statistics
        with self.assertRaises(ValueError): scan_statistics([[1.],[2.]],[1.,1.],.1,8.)
    def test_independent_motion_annotations_recover_scale_and_full_rotation(self):
        from bag_statistics import motion_drift
        import math
        odom=[[float(i),2.02*i/4,0.,math.atan2(math.sin(i*math.pi/2),math.cos(i*math.pi/2))] for i in range(5)]
        result=motion_drift(odom,[{'start_s':0.,'end_s':4.,'expected_forward_m':2.,'expected_lateral_m':0.,'expected_yaw_rad':2*math.pi,'evidence':'tape-and-angle-sheet','uncertainty_m':.005,'uncertainty_rad':.01}])
        self.assertAlmostEqual(result['samples'][0]['forward_error_m'],.02)
        self.assertAlmostEqual(result['samples'][0]['yaw_error_rad'],0.)
        with self.assertRaises(ValueError): motion_drift(odom,[{'start_s':0.,'end_s':4.}])

    def test_gap_reports_unavailable_measured_drift(self):
        from bag_statistics import compare
        report=compare({'kind':'real','scan':{'measurement_hz':10.}},{'kind':'simulation','scan':{'measurement_hz':9.}})
        self.assertEqual(report['scan_difference']['measurement_hz'],-1.)
        self.assertEqual(report['odometry_drift_comparison'],'unverified: independent displacement annotations required')
if __name__=='__main__': unittest.main()
