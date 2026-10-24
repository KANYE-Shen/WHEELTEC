"""ROS-free tests for restoring simulator layout alongside a saved user map."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import room_session
        except ImportError:
            room_session=None
        cls.session=room_session

    def setUp(self):
        self.assertIsNotNone(self.session,'room_session must resolve saved-map scenario identity')
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.maps=self.root/'maps'
        self.maps.mkdir()
        self.map=self.maps/'room.yaml'
        self.map.write_text('image: room.pgm')
        (self.maps/'latest.json').write_text(json.dumps({'map_yaml':str(self.map)}))

    def test_latest_map_restores_layout_spawn_and_source_hash(self):
        sidecar={'version':1,'scenario':'l_shape','spawn_index':2,
                 'scenario_sha256':self.session.scenario_hash('l_shape')}
        self.map.with_suffix('.simulation.json').write_text(json.dumps(sidecar))
        resolved=self.session.resolve_session(['mode:=localization'],self.root)
        self.assertEqual(resolved['scenario'],'l_shape')
        self.assertEqual(resolved['spawn'],2)
        self.assertEqual(resolved['map'],self.map)

    def test_old_map_keeps_legacy_world_and_does_not_modify_user_files(self):
        before={p.name:p.read_bytes() for p in self.maps.iterdir()}
        resolved=self.session.resolve_session(['mode:=localization'],self.root)
        self.assertIsNone(resolved['scenario'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.maps.iterdir()})

    def test_explicit_scenario_overrides_saved_identity_but_mismatched_hash_is_not_silent(self):
        sidecar={'version':1,'scenario':'l_shape','spawn_index':2,'scenario_sha256':'changed'}
        self.map.with_suffix('.simulation.json').write_text(json.dumps(sidecar))
        with self.assertRaisesRegex(ValueError,'hash'):
            self.session.resolve_session(['mode:=localization'],self.root)
        resolved=self.session.resolve_session(['mode:=localization','scenario:=clutter','spawn:=1'],self.root)
        self.assertEqual((resolved['scenario'],resolved['spawn']),('clutter',1))

    def test_normal_explore_preassigns_map_and_recording_and_rejects_overwriting_sidecar(self):
        resolved=self.session.resolve_session(['explore:=true'],self.root)
        self.assertEqual(resolved['scenario'],'baseline')
        self.session.prepare_exploration(resolved,self.root,stamp='unit-test')
        self.assertTrue(resolved['run_dir'].is_dir())
        sidecar=resolved['map_output'].with_suffix('.simulation.json')
        self.assertEqual(json.loads(sidecar.read_text())['scenario'],'baseline')
        before=sidecar.read_bytes()
        with self.assertRaises(FileExistsError):
            self.session.prepare_exploration(self.session.resolve_session(['explore:=true'],self.root),self.root,stamp='unit-test')
        self.assertEqual(sidecar.read_bytes(),before)

    def test_nonexplore_validation_launch_has_no_session_recording(self):
        resolved=self.session.resolve_session(['mode:=mapping','ros_domain_id:=83'],self.root)
        self.assertNotIn('run_dir',resolved)
        self.assertIsNone(resolved['scenario'])



class ActiveSessionTests(unittest.TestCase):
    def setUp(self):
        import os
        import room_session
        self.session=room_session
        self.assertTrue(hasattr(room_session,'register_session'),'Manual map saves need a validated current-session identity registry')
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.proc=self.root/'proc'
        self.pid=4321
        (self.proc/str(self.pid)).mkdir(parents=True)
        # /proc stat command names may contain spaces; starttime is field 22.
        (self.proc/str(self.pid)/'stat').write_text(str(self.pid)+' (ros2 launch name) S '+'0 '*18+'9988 0 0')
        self.lock=self.root/'room77.lock'
        self.lock.touch()
        stat=self.lock.stat()
        (self.proc/'locks').write_text(f'1: FLOCK ADVISORY WRITE {self.pid} {os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}:{stat.st_ino} 0 EOF\n')
        self.resolved=room_session.resolve_session(['mode:=mapping','scenario:=l_shape','spawn:=2'],self.root)
        room_session.register_session(self.resolved,self.root,'77',self.lock,owner_pid=self.pid,proc_root=self.proc)

    def active(self):
        return self.session.active_session(self.root,'77',self.lock,proc_root=self.proc)

    def test_manual_save_copies_active_world_identity_and_localization_restores_it(self):
        from save_map import write_record
        current=self.active()
        output=self.root/'maps/new/room'
        output.parent.mkdir(parents=True)
        output.with_suffix('.yaml').write_text('image: room.pgm')
        record={'map_yaml':str(output.with_suffix('.yaml'))}
        write_record(output,record,self.root,'77',current,lock_path=self.lock,proc_root=self.proc)
        sidecar=json.loads(output.with_suffix('.simulation.json').read_text())
        self.assertEqual((sidecar['scenario'],sidecar['spawn_index']),('l_shape',2))
        restored=self.session.resolve_session(['mode:=localization'],self.root)
        self.assertEqual((restored['scenario'],restored['spawn']),('l_shape',2))

    def test_stale_registry_with_exited_or_reused_owner_is_not_active(self):
        stat=self.proc/str(self.pid)/'stat'
        original=stat.read_text()
        stat.unlink()
        self.assertIsNone(self.active())
        stat.write_text(original.replace('9988','9989'))
        self.assertIsNone(self.active())

    def test_live_owner_without_its_matching_lock_is_not_active(self):
        (self.proc/'locks').write_text('')
        self.assertIsNone(self.active())

    def test_session_change_during_save_does_not_publish_latest_or_wrong_sidecar(self):
        from save_map import write_record
        current=self.active()
        (self.proc/'locks').write_text('')
        output=self.root/'maps/new/room'
        output.parent.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError,'session changed'):
            write_record(output,{},self.root,'77',current,lock_path=self.lock,proc_root=self.proc)
        self.assertFalse((self.root/'maps/latest.json').exists())
        self.assertFalse(output.with_suffix('.simulation.json').exists())

    def test_original_default_world_also_has_explicit_baseline_identity(self):
        resolved=self.session.resolve_session(['mode:=mapping'],self.root)
        self.session.register_session(resolved,self.root,'77',self.lock,owner_pid=self.pid,proc_root=self.proc)
        self.assertEqual(self.active()['simulation']['scenario'],'baseline')


class LiveLockTests(unittest.TestCase):
    def test_registry_survives_exec_and_becomes_inactive_after_owner_exit(self):
        import os
        import subprocess
        import sys
        import time
        from room_session import active_session
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            lock=root/'session.lock'
            code='''import fcntl,os,sys
from pathlib import Path
from room_session import register_session,resolve_session
root=Path(sys.argv[1]); lock=root/'session.lock'
fd=os.open(str(lock),os.O_CREAT|os.O_RDWR,0o600)
fcntl.flock(fd,fcntl.LOCK_EX); os.set_inheritable(fd,True)
register_session(resolve_session(['scenario:=l_shape','spawn:=1'],root),root,77,lock)
os.execv(sys.executable,[sys.executable,'-c','import time; time.sleep(60)'])
'''
            child=subprocess.Popen([sys.executable,'-c',code,folder],cwd=Path(__file__).resolve().parent)
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    command=Path('/proc',str(child.pid),'cmdline')
                    if command.exists() and command.read_bytes().split(b'\0')[:-1] == [os.fsencode(sys.executable),b'-c',b'import time; time.sleep(60)'] and (root/'sessions/domain-77.json').exists():
                        break
                    time.sleep(.02)
                else:
                    self.fail('Child did not reach the exact post-exec argv before deadline')
                current=active_session(root,77,lock)
                self.assertIsNotNone(current,'Inherited launch lock must remain attributable after exec')
                self.assertEqual(current['owner_pid'],child.pid)
                self.assertEqual(current['simulation']['scenario'],'l_shape')
            finally:
                child.terminate()
                child.wait(timeout=5)
            self.assertTrue((root/'sessions/domain-77.json').exists())
            self.assertIsNone(active_session(root,77,lock),'Residual registry must be rejected after owner exits')

if __name__=='__main__':
    unittest.main()
