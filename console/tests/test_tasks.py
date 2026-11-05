import threading,time,unittest
from console.target.tasks import TaskController

class FakeProcess:
    def __init__(self):self.exit=None;self.signals=[]
    def poll(self):return self.exit
    def send_signal(self,s):self.signals.append(s)

class TaskTests(unittest.TestCase):
    def wait(self,predicate):
        end=time.monotonic()+1
        while not predicate() and time.monotonic()<end:time.sleep(.005)
        self.assertTrue(predicate())
    def test_one_click_launches_once_and_space_returns_remote(self):
        calls=[];p=FakeProcess()
        c=TaskController(lambda:None,lambda current:calls.append('activate'),lambda:calls.append('spawn') or p,lambda:calls.append('halt'))
        c.start();self.wait(lambda:c.snapshot()['mode']=='autonomous');c.start()
        self.assertEqual(calls.count('spawn'),1)
        c.remote();self.assertEqual(c.snapshot()['mode'],'remote');self.assertEqual(len(p.signals),1)
        c.remote();self.assertEqual(len(p.signals),1)
        self.assertIn('halt',calls)
    def test_space_preempts_pending_start_and_old_worker_cannot_launch(self):
        entered=threading.Event();finish=threading.Event();calls=[]
        def activate(current):entered.set();finish.wait(.5)
        c=TaskController(lambda:None,activate,lambda:calls.append('spawn') or FakeProcess(),lambda:calls.append('halt'))
        c.start();self.assertTrue(entered.wait(.5));c.remote();finish.set()
        time.sleep(.03)
        self.assertEqual(c.snapshot()['mode'],'remote');self.assertNotIn('spawn',calls)
    def test_preflight_error_never_arms_or_launches(self):
        calls=[]
        def check():raise ValueError('control not configured')
        c=TaskController(check,lambda current:calls.append('arm'),lambda:calls.append('spawn'),lambda:None)
        with self.assertRaisesRegex(ValueError,'not configured'):c.start()
        self.assertEqual(calls,[]);self.assertEqual(c.snapshot()['mode'],'remote')
    def test_safety_stop_preserves_reason_until_explicit_operator_action(self):
        p=FakeProcess()
        c=TaskController(lambda:None,lambda current:None,lambda:p,lambda:None)
        c.start();self.wait(lambda:c.snapshot()['mode']=='autonomous')
        c.remote('tf_stale: odom_combined -> base_footprint')
        self.assertEqual(c.snapshot(),{'mode':'remote','error':'tf_stale: odom_combined -> base_footprint'})
        self.assertEqual(len(p.signals),1)
        c.remote();self.assertEqual(c.snapshot()['error'],'')

    def test_process_exit_holds_and_does_not_restart(self):
        calls=[];p=FakeProcess()
        c=TaskController(lambda:None,lambda current:None,lambda:p,lambda:calls.append('halt'))
        c.start();self.wait(lambda:c.snapshot()['mode']=='autonomous');p.exit=2
        self.assertEqual(c.snapshot()['mode'],'remote');self.assertIn('halt',calls)

class GearTests(unittest.TestCase):
    def test_middle_default_and_clamp_for_both_sources(self):
        from robot.safety import CommandSelector
        for source in ('manual','autonomy'):
            p=CommandSelector(.5);p.select(source);p.command(source,(.1,.3),1.)
            self.assertEqual(p.output(1.1),(.06,.18))
            p.set_gear(0);self.assertEqual(p.output(1.1),(.03,.09))
            p.set_gear(2);self.assertEqual(p.output(1.1),(.1,.3))
    def test_invalid_gear_does_not_raise_speed(self):
        from robot.safety import CommandSelector
        p=CommandSelector(.5)
        with self.assertRaises(ValueError):p.set_gear(3)
        self.assertEqual(p.gear,1)
    def test_space_during_preflight_cannot_be_undone_by_late_start(self):
        entered=threading.Event();finish=threading.Event();calls=[]
        def check():entered.set();finish.wait(.5)
        c=TaskController(check,lambda current:calls.append('activate'),lambda:FakeProcess(),lambda:None)
        worker=threading.Thread(target=c.start);worker.start();self.assertTrue(entered.wait(.5))
        c.remote();finish.set();worker.join(.5);time.sleep(.02)
        self.assertEqual(c.snapshot()['mode'],'remote');self.assertEqual(calls,[])


