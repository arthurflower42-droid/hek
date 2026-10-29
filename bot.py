#!/usr/bin/env python3
"""550D&A · Digital Algorithms — витринный Telegram-бот.
Показывает экраны как на скринах, но функции не активны (демо-режим).
Python 3.10+, только стандартная библиотека."""

import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

def load_config():
    cfg = {}
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    cfg["token"] = (os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("token") or "").strip()
    cfg["expected_username"] = (os.environ.get("EXPECTED_USERNAME") or cfg.get("expected_username") or "").lstrip("@")
    cfg["database"] = os.environ.get("DATABASE") or cfg.get("database") or "magnit.sqlite3"
    try:
        cfg["health_port"] = int(os.environ.get("HEALTH_PORT") or cfg.get("health_port") or 0)
    except (TypeError, ValueError):
        cfg["health_port"] = 0
    return cfg

CFG = load_config()
TOKEN = CFG["token"]
API = "https://api.telegram.org/bot" + TOKEN + "/"
DB_PATH = CFG["database"] if os.path.isabs(CFG["database"]) else os.path.join(HERE, CFG["database"])

STATE = {"started": time.time(), "last_update": 0.0, "last_poll": 0.0, "updates": 0, "username": "", "ok": False}

DEMO_NOTE = "\n\n<i>Демо-режим: витрина для показа. Функции не активны, средства не принимаются.</i>"

# Тексты для экранов (как на скринах)
WELCOME_TEXT = (
    "<b>Welcome to Digital Algorithms!</b>\n\n"
    "🚀 Congratulations! You have successfully registered and become part of our international community!\n\n"
    "🇦🇺 Digital Algorithms is an Australian technology company specializing in automated trading "
    "in financial markets using intelligent trading algorithms.\n\n"
    "🇦🇺 Our company is officially registered in Australia, and our registration documents are available for verification.\n\n"
    "📄 <b>Want to Learn More?</b>\n"
    "In the \"About Us\" section, you will find detailed information about our company, technologies, and how our system operates.\n\n"
    "📊 We also recommend exploring the Digital Algorithms Presentation, which provides a detailed overview "
    "of our business model and the opportunities offered by our platform.\n\n"
    "❤️ Thank you for your trust! We're delighted to welcome you to Digital Algorithms!\n\n"
    "<i>Digital Algorithms Team</i>"
)

DASHBOARD_TEXT = (
    "<b>550D&A</b>\n\n"
    "Choose an action below or open the dashboard.\n\n"
    "<b>Total, = USDT</b>    0.00 USDT\n"
    "<b>Available</b>        0.00 USDT\n"
    "<b>In deposits</b>      0.00 USDT\n"
    "<b>Estimated income</b> 0.00 USDT"
)

ABOUT_TEXT = (
    "<b>About Digital Algorithms</b>\n\n"
    "Digital Algorithms is an Australian technology company specializing in automated trading "
    "in financial markets using intelligent trading algorithms.\n\n"
    "Our company is officially registered in Australia, and our registration documents are available for verification.\n\n"
    "We develop cutting-edge algorithmic trading systems that operate 24/7 across global financial markets, "
    "using advanced mathematical models and machine learning to identify profitable opportunities."
)

PRESENTATION_TEXT = (
    "<b>Digital Algorithms Presentation</b>\n\n"
    "📊 Our business model combines automated trading algorithms with a user-friendly platform "
    "that allows investors to participate in algorithmic trading without technical expertise.\n\n"
    "Key features:\n"
    "• Automated trading 24/7\n"
    "• Risk management systems\n"
    "• Transparent reporting\n"
    "• Multi-asset strategies\n\n"
    "Contact our team for a detailed presentation."
)

HELP_TEXT = (
    "<b>Help & Support</b>\n\n"
    "For assistance, please contact our support team:\n"
    "• Email: support@digitalalgorithms.com\n"
    "• Live chat available in your dashboard\n"
    "• FAQ section coming soon\n\n"
    "Our team is available 24/7 to assist you."
)

