import importlib.util
import os
import io
import json
import urllib.error
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('installer',Path(__file__).parent/'deploy/install.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class Deployment(unittest.TestCase):
    def test_config_input_accepts_windows_utf8_bom(self):
        source=io.TextIOWrapper(io.BytesIO(bytes([239,187,191])+b'{"token":"fixture"}'),encoding='utf-8')
        self.assertEqual(installer.read_settings(source),{'token':'fixture'})
    def test_config_input_errors_do_not_echo_input(self):
        for raw,stage in [('', 'CONFIG_INPUT_EMPTY'),('private-input','CONFIG_INPUT_JSON'),('[]','CONFIG_INPUT_TYPE')]:
            with self.subTest(stage=stage),self.assertRaises(RuntimeError) as caught:
                installer.read_settings(io.StringIO(raw))
            self.assertIn(stage,str(caught.exception))
            self.assertNotIn('private-input',str(caught.exception))
    def test_telegram_bad_json_retries_then_recovers(self):
        bad=io.BytesIO(b'<html>temporary response</html>')
        good=io.BytesIO(json.dumps({'ok':True,'result':{'username':'MagnitWaveBot'}}).encode())
        with patch.object(installer.urllib.request,'urlopen',side_effect=[bad,good]) as request,patch.object(installer.time,'sleep'),patch('sys.stdout',new_callable=io.StringIO):
            result=installer.telegram_result('fixture','getMe')
        self.assertEqual(result['username'],'MagnitWaveBot')
        self.assertEqual(request.call_count,2)
    def test_telegram_bad_json_has_clear_stage_without_url(self):
        with patch.object(installer.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(b'not-json')),patch.object(installer.time,'sleep'),patch('sys.stdout',new_callable=io.StringIO):
            with self.assertRaisesRegex(RuntimeError,'TELEGRAM_RESPONSE_JSON: getMe') as caught:
                installer.telegram_result('private-input','getMe')
        self.assertNotIn('private-input',str(caught.exception))
    def test_invalid_token_http_does_not_retry(self):
        error=urllib.error.HTTPError('https://example.invalid/private-input',401,'Unauthorized',{},None)
        with patch.object(installer.urllib.request,'urlopen',side_effect=error) as request,patch.object(installer.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'TELEGRAM_HTTP: getMe returned 401'):
                installer.telegram_result('fixture','getMe')
        self.assertEqual(request.call_count,1)
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
