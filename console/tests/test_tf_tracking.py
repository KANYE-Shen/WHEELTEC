import threading,unittest
from types import SimpleNamespace
from console.target.data import tf_chain_fresh
from console.target.tf_buffer import TransformReceiptTracking


class MemoryBuffer:
    def __init__(self):self.values={}
    def set_transform(self,t,authority):
        if not authority:raise ValueError('rejected transform')
        self.values[t.child_frame_id]=t
    def set_transform_static(self,t,authority):
        if not authority:raise ValueError('rejected transform')
        self.values[t.child_frame_id]=t


class TrackedBuffer(TransformReceiptTracking,MemoryBuffer):pass


class TransformTrackingTests(unittest.TestCase):
    def setUp(self):
        self.edges={};self.now=10.;self.observed=[]
        def receive(t,static):
            self.assertIs(self.buffer.values[t.child_frame_id],t)
            self.edges[(t.header.frame_id,t.child_frame_id)]=(self.now,static)
            self.observed.append((t.child_frame_id,static))
        self.buffer=TrackedBuffer(on_transform=receive,receipt_lock=threading.RLock())

    def transform(self,parent,child):
        return SimpleNamespace(header=SimpleNamespace(frame_id=parent),child_frame_id=child)

    def test_one_tf_delivery_updates_buffer_and_liveness_together(self):
        self.buffer.set_transform(self.transform('odom','base'),'driver')
        self.buffer.set_transform_static(self.transform('base','laser'),'model')
        self.assertTrue(tf_chain_fresh(self.edges,'odom','laser',10.2))
        self.assertEqual(self.observed,[('base',False),('laser',True)])

    def test_frozen_dynamic_source_still_expires_but_static_transform_does_not(self):
        self.buffer.set_transform(self.transform('odom','base'),'driver')
        self.buffer.set_transform_static(self.transform('base','laser'),'model')
        self.assertFalse(tf_chain_fresh(self.edges,'odom','laser',12.))
        self.assertTrue(tf_chain_fresh(self.edges,'base','laser',12.))

    def test_rejected_buffer_update_never_renews_liveness(self):
        with self.assertRaises(ValueError):
            self.buffer.set_transform(self.transform('odom','base'),'')
        self.assertFalse(self.edges)

    def test_reading_buffer_does_not_keep_transform_alive(self):
        self.buffer.set_transform(self.transform('odom','base'),'driver')
        self.now=12.
        self.assertIsNotNone(self.buffer.values.get('base'))
        self.assertFalse(tf_chain_fresh(self.edges,'odom','base',self.now))
