import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import bot


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls, self.updates = [], []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data = json.loads(
                    self.rfile.read(int(self.headers.get("Content-Length", 0)))
                )
                method = self.path.rsplit("/", 1)[-1]
                outer.calls.append((method, data))
                value = True
                if method == "getMe":
                    value = {"username": "MagnitWaveBot"}
                if method == "getWebhookInfo":
                    value = {"url": ""}
                if method == "getUpdates":
                    value = outer.updates
                if method == "sendMessage":
                    value = {"message_id": 12}
                self.respond({"ok": True, "result": value})

            def respond(self, data):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        base = "http://127.0.0.1:" + str(self.server.server_port)
        self.config = {
            "token": "fixture",
            "database": self.tmp.name + "/db.sqlite",
            "telegram_base": base,
        }
        self.b = bot.Bot(self.config)

    def tearDown(self):
        self.b.store.db.close()
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def update(self, text, uid=10, typ="private"):
        return {
            "update_id": 1,
            "message": {
                "chat": {"id": uid, "type": typ},
                "from": {"id": uid},
                "text": text,
            },
        }

    def send(self, text, uid=10):
        self.b.rates.clear()
        self.b.handle(self.update(text, uid))
        return [d for m, d in self.calls if m == "sendMessage"][-1]

    def test_incoming_update_subprocess(self):
        self.updates = [
            self.update("/start"),
            dict(self.update("/dashboard", 11), update_id=2),
        ]
        config = Path(self.tmp.name) / "config.json"
        config.write_text(json.dumps(self.config))
        p = subprocess.run(
            [
                sys.executable,
                str(Path(bot.__file__)),
                "--config",
                str(config),
                "--once",
            ],
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        messages = [d["text"] for m, d in self.calls if m == "sendMessage"]
        self.assertEqual(len(messages), 2)
        self.assertIn("Digital Algorithms", messages[0])
        self.assertIn("0.00 USDT", messages[1])
        self.assertEqual(self.b.store.offset(), 3)

    def test_welcome_text(self):
        text = self.send("/start")["text"]
        self.assertIn("Welcome to Digital Algorithms!", text)
        self.assertIn("Australian technology company", text)

    def test_dashboard_zero_balances(self):
        text = self.send("/dashboard")["text"]
        for line in ("Total:", "Available:", "In deposits:", "Estimated income:"):
            self.assertIn(line, text)
        self.assertEqual(text.count("0.00 USDT"), 4)
        self.assertIn("Демо-режим", text)

    def test_callback_dashboard(self):
        self.b.handle(
            {
                "update_id": 2,
                "callback_query": {
                    "id": "click",
                    "from": {"id": 10},
                    "data": "balance",
                    "message": {
                        "from": {"id": 99},
                        "chat": {"id": 10, "type": "private"},
                    },
                },
            }
        )
        self.assertEqual(self.calls[0][0], "answerCallbackQuery")
        text = [d for m, d in self.calls if m == "sendMessage"][-1]["text"]
        self.assertIn("0.00 USDT", text)

    def test_stub_sections(self):
        for cmd in ("deposit", "topup", "withdraw", "reinvest"):
            self.assertIn("витрина", self.send("/" + cmd)["text"])

    def test_language_switch(self):
        self.b.handle(
            {
                "update_id": 3,
                "callback_query": {
                    "id": "click",
                    "from": {"id": 10},
                    "data": "setlang:ru",
                    "message": {
                        "from": {"id": 99},
                        "chat": {"id": 10, "type": "private"},
                    },
                },
            }
        )
        self.assertEqual(self.b.store.language(10), "ru")
        self.assertFalse(self.b.store.language(10, "xx"))

    def test_group_ignored(self):
        self.b.handle(self.update("/start", typ="group"))
        self.assertEqual(self.calls, [])

    def test_forget(self):
        self.b.store.user(10)
        self.send("/forget")
        self.assertEqual(
            self.b.store.db.execute("select count(*) from users").fetchone()[0], 0
        )

    def test_cursor_not_advanced_on_send_failure(self):
        self.updates = [self.update("/start")]
        original = self.b.api

        def api(method, *a, **kw):
            if method == "sendMessage":
                raise bot.UpstreamError(500)
            return original(method, *a, **kw)

        with patch.object(self.b, "api", side_effect=api):
            with self.assertRaises(bot.UpstreamError):
                self.b.poll()
        self.assertEqual(self.b.store.offset(), 0)

    def test_webhook_not_destroyed(self):
        original = self.b.api

        def api(method, *a, **kw):
            return (
                {"url": "https://example.com/hook"}
                if method == "getWebhookInfo"
                else original(method, *a, **kw)
            )

        with patch.object(self.b, "api", side_effect=api):
            with self.assertRaises(RuntimeError):
                self.b.setup()
        self.assertFalse(any(m == "deleteWebhook" for m, d in self.calls))

    def test_wrong_bot_rejected(self):
        with patch.object(self.b, "api", return_value={"username": "OtherBot"}):
            with self.assertRaises(RuntimeError):
                self.b.setup()

    def test_health_waits_for_successful_poll(self):
        self.assertFalse(self.b.health()["ok"])
        self.b.poll()
        self.assertTrue(self.b.health()["ok"])


if __name__ == "__main__":
    unittest.main()