class TaskGatewayTests(unittest.TestCase):
    def test_task_actions_are_authenticated_and_allowlisted(self):
        import json
        from unittest.mock import patch, MagicMock
        from fastapi.testclient import TestClient
        from console.backend import app as gateway
        client=TestClient(gateway.app,base_url='http://127.0.0.1:8766')
        headers={'origin':'http://127.0.0.1:8766'}
        self.assertEqual(client.post('/api/v1/task',json={'action':'explore'},headers=headers).status_code,401)
        client.get('/bootstrap')
        fake=gateway.Session();fake.request=MagicMock(return_value=json.dumps({'mode':'remote','error':''}).encode())
        with patch.object(gateway,'session',fake):
            self.assertEqual(client.post('/api/v1/task',json={'action':'shell'},headers=headers).status_code,400)
            fake.request.assert_not_called()
            for action in ('explore','remote','stop'):
                self.assertEqual(client.post('/api/v1/task',json={'action':action},headers=headers).status_code,200)
                fake.request.assert_called_with('/task',{'action':action})
            self.assertEqual(client.post('/api/v1/task',json={'action':'explore'},headers={'origin':'http://evil.test'}).status_code,403)
            fake.maintenance='open'
            self.assertEqual(client.post('/api/v1/task',json={'action':'explore'},headers=headers).status_code,400)
            self.assertEqual(client.post('/api/v1/task',json={'action':'stop'},headers=headers).status_code,200)

    def test_stop_is_not_serialized_behind_a_slow_start(self):
        from console.backend.app import Session
        entered=threading.Event();finish=threading.Event();stopped=threading.Event()
        class SSH:
            def request(self,method,path,body,token):
                if path=='/task':entered.set();finish.wait(.5)
                else:stopped.set()
                return b'{}'
        session=Session();session.ssh=SSH()
        worker=threading.Thread(target=lambda:session.request('/task',{'action':'explore'}));worker.start()
        self.assertTrue(entered.wait(.5))
        stop=threading.Thread(target=lambda:session.request('/control',{'action':'stop'}));stop.start()
        try:self.assertTrue(stopped.wait(.1),'Space was blocked behind the exploration request')
        finally:finish.set();worker.join(.5);stop.join(.5)


class StableStartupTests(unittest.TestCase):
    def run_window(self, check, current=lambda:True):
        from console.target.tasks import wait_for_stable_readiness
        now=[0.]
        def sleep(seconds):now[0]+=seconds
        return wait_for_stable_readiness(current,lambda:check(now[0]),
            healthy_for=.5,timeout=1.5,clock=lambda:now[0],sleep=sleep)

    def test_single_fresh_sample_cannot_unlock_an_unstable_tf(self):
        with self.assertRaisesRegex(ValueError,'tf_stale'):
            self.run_window(lambda t:None if .1<=t<.2 else 'tf_stale: odom_combined -> base_footprint')

    def test_recovery_requires_a_continuous_healthy_window(self):
        checked=[]
        def check(t):
            checked.append(t)
            return 'tf_stale' if .15<t<.3 else None
        self.run_window(check)
        self.assertGreaterEqual(checked[-1],.8)

    def test_space_during_wait_cannot_finish_start(self):
        checked=[]
        with self.assertRaisesRegex(ValueError,'启动已取消'):
            self.run_window(lambda t:checked.append(t) or None,lambda:len(checked)<3)

    def test_preflight_failure_is_retained_in_task_state(self):
        def check():raise ValueError('tf_stale: map -> base_footprint')
        c=TaskController(check,lambda current:None,lambda:FakeProcess(),lambda:None)
        with self.assertRaises(ValueError):c.start()
        self.assertEqual(c.snapshot()['mode'],'remote')
        self.assertIn('tf_stale',c.snapshot()['error'])
