#!/usr/bin/env python3
"""550D&A · Digital Algorithms. Витринный бот: экраны для показа, функции не активны.
Python 3.10+, standard library only."""

import argparse
import datetime as dt
import html
import json
import logging
import signal
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = logging.getLogger("magnit")
DEMO_NOTE = "\n\n<i>Демо-режим: витрина для показа. Функции не активны, средства не принимаются.</i>"

COMMANDS = [
    ("start", "Welcome / Главная"),
    ("dashboard", "Дашборд"),
    ("balance", "Баланс"),
    ("deposits", "Мои депозиты"),
    ("team", "Команда"),
    ("history", "История"),
    ("help", "Помощь"),
    ("presentation", "Презентация"),
    ("about", "О компании"),
    ("language", "Language"),
]


def clean(value, limit=3500):
    return html.escape(str(value))[:limit]


class UpstreamError(Exception):
    def __init__(self, status=0, retry_after=0):
        self.status, self.retry_after = status, retry_after
        super().__init__("External service unavailable")


class HTTP:
    def request(self, url, data=None, headers=None, timeout=15):
        h = {"User-Agent": "MagnitWaveBot/1.0", **(headers or {})}
        body = None if data is None else json.dumps(data).encode()
        if body is not None:
            h["Content-Type"] = "application/json"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, body, h), timeout=timeout
            ) as r:
                content = r.read(2_000_001)
                if len(content) > 2_000_000:
                    raise UpstreamError()
                return json.loads(content)
        except urllib.error.HTTPError as exc:
            retry = 0
            try:
                payload = json.loads(exc.read(8192))
                retry = int(payload.get("parameters", {}).get("retry_after", 0))
            except (ValueError, TypeError):
                pass
            raise UpstreamError(exc.code, retry) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise UpstreamError() from None


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, language TEXT NOT NULL DEFAULT 'en');
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);"""
        )
        self.db.commit()

    def user(self, uid):
        self.db.execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (uid,))
        self.db.commit()
        row = self.db.execute(
            "SELECT language FROM users WHERE id=?", (uid,)
        ).fetchone()
        return {"language": row[0]}

    def language(self, uid, value=None):
        if value is not None:
            if value not in ("en", "ru"):
                return False
            self.user(uid)
            self.db.execute("UPDATE users SET language=? WHERE id=?", (value, uid))
            self.db.commit()
        return self.user(uid)["language"]

    def forget(self, uid):
        self.db.execute("DELETE FROM users WHERE id=?", (uid,))
        self.db.commit()

    def offset(self, value=None):
        if value is not None:
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES('offset',?)", (str(value),)
            )
            self.db.commit()
        row = self.db.execute("SELECT value FROM meta WHERE key='offset'").fetchone()
        return int(row[0]) if row else 0


class Bot:
    def __init__(self, config, http=None):
        self.cfg, self.http = config, http or HTTP()
        self.store = Store(config.get("database", "magnit.sqlite3"))
        self.base = (
            config.get("telegram_base", "https://api.telegram.org")
            + "/bot"
            + config["token"]
            + "/"
        )
        self.rates = {}
        self.last_poll = 0
        self.stopping = False
        self.revision = config.get("revision", "local")

    def api(self, method, data=None, timeout=15):
        result = self.http.request(self.base + method, data or {}, timeout=timeout)
        if not result.get("ok"):
            raise UpstreamError(
                result.get("error_code", 0),
                result.get("parameters", {}).get("retry_after", 0),
            )
        return result["result"]

    # ---------- витринные экраны ----------

    def keyboard(self):
        return {
            "inline_keyboard": [
                [{"text": "📊 Open deposit", "callback_data": "deposit"}],
                [
                    {"text": "⬆ Top up", "callback_data": "topup"},
                    {"text": "⬇ Withdraw", "callback_data": "withdraw"},
                ],
                [
                    {"text": "📁 My deposits", "callback_data": "deposits"},
                    {"text": "💰 Balance", "callback_data": "balance"},
                ],
                [{"text": "♻ Reinvest", "callback_data": "reinvest"}],
                [
                    {"text": "👥 Team", "callback_data": "team"},
                    {"text": "🕘 History", "callback_data": "history"},
                ],
                [
                    {"text": "❓ Help", "callback_data": "help"},
                    {"text": "🌐 Language", "callback_data": "language"},
                ],
                [{"text": "📄 Presentation", "callback_data": "presentation"}],
                [{"text": "🚀 Open dashboard", "callback_data": "dashboard"}],
            ]
        }

    def welcome(self):
        return (
            "<b>Welcome to Digital Algorithms!</b>\n\n"
            "Congratulations! You have successfully registered and become part "
            "of our international community!\n\n"
            "Digital Algorithms is an Australian technology company specializing "
            "in automated trading in financial markets using intelligent "
            "trading algorithms.\n\n"
            "Our company is officially registered in Australia, and our "
            "registration documents are available for verification.\n\n"
            "<b>Want to learn more?</b>\n"
            "In the \"About Us\" section, you will find detailed information "
            "about our company, technologies, and how our system operates.\n\n"
            "We also recommend exploring the Digital Algorithms Presentation, "
            "which provides a detailed overview of our business model and the "
            "opportunities offered by our platform.\n\n"
            "Thank you for your trust! We're delighted to welcome you to "
            "Digital Algorithms! 💚\n\n"
            "<i>Digital Algorithms Team</i>"
            + DEMO_NOTE
        )

    def dashboard(self):
        now = dt.datetime.now(dt.timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        return (
            "<b>550D&amp;A</b>\n"
            "<i>Choose an action below or open the dashboard.</i>\n\n"
            "<b>Total:</b> 0.00 USDT\n"
            "<b>Available:</b> 0.00 USDT\n"
            "<b>In deposits:</b> 0.00 USDT\n"
            "<b>Estimated income:</b> 0.00 USDT\n\n"
            f"<i>Updated {now}</i>"
            + DEMO_NOTE
        )

    def balance(self):
        return (
            "<b>💰 Balance</b>\n\n"
            "Total: 0.00 USDT\n"
            "Available: 0.00 USDT\n"
            "In deposits: 0.00 USDT\n"
            "Estimated income: 0.00 USDT"
            + DEMO_NOTE
        )

    def deposits(self):
        return "<b>📁 My deposits</b>\n\nНет активных депозитов." + DEMO_NOTE

    def history(self):
        return "<b>🕘 History</b>\n\nОпераций пока нет." + DEMO_NOTE

    def team(self):
        return (
            "<b>👥 Team</b>\n\n"
            "Партнёров пока нет. Твоя структура пуста."
            + DEMO_NOTE
        )

    def presentation(self):
        return (
            "<b>📄 Digital Algorithms Presentation</b>\n\n"
            "Обзор бизнес-модели и возможностей платформы.\n"
            "<i>Презентация доступна владельцу проекта для загрузки.</i>"
            + DEMO_NOTE
        )

    def about(self):
        return (
            "<b>◆ About Us</b>\n\n"
            "Digital Algorithms — австралийская технологическая компания, "
            "специализирующаяся на автоматизированной торговле на финансовых "
            "рынках с использованием интеллектуальных торговых алгоритмов.\n\n"
            "Компания официально зарегистрирована в Австралии; регистрационные "
            "документы доступны для проверки."
            + DEMO_NOTE
        )

    def help(self):
        return (
            "<b>❓ Help</b>\n\n"
            "Разделы бота:\n"
            "/dashboard — дашборд\n"
            "/balance — баланс\n"
            "/deposits — мои депозиты\n"
            "/team — команда\n"
            "/history — история\n"
            "/presentation — презентация\n"
            "/about — о компании"
            + DEMO_NOTE
        )

    def language_screen(self):
        return (
            "<b>🌐 Language</b>\n\nChoose your language:"
        )

    def language_keyboard(self):
        return {
            "inline_keyboard": [
                [
                    {"text": "🇬🇧 English", "callback_data": "setlang:en"},
                    {"text": "🇷🇺 Русский", "callback_data": "setlang:ru"},
                ],
                [{"text": "← Back", "callback_data": "dashboard"}],
            ]
        }

    def stub(self, title):
        return (
            f"<b>{title}</b>\n\n"
            "Этот раздел показан как витрина: функция не активна в демо-режиме."
            + DEMO_NOTE
        )

    # ---------- диспетчер ----------

    def answer(self, command):
        table = {
            "start": self.welcome,
            "dashboard": self.dashboard,
            "balance": self.balance,
            "deposits": self.deposits,
            "team": self.team,
            "history": self.history,
            "presentation": self.presentation,
            "about": self.about,
            "help": self.help,
            "language": self.language_screen,
            "deposit": lambda: self.stub("📊 Open deposit"),
            "topup": lambda: self.stub("⬆ Top up"),
            "withdraw": lambda: self.stub("⬇ Withdraw"),
            "reinvest": lambda: self.stub("♻ Reinvest"),
        }
        return table.get(command)

    def send(self, chat, text, markup=None):
        return self.api(
            "sendMessage",
            {
                "chat_id": chat,
                "text": text,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
                "reply_markup": markup or self.keyboard(),
            },
        )

    def handle(self, update):
        cb = update.get("callback_query")
        message = cb.get("message", {}) if cb else update.get("message", {})
        user = (cb or message).get("from", {})
        uid, chat = user.get("id"), message.get("chat", {}).get("id")
        if cb:
            self.api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        if not uid or not chat or message.get("chat", {}).get("type") != "private":
            return
        raw = cb.get("data", "") if cb else message.get("text", "")
        if not isinstance(raw, str):
            return
        now = time.monotonic()
        if now - self.rates.get(uid, -100) < 2:
            return
        if len(self.rates) > 10000:
            self.rates = {k: v for k, v in self.rates.items() if now - v < 60}
        self.rates[uid] = now
        command, _, _ = raw.strip().partition(" ")
        command = command.lstrip("/").split("@")[0].lower()
        if command == "forget":
            self.store.forget(uid)
            self.send(chat, "Твои настройки удалены.")
            return
        if command.startswith("setlang:"):
            lang = command.split(":", 1)[1]
            self.store.language(uid, lang)
            self.send(
                chat,
                "🇬🇧 Language saved.\n🇷🇺 Язык сохранён." + DEMO_NOTE,
            )
            return
        handler = self.answer(command)
        if handler is None:
            self.send(chat, self.welcome())
            return
        markup = self.language_keyboard() if command == "language" else None
        self.send(chat, handler(), markup)

    def setup(self):
        me = self.api("getMe")
        if (
            me.get("username", "").lower()
            != self.cfg.get("expected_username", "MagnitWaveBot").lower()
        ):
            raise RuntimeError("Token belongs to another bot")
        webhook = self.api("getWebhookInfo")
        if webhook.get("url"):
            raise RuntimeError(
                "Existing webhook found; installation stopped without changing it"
            )
        self.api(
            "setMyCommands",
            {"commands": [{"command": k, "description": v} for k, v in COMMANDS]},
        )
        self.api(
            "setMyDescription",
            {"description": "550D&A · Digital Algorithms — витринный демонстрационный бот."},
        )
        self.api(
            "setMyShortDescription",
            {"short_description": "Digital Algorithms. Демо-витрина."},
        )

    def poll(self):
        updates = self.api(
            "getUpdates",
            {
                "offset": self.store.offset(),
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            },
            timeout=40,
        )
        self.last_poll = time.monotonic()
        for update in updates:
            try:
                self.handle(update)
            except UpstreamError as exc:
                if exc.status in (400, 403):
                    LOG.warning("undeliverable_update status=%s", exc.status)
                else:
                    raise
            self.store.offset(update["update_id"] + 1)

    def run(self):
        backoff = 1
        while not self.stopping:
            try:
                self.poll()
                backoff = 1
            except UpstreamError as exc:
                LOG.warning("poll_failed status=%s", exc.status)
                if exc.status in (401, 409):
                    raise RuntimeError(
                        "Unauthorized token or competing poller"
                    ) from None
                time.sleep(min(60, max(backoff, exc.retry_after)))
                backoff = min(60, backoff * 2)

    def health(self):
        return {
            "ok": bool(self.last_poll and time.monotonic() - self.last_poll < 90),
            "revision": self.revision,
        }


def serve_health(bot, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/health":
                self.send_error(404)
                return
            result = bot.health()
            self.send_response(200 if result["ok"] else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        def log_message(*args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/magnit/config.json")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    config = json.loads(Path(args.config).read_text())
    bot = Bot(config)
    bot.setup()
    if args.once:
        bot.poll()
        return
    server = serve_health(bot, int(config.get("health_port", 8769)))
    signal.signal(signal.SIGTERM, lambda *_: setattr(bot, "stopping", True))
    signal.signal(signal.SIGINT, lambda *_: setattr(bot, "stopping", True))
    LOG.info("started revision=%s", bot.revision)
    try:
        bot.run()
    finally:
        server.shutdown()
        bot.store.db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        LOG.error("fatal type=%s", type(exc).__name__)
        raise SystemExit(1)
