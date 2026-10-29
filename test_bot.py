import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import bot


class BotFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = bot.DB_PATH
        bot.DB_PATH = str(Path(self.tmp.name) / 'test.sqlite3')
        self.old_local = bot.LOCAL
        bot.LOCAL = threading.local()
        self.old_state = bot.STATE.copy()
        self.sent = []
        self.api = patch.object(bot, 'api', side_effect=self.telegram).start()

    def tearDown(self):
        patch.stopall()
        if getattr(bot.LOCAL, 'conn', None):
            bot.LOCAL.conn.close()
        bot.LOCAL = self.old_local
        bot.DB_PATH = self.old_path
        bot.STATE.clear()
        bot.STATE.update(self.old_state)
        self.tmp.cleanup()

    def telegram(self, method, payload):
        self.sent.append((method, payload))
        return {'message_id': len(self.sent)} if method == 'sendMessage' else True

    def message(self, text):
        bot.handle({'update_id': 1, 'message': {'message_id': 1,
                   'from': {'id': 71}, 'chat': {'id': 71, 'type': 'private'}, 'text': text}})

    def callback(self, data):
        bot.handle({'update_id': 2, 'callback_query': {'id': 'cb', 'from': {'id': 71},
                   'message': {'chat': {'id': 71, 'type': 'private'}}, 'data': data}})

    def test_start_incoming_update_sends_menu_and_tracks_reply(self):
        before = bot.STATE['replies']
        self.message('/start')
        self.assertEqual(self.sent[-1][0], 'sendMessage')
        self.assertEqual(self.sent[-1][1]['chat_id'], 71)
        self.assertIn('MAGNIT', self.sent[-1][1]['text'])
        self.assertTrue(self.sent[-1][1]['reply_markup']['inline_keyboard'])
        self.assertEqual(bot.STATE['replies'], before + 1)

    def test_incoming_buttons_open_close_and_replay_does_not_credit_twice(self):
        self.message('/start')
        self.callback('open:100')
        self.assertEqual(bot.user(71)['balance'], 9900)
        self.callback('close:1:10')
        self.assertEqual(bot.user(71)['balance'], 10010)
        self.callback('close:1:10')
        self.assertEqual(bot.user(71)['balance'], 10010)

    def test_language_and_deep_link_start(self):
        self.message('/start@MagnitWaveBot referral')
        self.callback('language')
        self.assertEqual(bot.lang(71), 'ru')
        self.message('/start')
        self.assertIn('МАГНИТ', self.sent[-1][1]['text'])

    def test_failed_send_is_not_counted_as_a_reply(self):
        before = bot.STATE['replies']
        self.api.side_effect = lambda *_: None
        self.message('/start')
        self.assertEqual(bot.STATE['replies'], before)

    def test_health_requires_a_recent_successful_poll_and_reports_revision(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), bot.Health)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = 'http://127.0.0.1:%s/health' % server.server_port
        try:
            bot.STATE.update(ok=True, last_poll=0)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(url)
            self.assertEqual(caught.exception.code, 503)
            bot.STATE['last_poll'] = time.time()
            with patch.dict(bot.CFG, revision='revision-under-test'):
                with urllib.request.urlopen(url) as response:
                    data = json.load(response)
                self.assertTrue(data['ok'])
                self.assertEqual(data['revision'], 'revision-under-test')
            bot.STATE['last_poll'] = time.time() - 100
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


class Startup(unittest.TestCase):
    def test_config_argument_is_read_outside_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'settings.json'
            config.write_text(json.dumps({'revision': 'config-loaded', 'health_port': 8769}))
            code = ('import sys; sys.argv=["bot.py","--config",sys.argv[1]]; '
                    'import bot; print(bot.CFG.get("revision"),bot.HEALTH_PORT)')
            result = subprocess.run([sys.executable, '-c', code, str(config)],
                                    cwd=Path(__file__).parent, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'config-loaded 8769')

    def test_polling_conflict_is_visible_without_printing_the_request_url(self):
        error = urllib.error.HTTPError('https://example.invalid/private', 409, 'Conflict', {}, io.BytesIO())
        with patch.object(bot.urllib.request, 'urlopen', side_effect=error), patch('sys.stdout', new_callable=io.StringIO) as log:
            self.assertIsNone(bot.api('getUpdates', {}))
            self.assertIn('409', log.getvalue())
            self.assertNotIn('example.invalid', log.getvalue())


if __name__ == '__main__':
    unittest.main()
