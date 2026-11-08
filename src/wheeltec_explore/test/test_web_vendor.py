"""Focused contracts for managed vendor exploration used by the web task."""
import ast
import math
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from wheeltec_explore.vendor_runtime import VendorProcesses, map_sampling_bounds

ROOT = Path(__file__).resolve().parents[3]

def info(width=100, height=80, yaw=0.):
    return NS(width=width,height=height,resolution=.05,
              origin=NS(position=NS(x=-2.,y=-1.),
                        orientation=NS(x=0.,y=0.,z=math.sin(yaw/2),w=math.cos(yaw/2))))

class WebVendorTests(unittest.TestCase):
    def test_map_bounds_track_size_and_reject_rotation(self):
        for actual, expected in zip(map_sampling_bounds(info()),(-1.975,-.975,2.975,2.975)):
            self.assertAlmostEqual(actual, expected)
        self.assertGreater(map_sampling_bounds(info(width=120))[2],map_sampling_bounds(info())[2])
        with self.assertRaisesRegex(ValueError,'旋转'): map_sampling_bounds(info(yaw=.1))

    def test_web_spawn_requests_managed_vendor_and_keeps_existing_gate(self):
        tree=ast.parse((ROOT/'console/target/adapter.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='spawn_exploration')
        source=ast.unparse(fn)
        for item in ('frontier_backend:=vendor','vendor_managed:=true','WHEELTEC_CONSOLE_START_GATE',
                     'footprint_exclusion_radius:=','map_output:='):
            self.assertIn(item,source)

    def test_vendor_processes_own_a_single_supervisor(self):
        commands=[]
        class Child:
            def __init__(self,cmd,**kwargs):
                commands.append(cmd);self.pid=101;self.done=False
                assert kwargs['start_new_session'] is True
            def poll(self):return 0 if self.done else None
            def wait(self,timeout=None):self.done=True;return 0
        with patch('wheeltec_explore.vendor_runtime.subprocess.Popen',side_effect=Child), \
             patch('wheeltec_explore.vendor_runtime.os.killpg',create=True) as kill:
            runtime=VendorProcesses();runtime.start();runtime.check();runtime.stop()
            self.assertEqual(commands[0][1:3],['-m','wheeltec_explore.vendor_supervisor'])
            self.assertEqual(kill.call_count,1)

    def test_managed_prepare_restarts_when_map_changes(self):
        tree=ast.parse((ROOT/'src/wheeltec_explore/wheeltec_explore/node.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Explorer')
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='prepare_managed_vendor')
        # Run the actual method in the package namespace so its relative import works.
        env={'__name__':'wheeltec_explore.node','__package__':'wheeltec_explore'}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'managed_prepare','exec'),env)
        events=[]
        from concurrent.futures import ThreadPoolExecutor
        import threading
        class Runtime:
            def start(self):
                self_test.assertIs(threading.current_thread(),threading.main_thread())
                events.append('start')
            def check(self):events.append('check')
            def stop(self):
                self_test.assertIsNot(threading.current_thread(),threading.main_thread())
                events.append('stop')
        self_test=self
        obj=NS(latest_map=NS(info=info()),vendor_initialized=False,vendor_runtime=None,
               vendor_map_bounds=None,vendor_points=(),vendor_received=None,config={},
               boundary_pub=NS(get_subscription_count=lambda:0),
               get_publishers_info_by_topic=lambda topic:[],wait=lambda predicate,*a,**k:predicate())
        def initialize(pose):events.append('initialize');obj.vendor_initialized=True
        obj.initialize_vendor=initialize
        def run_operation(operation):
            with ThreadPoolExecutor(max_workers=1) as worker:
                return worker.submit(operation).result()
        obj.run_vendor_operation=run_operation
        with patch('wheeltec_explore.vendor_runtime.VendorProcesses',Runtime):
            env['prepare_managed_vendor'](obj,(0,0,0))
            env['prepare_managed_vendor'](obj,(0,0,0))
            obj.latest_map.info=info(width=120)
            env['prepare_managed_vendor'](obj,(0,0,0))
        self.assertEqual(events,['start','initialize','check','stop','start','initialize'])


    def test_vendor_process_operation_spins_callbacks_while_worker_waits(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        tree=ast.parse((ROOT/'src/wheeltec_explore/wheeltec_explore/node.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Explorer')
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='run_vendor_operation')
        env={'ThreadPoolExecutor':ThreadPoolExecutor}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'vendor_operation','exec'),env)
        signal=threading.Event(); callbacks=[]
        def wait(predicate,timeout,**kwargs):
            callbacks.append(kwargs);signal.set()
            return bool(signal.wait(1.))
        node=NS(wait=wait,wait_reason='')
        result=env['run_vendor_operation'](node,lambda:signal.wait(1.))
        self.assertTrue(result)
        self.assertEqual(callbacks,[{'check_task':True,'check_sensors':True}])

    def test_vendor_prepares_before_web_release_and_stops_on_cancel(self):
        from wheeltec_explore.startup import wait_for_console_start
        import os
        import tempfile
        tree=ast.parse((ROOT/'src/wheeltec_explore/wheeltec_explore/node.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[]
        runtime=NS(stop=lambda:calls.append('stop'))
        node=NS(latest_map=object(),position=lambda:(0,0,0),last_scan_ros=1.,ros_seconds=lambda:1.,
                config={'scan_max_age':1.,'initialization_timeout':5.,'frontier_backend':'vendor','vendor_managed':True},
                nav=NS(server_is_ready=lambda:True),vendor_runtime=runtime,
                wait=lambda predicate,timeout:predicate(),
                prepare_managed_vendor=lambda pose:calls.append('vendor_ready'),
                run=lambda:calls.append('run'),cancel_active=lambda:calls.append('cancel'),
                status=lambda *a,**k:None,destroy_node=lambda:None)
        def spin(*args,**kwargs):
            calls.append('spin')
            raise KeyboardInterrupt()
        env={'rclpy':NS(init=lambda **k:None,ok=lambda:True,shutdown=lambda:None,spin_once=spin),
             'SignalHandlerOptions':NS(NO=0),'Explorer':lambda:node,'os':os,
             'observation_fresh':lambda *a:True,'wait_for_console_start':wait_for_console_start,
             'MapUnstableError':type('HealthError',(Exception,),{})}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual_vendor_main','exec'),env)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'WHEELTEC_CONSOLE_START_GATE':directory}):
            self.assertEqual(env['main'](),130)
        self.assertEqual(calls,['vendor_ready','spin','cancel','stop'])

if __name__=='__main__':unittest.main()
