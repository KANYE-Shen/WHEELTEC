"""Runtime regressions for evaluator clock ordering and independent truth arrival."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
import truth_capture


class TruthWorkerIsolationTests(unittest.TestCase):
    def test_parent_gil_stall_does_not_become_truth_arrival_gap(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            fixture=folder/'ign'
            fixture.write_text('#!'+sys.executable+'\n'+'''import json,signal,sys,time
signal.signal(signal.SIGINT,lambda *args:sys.exit(0))
start=time.monotonic()
while True:
 t=time.monotonic()-start
 print(json.dumps({'header':{'stamp':{'sec':int(t),'nsec':int(t%1*1e9)}},'pose':[{'name':'wheeltec_reference','position':{},'orientation':{'w':1}}]}),flush=True)
 time.sleep(.02)
''')
            fixture.chmod(0o755)
            with patch.dict(os.environ,{'PATH':str(folder)+os.pathsep+os.environ['PATH']}):
                capture=truth_capture.GazeboTruthCapture('truth-unit-fixture',time.monotonic(),folder/'reader.log')
            samples=[]
            try:
                time.sleep(.25)
                samples.extend(capture.drain())
                self.assertGreaterEqual(len(samples),3)
                previous=sys.getswitchinterval()
                try:
                    sys.setswitchinterval(2.0)
                    until=time.perf_counter()+.85
                    while time.perf_counter()<until:
                        pass
                finally:
                    sys.setswitchinterval(previous)
                time.sleep(.1)
                samples.extend(capture.drain())
            finally:
                if capture.process.poll() is None:
                    os.killpg(capture.process.pid,signal.SIGINT)
                capture.process.wait(timeout=5)
                capture.close()
            gaps=[b['wall_t']-a['wall_t'] for a,b in zip(samples,samples[1:])]
            self.assertLessEqual(max(gaps),.5,'parent held GIL; truth arrival must be captured independently')
            self.assertEqual(capture.diagnostics()['parse_errors'],0)
            self.assertIsNone(capture.diagnostics()['reader_error'])


class TerminalClockSynchronizationTests(unittest.TestCase):
    def fixture(self,mode):
        state={'wall':10.4,'sim':.011,'polls':0}
        samples=[{'t':i*.02,'wall_t':10+i*.02,'pose':[0,0,0]} for i in range(21)]
        def spin(timeout):
            state['wall']+=timeout
            if mode!='clock_stopped':
                state['sim']=state['wall']-10
        def poll():
            state['polls']+=1
            if mode in ('healthy','clock_stopped') and state['wall']>samples[-1]['wall_t']+.019:
                samples.append({'t':state['wall']-10,'wall_t':state['wall'],'pose':[0,0,0]})
            if mode=='regressed' and state['polls']==2:
                samples.append({'t':.1,'wall_t':state['wall'],'pose':[0,0,0]})
        return state,samples,spin,poll

    def assess(self,mode):
        state,samples,spin,poll=self.fixture(mode)
        finish=truth_capture.synchronize_terminal_truth
        result=finish(samples,poll,spin,lambda:state['sim'],0,10,monotonic=lambda:state['wall'])
        return result,state

    def test_lagging_clock_catches_up_with_new_truth_under_original_limits(self):
        result,state=self.assess('healthy')
        self.assertTrue(result['valid'],result['issues'])
        self.assertLessEqual(state['wall']-10.4,2.000001)
        self.assertEqual(result['limits']['maximum_wall_gap_s'],.5)
        self.assertEqual(result['limits']['future_tolerance_s'],.1)

    def test_clock_catchup_cannot_reuse_a_stopped_truth_stream(self):
        result,state=self.assess('truth_stopped')
        self.assertFalse(result['valid'])
        self.assertLessEqual(state['wall']-10.4,2.000001)

    def test_stopped_clock_or_regressed_truth_stays_invalid(self):
        for mode in ('clock_stopped','regressed'):
            with self.subTest(mode=mode):
                result,state=self.assess(mode)
                self.assertFalse(result['valid'])
                self.assertLessEqual(state['wall']-10.4,2.000001)



class TruthSpoolBoundaryTests(unittest.TestCase):
    def test_partial_lines_are_retained_and_complete_samples_are_not_duplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            capture=truth_capture.GazeboTruthCapture.__new__(truth_capture.GazeboTruthCapture)
            capture.sample_path=Path(directory)/'samples.jsonl'
            capture._stream=None
            capture._partial=b''
            capture._consumer_errors=0
            capture.error=None
            try:
                capture.sample_path.write_bytes(b'{"t":1')
                self.assertEqual(capture.drain(),[])
                with capture.sample_path.open('ab') as stream:
                    stream.write(b',"wall_t":2,"pose":[0,0,0]}\n{"t":2')
                self.assertEqual(capture.drain(),[{'t':1,'wall_t':2,'pose':[0,0,0]}])
                self.assertEqual(capture.drain(),[])
                with capture.sample_path.open('ab') as stream:
                    stream.write(b',"wall_t":3,"pose":[0,0,0]}\n')
                self.assertEqual(capture.drain(),[{'t':2,'wall_t':3,'pose':[0,0,0]}])
                self.assertEqual(capture._partial,b'')
            finally:
                if capture._stream is not None:
                    capture._stream.close()

    def test_bad_native_json_and_unexpected_exit_are_visible_failures(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            fixture=folder/'ign'
            fixture.write_text('#!'+sys.executable+'\nprint("{malformed",flush=True)\n')
            fixture.chmod(0o755)
            with patch.dict(os.environ,{'PATH':str(folder)+os.pathsep+os.environ['PATH']}):
                capture=truth_capture.GazeboTruthCapture('truth-unit-fixture',time.monotonic(),folder/'reader.log')
            try:
                capture.process.wait(timeout=5)
                self.assertEqual(capture.drain(),[])
            finally:
                capture.close()
            report=capture.diagnostics()
            self.assertEqual(report['parse_errors'],1)
            self.assertIn('before owned shutdown',report['reader_error'])
            self.assertNotEqual(capture.process.returncode,0)


class OwnedGroupCleanupTests(unittest.TestCase):
    @staticmethod
    def live(pid):
        try:
            return Path('/proc/'+str(pid)+'/stat').read_text().rpartition(')')[2].split()[0] not in ('Z','X')
        except FileNotFoundError:
            return False

    def test_native_is_cleaned_even_when_owned_worker_leader_already_died(self):
        import subprocess
        from check_exploration import stop_owned
        with tempfile.TemporaryDirectory() as directory:
            ready=Path(directory)/'native.pid'
            native_code='import os,time;from pathlib import Path;Path('+repr(str(ready))+').write_text(str(os.getpid()));time.sleep(60)'
            leader_code='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(native_code)+']);time.sleep(60)'
            leader=subprocess.Popen([sys.executable,'-c',leader_code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                deadline=time.monotonic()+3
                while not ready.is_file() and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertTrue(ready.is_file())
                native_pid=int(ready.read_text())
                os.kill(leader.pid,signal.SIGKILL)
                leader.wait(timeout=3)
                self.assertTrue(self.live(native_pid),'fixture must leave a live native child')
                report=stop_owned(leader)
                self.assertFalse(self.live(native_pid),'leader exit must not skip owned descendant cleanup')
                self.assertEqual(report['returncode'],-signal.SIGKILL)
            finally:
                try:
                    os.killpg(leader.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                leader.wait(timeout=3)

    def test_sigint_ignoring_native_is_killed_within_the_owned_group(self):
        import subprocess
        from check_exploration import stop_owned
        with tempfile.TemporaryDirectory() as directory:
            ready=Path(directory)/'native.pid'
            native_code='import os,signal,time;from pathlib import Path;signal.signal(signal.SIGINT,signal.SIG_IGN);Path('+repr(str(ready))+').write_text(str(os.getpid()));time.sleep(60)'
            leader_code='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(native_code)+']);time.sleep(60)'
            leader=subprocess.Popen([sys.executable,'-c',leader_code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                deadline=time.monotonic()+3
                while not ready.is_file() and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertTrue(ready.is_file())
                native_pid=int(ready.read_text())
                os.kill(leader.pid,signal.SIGKILL)
                leader.wait(timeout=3)
                report=stop_owned(leader,timeout=.2)
                self.assertFalse(self.live(native_pid))
                self.assertTrue(report['forced_kill'])
                self.assertEqual(report['remaining_live_group_members'],[])
                self.assertEqual(report['returncode'],-signal.SIGKILL)
            finally:
                try:
                    os.killpg(leader.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                leader.wait(timeout=3)


if __name__=='__main__':
    unittest.main()