import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import bot

class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls, self.updates = [], []
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
                method = self.path.rsplit('/',1)[-1]
                outer.calls.append((method,data))
                value = True
                if method=='getMe': value={'username':'MagnitWaveBot'}
                if method=='getWebhookInfo': value={'url':''}
                if method=='getUpdates': value=outer.updates
                if method=='sendMessage': value={'message_id':12}
                self.respond({'ok':True,'result':value})
            def do_GET(self):
                if self.path.startswith('/price'):
                    data={v:{'usd':123.45,'rub':10000,'eur':110,'usd_24h_change':2.5,
                          'last_updated_at':int(time.time())} for v in bot.COINS.values()}
                    self.respond(data)
                elif self.path.startswith('/music'):
                    self.respond({'results':[{'artistName':'A & B','trackName':'Track',
                        'trackViewUrl':'https://music.apple.com/us/song/test/1'},
                        {'artistName':'bad','trackViewUrl':'javascript:alert(1)'}]})
                else:
                    body=b'<rss><channel><item><title>News &amp; test</title><link>https://example.com/news</link><pubDate>Thu, 29 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
                    self.send_response(200);self.end_headers();self.wfile.write(body)
            def respond(self,data):
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            def log_message(self,*args): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        base='http://127.0.0.1:'+str(self.server.server_port)
        self.config={'token':'fixture', 'database':self.tmp.name+'/db.sqlite', 'telegram_base':base,
            'price_base':base+'/price', 'music_base':base+'/music',
            'feeds':{'world':[['Fixture',base+'/rss']], 'crypto':[['Fixture',base+'/rss']]}}
        self.b=bot.Bot(self.config)
    def tearDown(self):
        self.b.store.db.close();self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def update(self,text, uid=10, typ='private'):
        return {'update_id':1,'message':{'chat':{'id':uid,'type':typ},'from':{'id':uid},'text':text}}
    def send(self,text,uid=10):
        self.b.rates.clear();self.b.handle(self.update(text,uid))
        return [d for m,d in self.calls if m=='sendMessage'][-1]
    def test_incoming_update_subprocess(self):
        # Actual process -> HTTP getUpdates -> dispatcher -> HTTP sendMessage -> durable cursor.
        self.updates=[self.update('/start'),dict(self.update('/crypto',11),update_id=2),
                      dict(self.update('/news',12),update_id=3),dict(self.update('/music test',13),update_id=4)]
        config=Path(self.tmp.name)/'config.json';config.write_text(json.dumps(self.config))
        p=subprocess.run([sys.executable,str(Path(bot.__file__)), '--config',str(config),'--once'],capture_output=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr.decode())
        messages=[d['text'] for m,d in self.calls if m=='sendMessage']
        self.assertEqual(len(messages),4)
        self.assertIn('МАГНИТ',messages[0]);self.assertIn('BTC',messages[1]);self.assertIn('News',messages[2]);self.assertIn('A &amp; B',messages[3])
        self.assertEqual(self.b.store.offset(),5)
    def test_preferences_survive_reopen(self):
        self.b.store.setting(10,'currency','rub');self.b.store.db.close();self.b.store=bot.Store(self.config['database'])
        self.assertEqual(self.b.store.user(10)['currency'],'rub')
        self.assertFalse(self.b.store.setting(10,'currency','invalid'))
    def test_callback_uses_sender_and_ack(self):
        self.b.handle({'update_id':2,'callback_query':{'id':'click','from':{'id':10},'data':'currency:eur',
             'message':{'from':{'id':99},'chat':{'id':10,'type':'private'}}}})
        self.assertEqual(self.calls[0][0],'answerCallbackQuery')
        self.assertEqual(self.b.store.user(10)['currency'],'eur')
    def test_failure_does_not_fabricate(self):
        with patch.object(self.b,'crypto',side_effect=bot.UpstreamError(429)):
            self.assertIn('Источник сейчас недоступен',self.send('/crypto')['text'])
    def test_cursor_not_advanced_on_send_failure(self):
        self.updates=[self.update('/start')]
        original=self.b.api
        def api(method,*a,**kw):
            if method=='sendMessage':raise bot.UpstreamError(500)
            return original(method,*a,**kw)
        with patch.object(self.b,'api',side_effect=api):
            with self.assertRaises(bot.UpstreamError):self.b.poll()
        self.assertEqual(self.b.store.offset(),0)
    def test_forbidden_chat_skipped(self):
        self.updates=[self.update('/start')]
        original=self.b.api
        def api(method,*a,**kw):
            if method=='sendMessage':raise bot.UpstreamError(403)
            return original(method,*a,**kw)
        with patch.object(self.b,'api',side_effect=api):self.b.poll()
        self.assertEqual(self.b.store.offset(),2)
    def test_group_ignored(self):
        self.b.handle(self.update('/start',typ='group'));self.assertEqual(self.calls,[])
    def test_music_escaping_and_links(self):
        text=self.send('/music track')['text'];self.assertIn('A &amp; B',text);self.assertNotIn('javascript:',text)
    def test_forget(self):
        self.b.store.user(10);self.b.store.quota(10,2);self.send('/forget')
        self.assertEqual(self.b.store.db.execute('select count(*) from users').fetchone()[0],0)
        self.assertEqual(self.b.store.db.execute('select count(*) from usage').fetchone()[0],0)
    def test_ai_quota_and_no_key(self):
        self.assertIn('пока не подключён',self.send('/ai hello')['text'])
        self.assertTrue(self.b.store.quota(10,1));self.assertFalse(self.b.store.quota(10,1))
    def test_cache_only_success(self):
        count=[]
        def load():count.append(1);return 'ok'
        self.assertEqual(self.b.cached('a',30,load),'ok');self.b.cached('a',30,load);self.assertEqual(len(count),1)
    def test_webhook_not_destroyed(self):
        original=self.b.api
        def api(method,*a,**kw):
            return {'url':'https://example.com/hook'} if method=='getWebhookInfo' else original(method,*a,**kw)
        with patch.object(self.b,'api',side_effect=api):
            with self.assertRaises(RuntimeError):self.b.setup()
        self.assertFalse(any(m=='deleteWebhook' for m,d in self.calls))
    def test_wrong_bot_rejected(self):
        with patch.object(self.b,'api',return_value={'username':'OtherBot'}):
            with self.assertRaises(RuntimeError):self.b.setup()
    def test_health_waits_for_successful_poll(self):
        self.assertFalse(self.b.health()['ok']);self.b.poll();self.assertTrue(self.b.health()['ok'])
    def test_ai_response_and_explicit_input_only(self):
        self.b.cfg['openai_key']='fixture'
        with patch.object(self.b.http,'request',return_value={'output':[{'content':[{'type':'output_text','text':'Ответ'}]}]}) as req:
            self.assertEqual(self.b.ai(10,'hello'),'Ответ')
            payload=req.call_args.args[1]
            self.assertFalse(payload['store']);self.assertEqual(payload['input'],'hello')
            self.assertNotIn('previous_response_id',payload)

if __name__=='__main__':unittest.main()
