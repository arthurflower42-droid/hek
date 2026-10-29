import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('installer',Path(__file__).parent/'deploy/install.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class Deployment(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Linux deployment check')
    def test_hook_is_valid_shell(self):
        result=subprocess.run(['bash','-n'],input=installer.HOOK,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('unset GIT_DIR',installer.HOOK)
        self.assertIn('--existing',installer.HOOK)
    def test_invalid_token_fails_before_network(self):
        with patch.object(installer.urllib.request,'urlopen') as request:
            with self.assertRaises(RuntimeError):installer.verify({'token':'fixture'})
            request.assert_not_called()
    @unittest.skipUnless(os.name == 'posix', 'Linux deployment check')
    def test_atomic_config_write_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json'
            installer.atom(path,'first',0o640);installer.atom(path,'second',0o640)
            self.assertEqual(path.read_text(),'second')
            self.assertEqual(path.stat().st_mode & 0o777,0o640)
            self.assertFalse(path.with_name('config.json.new').exists())
    @unittest.skipUnless(os.name == 'posix', 'Linux deployment check')
    def test_atomic_release_switch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(installer,'ROOT',Path(tmp)):
            first=Path(tmp)/'one';second=Path(tmp)/'two';first.mkdir();second.mkdir()
            installer.select(first);installer.select(second)
            self.assertEqual((Path(tmp)/'current').resolve(),second)
            self.assertFalse((Path(tmp)/'current.new').exists())
    def test_unit_has_separate_user_and_local_paths(self):
        self.assertIn('User=magnit',installer.SERVICE)
        self.assertIn('ReadWritePaths=/var/lib/magnit',installer.SERVICE)
        self.assertNotIn('peretosh',installer.SERVICE)

if __name__=='__main__':unittest.main()