def call(method, payload):
    request = urllib.request.Request(
        API + method,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=50) as response:
            result = json.loads(response.read(2_000_000))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    return result.get("result") if result.get("ok") else None

# База данных (лёгкая статистика)
_LOCAL = threading.local()

def db():
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = _LOCAL.conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, first_ts REAL, last_ts REAL, hits INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS clicks(key TEXT PRIMARY KEY, n INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
        conn.commit()
    return conn

def seen(uid):
    now = time.time()
    c = db()
    c.execute("INSERT INTO users(uid, first_ts, last_ts, hits) VALUES(?,?,?,1) "
              "ON CONFLICT(uid) DO UPDATE SET last_ts=?, hits=hits+1", (uid, now, now, now))
    c.commit()

def click(key):
    c = db()
    c.execute("INSERT INTO clicks(key, n) VALUES(?,1) ON CONFLICT(key) DO UPDATE SET n=n+1", (key,))
    c.commit()

def get_offset():
    try:
        row = db().execute("SELECT v FROM kv WHERE k='offset'").fetchone()
        return int(row[0]) if row else 0
    except (sqlite3.Error, ValueError):
        return 0

def set_offset(val):
    c = db()
    c.execute("INSERT INTO kv(k, v) VALUES('offset', ?) ON CONFLICT(k) DO UPDATE SET v=?", (str(val), str(val)))
    c.commit()

def stats():
    try:
        c = db()
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        hits = c.execute("SELECT COALESCE(SUM(hits),0) FROM users").fetchone()[0]
        return {"users": users, "hits": hits}
    except sqlite3.Error:
        return {"users": 0, "hits": 0}

# Клавиатуры
def main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📊 Open deposit", "callback_data": "deposit"}],
            [{"text": "⬆ Top up", "callback_data": "topup"}, {"text": "⬇ Withdraw", "callback_data": "withdraw"}],
            [{"text": "📋 My deposits", "callback_data": "my_deposits"}, {"text": "💰 Balance", "callback_data": "balance"}],
            [{"text": "🔄 Reinvest", "callback_data": "reinvest"}],
            [{"text": "👥 Team", "callback_data": "team"}, {"text": "📜 History", "callback_data": "history"}],
            [{"text": "❓ Help", "callback_data": "help"}, {"text": "🌐 Language", "callback_data": "language"}],
            [{"text": "📄 Presentation", "callback_data": "presentation"}],
            [{"text": "🔗 Open dashboard", "url": "https://t.me/MagnitWaveBot"}],
        ]
    }

def welcome_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📊 Open dashboard", "callback_data": "dashboard"}],
            [{"text": "📄 About Us", "callback_data": "about"}, {"text": "📊 Presentation", "callback_data": "presentation"}],
            [{"text": "❓ Help", "callback_data": "help"}],
        ]
    }

def back_keyboard():
    return {"inline_keyboard": [[{"text": "← Back to Dashboard", "callback_data": "dashboard"}]]}

def send(chat_id, text, markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "link_preview_options": {"is_disabled": True}}
    if markup:
        payload["reply_markup"] = markup
    call("sendMessage", payload)

