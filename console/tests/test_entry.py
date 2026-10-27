import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class EntryTests(unittest.TestCase):
    def test_installation_check_works_outside_repository(self):
        script=Path('console/start.py').resolve()
        with tempfile.TemporaryDirectory() as folder:
            result=subprocess.run([sys.executable,'-I',str(script),'--check'],cwd=folder,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Console installation check passed',result.stdout)
