"""Offline regression: never connects to ROS, SSH, camera, or a robot."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import timestamp_source_audit as target

FIXTURES = Path(__file__).resolve().parents[1] / "setup/verification/2026-10-28-night/g0-timestamp/fixtures"

class TimestampAuditTests(unittest.TestCase):
    def test_integer_shift_retains_epoch_microseconds(self):
        self.assertEqual(target.epoch_shift_us(946686580, 823742, 10, 123456000), 946686570700286)
    def test_rounding_monotonic_nsec_carries_at_second(self):
        self.assertEqual(target.epoch_shift_us(100, 0, 9, 999999500), 90000000)
    def test_timestamp_carries_fractional_epoch_shift(self):
        self.assertEqual(target.image_timestamp(10, 999999, 946686570700286), (946686581, 700285000))
    def test_half_second_does_not_round_seconds_up(self):
        stamps=[target.image_timestamp(10, u, 100000000) for u in [499999,500000,999999]]
        self.assertEqual(stamps, [(110,499999000),(110,500000000),(110,999999000)])
    def test_frame_sequence_is_monotonic_across_second(self):
        values=[target.image_timestamp(s,u,100700286) for s,u in [(10,499999),(10,500000),(10,999999),(11,0)]]
        self.assertEqual(values, sorted(values))
    def test_rejects_invalid_time_fields(self):
        for args in [(0,-1,0),(0,1000000,0),(0,0,-1)]:
            with self.assertRaises(ValueError): target.image_timestamp(*args)
    def test_identifies_all_three_exact_pinned_states(self):
        for state in ['legacy','pr267','candidate']:
            self.assertEqual(target.audit_source(FIXTURES/state)['state'],state)
    def test_unknown_or_incomplete_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(target.audit_source(Path(d))['state'],'unknown')
            with self.assertRaises(ValueError): target.prepare_patch(Path(d),Path(d)/'out')
    def test_mixed_source_is_not_called_fixed(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source'; shutil.copytree(FIXTURES/'legacy',src)
            shutil.copyfile(FIXTURES/'candidate/include/usb_cam/utils.hpp',src/'include/usb_cam/utils.hpp')
            self.assertEqual(target.audit_source(src)['state'],'unknown')
    def test_prepare_preserves_source_and_emits_reviewable_diff(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source'; shutil.copytree(FIXTURES/'legacy',src)
            before={str(p.relative_to(src)):p.read_bytes() for p in src.rglob('*') if p.is_file()}
            out=Path(d)/'bundle'; result=target.prepare_patch(src,out)
            after={str(p.relative_to(src)):p.read_bytes() for p in src.rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            self.assertIn('calc_img_timestamp',(out/'candidate.patch').read_text())
            self.assertEqual(target.audit_source(out/'candidate')['state'],'candidate')
            self.assertFalse(result['deployment_ready'])
    def test_does_not_overwrite_or_write_inside_source(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source'; shutil.copytree(FIXTURES/'legacy',src)
            out=Path(d)/'out'; out.mkdir(); (out/'sentinel').write_text('keep')
            with self.assertRaises(ValueError): target.prepare_patch(src,out)
            with self.assertRaises(ValueError): target.prepare_patch(src,src/'out')
            self.assertEqual((out/'sentinel').read_text(),'keep')
    def test_modified_fixture_cannot_supply_candidate_code(self):
        with tempfile.TemporaryDirectory() as d:
            fixtures=Path(d)/'fixtures'; shutil.copytree(FIXTURES,fixtures)
            with (fixtures/'candidate/src/usb_cam.cpp').open('a') as f: f.write('tamper')
            with self.assertRaises(ValueError): target.prepare_patch(FIXTURES/'legacy',Path(d)/'out',fixtures)

if __name__=='__main__': unittest.main()
