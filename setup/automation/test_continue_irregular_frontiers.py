import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('wake',Path(__file__).with_name('continue_irregular_frontiers.py'))

class WakeGuardTests(unittest.TestCase):
    def test_completed_is_quiet_and_active_recent_is_not_duplicated(self):
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertFalse(module.should_resume({'status':'completed','heartbeat_epoch':0},1000))
        self.assertFalse(module.should_resume({'status':'running','heartbeat_epoch':950},1000))
        self.assertTrue(module.should_resume({'status':'pending','heartbeat_epoch':999},1000))
        self.assertTrue(module.should_resume({'status':'running','heartbeat_epoch':0},1000))
    def test_fail_closed_on_invalid_task_state(self):
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaises(ValueError):module.should_resume({'status':'typo'},1000)

class ContinuationPermissionTests(unittest.TestCase):
    def test_scheduled_continuation_uses_existing_chat_permissions(self):
        import json,os,tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            state=root/'state.json';state.write_text(json.dumps({'status':'pending'}))
            prompt=root/'setup/automation/irregular-frontiers-continuation.md'
            prompt.parent.mkdir(parents=True);prompt.write_text('continue authorized task')
            binary=root/'OpenAI/Codex/bin/test/codex.exe'
            binary.parent.mkdir(parents=True);binary.write_text('fixture only')
            with patch.object(module,'ROOT',root),patch.object(module,'STATE',state),patch.dict(os.environ,{'LOCALAPPDATA':str(root)}),patch.object(module.tempfile,'gettempdir',return_value=str(root)),patch.object(module.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run,patch('sys.argv',['guard']):
                module.main()
            command=run.call_args.args[0]
            self.assertEqual(command[1:4],['queue','--thread',module.SESSION])
            self.assertNotIn('--approve-for-me',command)
            self.assertNotIn('exec',command)
