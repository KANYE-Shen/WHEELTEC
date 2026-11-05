"""Map corrections must not depend on the arbitrary odometry origin."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

REPO = Path(__file__).resolve().parents[3]
if not (REPO/'src/wheeltec_explore/wheeltec_explore/node.py').is_file():
    REPO = Path('D:/虚拟c盘/WHEELTEC')
sys.path.insert(0, str(REPO/'src/wheeltec_explore'))
from wheeltec_explore.health import MapHealth

# Raw pair from the stationary read-only probe, not a reconstructed failed task.
A = (3.57699442167272, -8.433158720084625, -2.6710353071795847)
B = (4.029600613130116, -8.448200659135974, -2.5698253071795856)
P = (-2.3423635637766504, -3.7775565327068197)

def shifted(t, shift):
    c,s=math.cos(t[2]),math.sin(t[2])
    return (t[0]+c*shift[0]-s*shift[1],t[1]+s*shift[0]+c*shift[1],t[2])

class CorrectionReferenceTests(unittest.TestCase):
    def check_pair(self, a, b, p):
        h=MapHealth()
        h.map(10.,10.);h.scan(10.,10.);h.slam(True)
        h.transform(10.,10.,a,reference_xy=p)
        h.transform(10.1,10.1,b,reference_xy=p)
        return h.snapshot(10.1)

    def test_recorded_stationary_correction_is_invariant_to_odom_origin(self):
        base=self.check_pair(A,B,P)
        self.assertTrue(base['healthy'])
        self.assertAlmostEqual(base['max_translation_jump_m'],.0031999190903700303)
        for shift in ((0.,3.),(100.,-200.),(-9.,7.)):
            moved=self.check_pair(shifted(A,shift),shifted(B,shift),
                                  (P[0]-shift[0],P[1]-shift[1]))
            self.assertTrue(moved['healthy'])
            self.assertAlmostEqual(moved['max_translation_jump_m'],base['max_translation_jump_m'])

    def test_small_rotation_about_distant_robot_does_not_look_like_translation(self):
        angle=.13262;p=(4.6,0.)
        b=(p[0]*(1-math.cos(angle)),-p[0]*math.sin(angle),angle)
        self.assertGreater(math.hypot(*b[:2]),.5)
        result=self.check_pair((0.,0.,0.),b,p)
        self.assertTrue(result['healthy'])
        self.assertAlmostEqual(result['max_translation_jump_m'],0.)

    def test_real_robot_translation_over_unchanged_limit_still_latches(self):
        angle=.13262;p=(4.6,0.)
        b=(p[0]*(1-math.cos(angle))+.6,-p[0]*math.sin(angle),angle)
        result=self.check_pair((0.,0.,0.),b,p)
        fault=result['faults']['map_to_odom_translation_jump']
        self.assertAlmostEqual(fault['magnitude'],.6)
        self.assertEqual(fault['limit'],.5)
        self.assertEqual(list(fault['reference_xy']),list(p))
        self.assertIn('previous_pose',fault)
        self.assertIn('current_pose',fault)

    def test_pivot_near_odom_origin_can_hide_real_displacement_at_robot(self):
        result=self.check_pair((0.,0.,0.),(0.,0.,.2),(4.,0.))
        self.assertIn('map_to_odom_translation_jump',result['issues'])

    def test_large_rotation_still_stops_at_robot_pivot(self):
        angle=.36;p=(4.6,0.)
        result=self.check_pair((0.,0.,0.),(p[0]*(1-math.cos(angle)),-p[0]*math.sin(angle),angle),p)
        self.assertIn('map_to_odom_rotation_jump',result['issues'])

    def test_nonfinite_reference_fails_closed(self):
        result=self.check_pair(A,B,(float('nan'),0.))
        self.assertFalse(result['healthy'])

class HealthTickReferenceTests(unittest.TestCase):
    def node(self, odom_stamp=10., missing=False):
        def transform(p,stamp):
            return NS(header=NS(stamp=NS(sec=int(stamp),nanosec=int((stamp-int(stamp))*1e9))),
                transform=NS(translation=NS(x=p[0],y=p[1]),
                    rotation=NS(w=math.cos(p[2]/2),z=math.sin(p[2]/2),x=0.,y=0.)))
        class MissingTransform(Exception): pass
        current=[shifted(A,(0.,3.))]
        calls=[]
        def lookup(target,source,stamp):
            calls.append((target,source))
            if target=='map':return transform(current[0],10.)
            if missing:raise MissingTransform()
            return transform((P[0],P[1]-3.,0.),odom_stamp)
        n=NS(config={'map_frame':'map','odom_frame':'odom_combined','base_frame':'base_footprint',
                     'tf_max_age':1.,'future_tolerance':.1},
             tf=NS(lookup_transform=lookup),ros_seconds=lambda:10.,
             get_node_names=lambda:['slam_toolbox'],health=MapHealth(),health_active=True,health_latched={})
        n.health.map(10.,10.);n.health.scan(10.,10.)
        tree=ast.parse((REPO/'src/wheeltec_explore/wheeltec_explore/node.py').read_text(encoding='utf-8'))
        cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Explorer')
        method=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='health_tick')
        env={'Time':lambda:None,'TransformException':MissingTransform,'math':math,
             'yaw':lambda q:2*math.atan2(q.z,q.w)}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'actual_health_tick','exec'),env)
        n.health_tick=env['health_tick'].__get__(n)
        return n,current,calls

    def test_actual_health_tick_uses_fresh_base_reference(self):
        n,current,calls=self.node()
        self.assertTrue(n.health_tick()['healthy'])
        current[0]=shifted(B,(0.,3.));n.ros_seconds=lambda:10.1
        # Advance transform stamps together to exercise the real callback.
        old=n.tf.lookup_transform
        def lookup(*args):
            t=old(*args);t.header.stamp.nanosec=100_000_000;return t
        n.tf.lookup_transform=lookup
        self.assertTrue(n.health_tick()['healthy'])
        self.assertIn(('odom_combined','base_footprint'),calls)
        self.assertFalse(n.health_latched)

    def test_stale_odom_reference_prevents_health_even_with_fresh_map_tf(self):
        n,_,_=self.node(odom_stamp=8.)
        self.assertFalse(n.health_tick()['healthy'])
        self.assertTrue(n.health_latched)

    def test_missing_odom_reference_prevents_health(self):
        n,_,_=self.node(missing=True)
        self.assertFalse(n.health_tick()['healthy'])
        self.assertTrue(n.health_latched)

if __name__=='__main__':unittest.main()