def handle(update):
    if "callback_query" in update:
        cb = update["callback_query"]
        call("answerCallbackQuery", {"callback_query_id": cb["id"]})
        message = cb.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if not chat_id:
            return
        key = cb.get("data", "")
        seen((cb.get("from") or {}).get("id") or chat_id)
        click(key)
        
        if key == "dashboard":
            send(chat_id, DASHBOARD_TEXT + DEMO_NOTE, main_keyboard())
        elif key == "deposit":
            send(chat_id, "<b>Open Deposit</b>\n\nChoose your investment plan:\n• Plan A: 10% monthly\n• Plan B: 15% monthly\n• Plan C: 20% monthly\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "topup":
            send(chat_id, "<b>Top Up</b>\n\nSend USDT to the following address:\n<code>0x1234...5678</code>\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "withdraw":
            send(chat_id, "<b>Withdraw</b>\n\nEnter the amount and your USDT address.\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "my_deposits":
            send(chat_id, "<b>My Deposits</b>\n\nYou have no active deposits.\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "balance":
            send(chat_id, "<b>Balance</b>\n\nTotal: 0.00 USDT\nAvailable: 0.00 USDT\nIn deposits: 0.00 USDT\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "reinvest":
            send(chat_id, "<b>Reinvest</b>\n\nAutomatically reinvest your earnings for compound growth.\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "team":
            send(chat_id, "<b>Team</b>\n\nYour referral link: https://t.me/MagnitWaveBot?start=ref123\nTeam size: 0\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "history":
            send(chat_id, "<b>History</b>\n\nNo transactions yet.\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "help":
            send(chat_id, HELP_TEXT + DEMO_NOTE, back_keyboard())
        elif key == "language":
            send(chat_id, "<b>Language</b>\n\nChoose your language:\n• English\n• Русский\n\n" + DEMO_NOTE, back_keyboard())
        elif key == "presentation":
            send(chat_id, PRESENTATION_TEXT + DEMO_NOTE, back_keyboard())
        elif key == "about":
            send(chat_id, ABOUT_TEXT + DEMO_NOTE, back_keyboard())
        return
    
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return
    text = (message.get("text") or "").strip()
    uid = (message.get("from") or {}).get("id") or chat.get("id")
    
    if text.startswith(("/start", "/help", "/menu")):
        seen(uid)
        click("/start")
        send(chat["id"], WELCOME_TEXT, welcome_keyboard())
    elif text.startswith("/dashboard"):
        seen(uid)
        click("/dashboard")
        send(chat["id"], DASHBOARD_TEXT + DEMO_NOTE, main_keyboard())

# Health-сервер
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        up = time.time() - STATE["started"]
        body = {
            "ok": STATE["ok"],
            "bot": STATE["username"],
            "uptime_sec": round(up),
            "last_update_ago": round(time.time() - STATE["last_update"]) if STATE["last_update"] else None,
            "last_poll_ago": round(time.time() - STATE["last_poll"]) if STATE["last_poll"] else None,
            "updates": STATE["updates"],
            **stats(),
        }
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200 if STATE["ok"] else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

def start_health(port):
    if not port:
        return
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Health)
    except OSError as e:
        print("health: порт", port, "занят —", e.__class__.__name__)
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("health: слушаю 127.0.0.1:%d" % port)

def main():
    if not TOKEN:
        raise SystemExit("Нет токена: задайте token в config.json или TELEGRAM_BOT_TOKEN.")
    me = call("getMe", {})
    if not me:
        raise SystemExit("Telegram не принял токен (getMe не ответил).")
    STATE["username"] = me.get("username", "")
    STATE["ok"] = True
    if CFG["expected_username"] and STATE["username"].lower() != CFG["expected_username"].lower():
        print("Внимание: токен от @%s, а в настройках ожидался @%s. "
              "Поменяйте expected_username или токен." % (STATE["username"], CFG["expected_username"]))
    print("Запущен @%s (id %s). База: %s" % (STATE["username"], me.get("id"), DB_PATH))
    start_health(CFG["health_port"])

    offset = get_offset()
    while True:
        updates = call("getUpdates", {"offset": offset, "timeout": 30,
                                      "allowed_updates": ["message", "callback_query"]})
        STATE["last_poll"] = time.time()
        if updates is None:
            STATE["ok"] = False
            time.sleep(3)
            continue
        STATE["ok"] = True
        for update in updates:
            offset = update["update_id"] + 1
            STATE["last_update"] = time.time()
            STATE["updates"] += 1
            try:
                handle(update)
            except Exception:
                pass
        if updates:
            set_offset(offset)

if __name__ == "__main__":
    main()
