#!/usr/bin/env python3
"""Magnit paper-trading demo. Standard library only; no real funds or exchange."""
import argparse
import html
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {}
_parser = argparse.ArgumentParser(description="Magnit bot")
_parser.add_argument("--config", default=os.path.join(HERE, "config.json"))
_args, _ = _parser.parse_known_args()
try:
    with open(_args.config, encoding="utf-8") as f:
        CFG = json.load(f)
except (OSError, ValueError):
    pass
TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or CFG.get("token") or "").strip()
EXPECTED = (os.environ.get("EXPECTED_USERNAME") or CFG.get("expected_username") or "").lstrip("@")
DB_NAME = os.environ.get("DATABASE") or CFG.get("database") or "magnit-demo.sqlite3"
DB_PATH = DB_NAME if os.path.isabs(DB_NAME) else os.path.join(HERE, DB_NAME)
try:
    HEALTH_PORT = int(os.environ.get("HEALTH_PORT") or CFG.get("health_port") or 0)
except (ValueError, TypeError):
    HEALTH_PORT = 0
API = "https://api.telegram.org/bot" + TOKEN + "/"
STATE = {"started": time.time(), "last_update": 0, "last_poll": 0, "updates": 0, "username": "", "ok": False,
         "replies": 0, "last_reply": 0, "last_error": ""}
LOCAL = threading.local()
SEED = 10000
PLANS = {100: "🌟 Starter", 500: "🚀 Explorer", 1000: "💎 Strategist"}
TEXT = {
 "en": {
  "welcome": (
      "╔══════════════════════╗\n"
      "║   🧲 <b>MAGNIT DEMO</b>   ║\n"
      "║   Paper Trading      ║\n"
      "╚══════════════════════╝\n\n"
      "🎮 <b>Welcome to your virtual trading floor!</b>\n\n"
      "💡 Explore a fictional portfolio using virtual credits.\n"
      "⚠️ No real money, deposits, or trading involved."
  ),
  "menu": "📋 <b>What would you like to do?</b>",
  "balance": "💰 Virtual Balance",
  "invested": "📊 In Open Demos",
  "portfolio": "📁 Portfolio",
  "plans": "🎯 <b>Choose Your Demo Plan</b>\n\nSelect a plan to open a virtual position.\nAll amounts are fictional credits — no real trades.",
  "opened": "✅ <b>Position Opened!</b>\n\n🎯 Plan: <b>{plan}</b>\n💳 Amount: <b>{amount:,} credits</b>\n\n📝 This is a demo only. No real trade was placed.",
  "insufficient": "❌ <b>Insufficient Credits</b>\n\nYou don't have enough virtual credits for this plan.\nClose an existing position first or choose a smaller plan.",
  "empty": "📭 <b>No Open Positions</b>\n\nYour portfolio is empty. Start by opening a demo position!",
  "portfolio_title": "📁 <b>Your Demo Portfolio</b>",
  "history_title": "📜 <b>Recent Activity</b>",
  "closed": "🔒 <b>Position Closed</b>\n\n🆔 ID: #{id}\n📊 Scenario: <b>{pct:+d}%</b>\n💱 Virtual Change: <b>{change:+,} credits</b>",
  "risk": "⚠️ <b>Risk Disclaimer</b>\n\n• Markets can move against you\n• Past results ≠ future results\n• This is invented demo data\n• Never share passwords or payment details",
  "about": "ℹ️ <b>About Magnit</b>\n\nMagnit is a fictional paper-trading interface for exploring Telegram bot navigation and virtual portfolios.\n\n🚫 Not a broker\n🚫 Not an exchange\n🚫 Not an investment offer",
  "help": "🆘 <b>How to Use</b>\n\n1️⃣ /start — Open main menu\n2️⃣ Choose a demo plan\n3️⃣ Close with -10%, 0%, or +10% scenario\n\nAll amounts are virtual credits.",
  "opened_list": "📂 <b>Your Open Positions:</b>",
  "closed_list": "📭 No activity yet.",
  "lang": "✅ Language set to English 🇬🇧",
  "open": "🚀 Open Demo",
  "portfolio_btn": "📁 Portfolio",
  "history_btn": "📜 Activity",
  "plans_btn": "🎯 Plans",
  "risk_btn": "⚠️ Risk Notes",
  "about_btn": "ℹ️ About",
  "help_btn": "🆘 Help",
  "back": "◀️ Menu",
  "close": "🔒 Close",
  "scenario": "🎲 <b>Choose Scenario</b>\n\nPick a hypothetical outcome for closing:",
  "close_btn": "🔒 Close Position",
  "scenario_minus": "📉 −10%",
  "scenario_zero": "➡️ 0%",
  "scenario_plus": "📈 +10%",
  "lang_btn": "🌐 Русский / English",
  "no_position": "❌ This position is not open or doesn't exist."
 },
 "ru": {
  "welcome": (
      "╔══════════════════════╗\n"
      "║   🧲 <b>МАГНИТ ДЕМО</b>   ║\n"
      "║   Торговый Симулятор ║\n"
      "╚══════════════════════╝\n\n"
      "🎮 <b>Добро пожаловать на виртуальную торговую площадку!</b>\n\n"
      "💡 Изучайте вымышленный портфель на виртуальных кредитах.\n"
      "⚠️ Реальных денег, сделок и инвестиций здесь нет."
  ),
  "menu": "📋 <b>Что хотите сделать?</b>",
  "balance": "💰 Виртуальный баланс",
  "invested": "📊 В открытых позициях",
  "portfolio": "📁 Портфель",
  "plans": "🎯 <b>Выберите Демо-План</b>\n\nОткройте виртуальную позицию.\nВсе суммы — вымышленные кредиты, реальных сделок нет.",
  "opened": "✅ <b>Позиция Открыта!</b>\n\n🎯 План: <b>{plan}</b>\n💳 Сумма: <b>{amount:,} кредитов</b>\n\n📝 Это только демо. Реальная сделка не совершалась.",
  "insufficient": "❌ <b>Недостаточно Кредитов</b>\n\nУ вас не хватает виртуальных кредитов.\nЗакройте существующую позицию или выберите план поменьше.",
  "empty": "📭 <b>Нет Открытых Позиций</b>\n\nВаш портфель пуст. Начните с открытия демо-позиции!",
  "portfolio_title": "📁 <b>Ваш Демо-Портфель</b>",
  "history_title": "📜 <b>Последние Операции</b>",
  "closed": "🔒 <b>Позиция Закрыта</b>\n\n🆔 ID: #{id}\n📊 Сценарий: <b>{pct:+d}%</b>\n💱 Вирт. изменение: <b>{change:+,} кредитов</b>",
  "risk": "⚠️ <b>О Рисках</b>\n\n• Рынок может идти против вас\n• Прошлые результаты ≠ будущие\n• Здесь вымышленные данные\n• Не передавайте пароли и платежные данные",
  "about": "ℹ️ <b>О Магните</b>\n\nМагнит — вымышленный интерфейс для знакомства с Telegram-ботами и виртуальными портфелями.\n\n🚫 Не брокер\n🚫 Не биржа\n🚫 Не инвест-предложение",
  "help": "🆘 <b>Как Использовать</b>\n\n1️⃣ /start — Главное меню\n2️⃣ Выберите демо-план\n3️⃣ Закройте со сценарием -10%, 0% или +10%\n\nВсе суммы виртуальные.",
  "opened_list": "📂 <b>Ваши Открытые Позиции:</b>",
  "closed_list": "📭 Операций пока нет.",
  "lang": "✅ Язык изменён на русский 🇷🇺",
  "open": "🚀 Открыть Демо",
  "portfolio_btn": "📁 Портфель",
  "history_btn": "📜 Операции",
  "plans_btn": "🎯 Планы",
  "risk_btn": "⚠️ О Рисках",
  "about_btn": "ℹ️ О Проекте",
  "help_btn": "🆘 Помощь",
  "back": "◀️ Меню",
  "close": "🔒 Закрыть",
  "scenario": "🎲 <b>Выберите Сценарий</b>\n\nГипотетический исход закрытия:",
  "close_btn": "🔒 Закрыть Позицию",
  "scenario_minus": "📉 −10%",
  "scenario_zero": "➡️ 0%",
  "scenario_plus": "📈 +10%",
  "lang_btn": "🌐 Русский / English",
  "no_position": "❌ Эта позиция не открыта или не существует."
 }
}

def db():
    conn = getattr(LOCAL, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY, language TEXT NOT NULL DEFAULT 'en',
            balance INTEGER NOT NULL DEFAULT 10000, created REAL NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS positions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, plan TEXT NOT NULL,
            amount INTEGER NOT NULL, opened REAL NOT NULL, closed REAL, scenario INTEGER)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, kind TEXT NOT NULL,
            detail TEXT NOT NULL, created REAL NOT NULL)""")
        conn.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
        conn.commit()
        LOCAL.conn = conn
    return conn

def user(uid):
    c = db()
    c.execute("INSERT OR IGNORE INTO users(uid, language, balance, created) VALUES(?, 'en', ?, ?)", (uid, SEED, time.time()))
    c.commit()
    return c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()

def lang(uid):
    return user(uid)["language"]

def say(uid, key, **kwargs):
    return TEXT[lang(uid)][key].format(**kwargs)

def keyboard(rows):
    return {"inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row] for row in rows]}

def menu_markup(uid):
    t = TEXT[lang(uid)]
    return keyboard([[ (t["open"], "plans"), (t["portfolio_btn"], "portfolio") ],
                     [ (t["history_btn"], "history"), (t["risk_btn"], "risk") ],
                     [ (t["about_btn"], "about"), (t["help_btn"], "help") ],
                     [ (t["lang_btn"], "language") ]])

def api(method, payload):
    req = urllib.request.Request(API + method, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read(2_000_000))
    except urllib.error.HTTPError as exc:
        STATE["last_error"] = method + ":HTTP_" + str(exc.code)
        print("Telegram HTTP error:", method, exc.code, flush=True)
        if exc.code == 409:
            print("Another process or webhook is consuming this bot's updates.", flush=True)
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        STATE["last_error"] = method + ":" + type(exc).__name__
        print("Telegram request failed:", method, type(exc).__name__, flush=True)
        return None
    if not result.get("ok"):
        print("Telegram API error:", method, result.get("error_code", "?"), result.get("description", "unknown error"), flush=True)
        return None
    return result.get("result")

def send(chat_id, body, markup=None):
    payload = {"chat_id": chat_id, "text": body, "parse_mode": "HTML",
               "link_preview_options": {"is_disabled": True}}
    if markup:
        payload["reply_markup"] = markup
    result = api("sendMessage", payload)
    if isinstance(result, dict) and result.get("message_id"):
        STATE["replies"] += 1
        STATE["last_reply"] = time.time()
    return result

def home(chat_id, uid):
    send(chat_id, say(uid, "welcome") + "\n\n" + say(uid, "menu"), menu_markup(uid))

def show_dashboard(chat_id, uid):
    u = user(uid)
    invested = db().execute("SELECT COALESCE(SUM(amount),0) FROM positions WHERE uid=? AND closed IS NULL", (uid,)).fetchone()[0]
    t = TEXT[lang(uid)]
    send(chat_id, (
        "╔══════════════════════╗\n"
        "║   🧲 <b>MAGNIT DEMO</b>   ║\n"
        "╚══════════════════════╝\n\n"
        f"{t['balance']}: <b>{u['balance']:,} credits</b>\n"
        f"{t['invested']}: <b>{invested:,} credits</b>\n\n"
        "💡 All figures are virtual. No real funds."
    ), menu_markup(uid))

def show_plans(chat_id, uid):
    t = TEXT[lang(uid)]
    rows = [[(f"{name} · {amount:,} credits", f"open:{amount}")] for amount, name in PLANS.items()]
    rows.append([(t["back"], "home")])
    send(chat_id, say(uid, "plans"), keyboard(rows))

def open_position(chat_id, uid, amount):
    if amount not in PLANS:
        return
    c = db()
    c.execute("BEGIN IMMEDIATE")
    u = c.execute("SELECT balance FROM users WHERE uid=?", (uid,)).fetchone()
    if not u or u["balance"] < amount:
        c.rollback()
        send(chat_id, say(uid, "insufficient"), menu_markup(uid))
        return
    now = time.time()
    c.execute("UPDATE users SET balance=balance-? WHERE uid=?", (amount, uid))
    cur = c.execute("INSERT INTO positions(uid,plan,amount,opened) VALUES(?,?,?,?)", (uid, PLANS[amount], amount, now))
    pid = cur.lastrowid
    c.execute("INSERT INTO events(uid,kind,detail,created) VALUES(?,?,?,?)", (uid, "opened", str(pid), now))
    c.commit()
    t = TEXT[lang(uid)]
    rows = [[(t["close_btn"], f"choose:{pid}")], [(t["back"], "home")]]
    send(chat_id, say(uid, "opened", plan=PLANS[amount], amount=amount), keyboard(rows))

def show_portfolio(chat_id, uid):
    c = db()
    positions = c.execute("SELECT * FROM positions WHERE uid=? AND closed IS NULL ORDER BY id DESC LIMIT 20", (uid,)).fetchall()
    if not positions:
        send(chat_id, say(uid, "empty"), keyboard([[(say(uid, "open"), "plans")], [(say(uid, "back"), "home")]]))
        return
    rows = []
    for p in positions:
        rows.append([(f"#{p['id']} {p['plan']} · {p['amount']:,} credits", f"choose:{p['id']}")])
    rows.append([(say(uid, "back"), "home")])
    send(chat_id, say(uid, "portfolio_title") + "\n\n" + say(uid, "opened_list"), keyboard(rows))

def choose_close(chat_id, uid, pid):
    p = db().execute("SELECT id FROM positions WHERE uid=? AND id=? AND closed IS NULL", (uid, pid)).fetchone()
    if not p:
        send(chat_id, say(uid, "no_position"), menu_markup(uid))
        return
    t = TEXT[lang(uid)]
    send(chat_id, say(uid, "scenario"), keyboard([
        [(t["scenario_minus"], f"close:{pid}:-10"), (t["scenario_zero"], f"close:{pid}:0"), (t["scenario_plus"], f"close:{pid}:10")],
        [(t["back"], "portfolio")]]))

def close_position(chat_id, uid, pid, pct):
    if pct not in (-10, 0, 10):
        return
    c = db()
    c.execute("BEGIN IMMEDIATE")
    p = c.execute("SELECT * FROM positions WHERE uid=? AND id=? AND closed IS NULL", (uid, pid)).fetchone()
    if not p:
        c.rollback()
        send(chat_id, say(uid, "no_position"), menu_markup(uid))
        return
    change = p["amount"] * pct // 100
    now = time.time()
    c.execute("UPDATE positions SET closed=?,scenario=? WHERE id=?", (now, pct, pid))
    c.execute("UPDATE users SET balance=balance+? WHERE uid=?", (p["amount"] + change, uid))
    c.execute("INSERT INTO events(uid,kind,detail,created) VALUES(?,?,?,?)", (uid, "closed", f"{pid}:{pct}:{change}", now))
    c.commit()
    send(chat_id, say(uid, "closed", id=pid, pct=pct, change=change), menu_markup(uid))

def show_history(chat_id, uid):
    rows = db().execute("SELECT kind,detail,created FROM events WHERE uid=? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
    if not rows:
        send(chat_id, say(uid, "closed_list"), menu_markup(uid))
        return
    lines = []
    for e in rows:
        stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(e["created"]))
        if e["kind"] == "opened":
            p = db().execute("SELECT plan,amount FROM positions WHERE id=?", (int(e["detail"]),)).fetchone()
            label = f"🟢 Opened #{e['detail']}: {p['plan']} · {p['amount']:,} credits" if p else f"🟢 Opened #{e['detail']}"
        else:
            pid, pct, change = e["detail"].split(":")
            label = f"🔴 Closed #{pid}: {int(pct):+d}% · {int(change):+,} credits"
        lines.append(html.escape(stamp + " · " + label))
    send(chat_id, say(uid, "history_title") + "\n\n" + "\n".join(lines), menu_markup(uid))

def handle(update):
    if "callback_query" in update:
        cb = update["callback_query"]
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        message = cb.get("message") or {}
        chat = message.get("chat") or {}
        sender = cb.get("from") or {}
        if not chat.get("id") or not sender.get("id"):
            return
        uid, chat_id, data = sender["id"], chat["id"], cb.get("data", "")
        user(uid)
        if data == "language":
            c = db()
            nxt = "ru" if lang(uid) == "en" else "en"
            c.execute("UPDATE users SET language=? WHERE uid=?", (nxt, uid)); c.commit()
            send(chat_id, say(uid, "lang"), menu_markup(uid))
        elif data == "home":
            home(chat_id, uid)
        elif data == "plans":
            show_plans(chat_id, uid)
        elif data == "portfolio":
            show_portfolio(chat_id, uid)
        elif data == "history":
            show_history(chat_id, uid)
        elif data in ("risk", "about", "help"):
            send(chat_id, say(uid, data), menu_markup(uid))
        elif data.startswith("open:"):
            try: open_position(chat_id, uid, int(data.split(":")[1]))
            except (ValueError, IndexError): send(chat_id, "Invalid demo selection.", menu_markup(uid))
        elif data.startswith("choose:"):
            try: choose_close(chat_id, uid, int(data.split(":")[1]))
            except (ValueError, IndexError): send(chat_id, say(uid, "no_position"), menu_markup(uid))
        elif data.startswith("close:"):
            try:
                _, pid, pct = data.split(":")
                close_position(chat_id, uid, int(pid), int(pct))
            except (ValueError, IndexError): send(chat_id, say(uid, "no_position"), menu_markup(uid))
        return
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return
    raw = (msg.get("text") or "").strip()
    command = raw.split(maxsplit=1)[0].split("@", 1)[0].lower() if raw.startswith("/") else ""
    uid, chat_id = (msg.get("from") or {}).get("id"), chat.get("id")
    if not uid or not chat_id:
        return
    user(uid)
    if command in ("/start", "/menu"):
        home(chat_id, uid)
    elif command == "/dashboard":
        show_dashboard(chat_id, uid)
    elif command == "/help":
        send(chat_id, say(uid, "help"), menu_markup(uid))
    elif command == "/language":
        c = db(); nxt = "ru" if lang(uid) == "en" else "en"
        c.execute("UPDATE users SET language=? WHERE uid=?", (nxt, uid)); c.commit()
        send(chat_id, say(uid, "lang"), menu_markup(uid))

def get_offset():
    row = db().execute("SELECT v FROM kv WHERE k='offset'").fetchone()
    return int(row["v"]) if row else 0

def set_offset(value):
    c = db()
    c.execute("INSERT INTO kv(k,v) VALUES('offset',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(value),))
    c.commit()

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        connection = db()
        try:
            demo_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            connection.close()
            del LOCAL.conn
        healthy = bool(STATE["ok"] and STATE["last_poll"] and time.time() - STATE["last_poll"] < 90)
        body = {"ok": healthy, "revision": CFG.get("revision", ""),
                "replies": STATE["replies"], "last_reply": STATE["last_reply"],
                "last_error": STATE["last_error"], "bot": STATE["username"], "uptime_sec": round(time.time()-STATE["started"]),
                "last_poll_ago": round(time.time()-STATE["last_poll"]) if STATE["last_poll"] else None,
                "updates": STATE["updates"],
                "demo_users": demo_users}
        data = json.dumps(body).encode()
        self.send_response(200 if healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass

def main():
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN or config.json token.")
    me = api("getMe", {})
    if not me:
        raise SystemExit("Telegram getMe failed. Check the bot token and network.")
    STATE["username"] = me.get("username", "")
    if EXPECTED and STATE["username"].lower() != EXPECTED.lower():
        raise SystemExit("Token belongs to a different bot. Configuration was not accepted.")
    STATE["ok"] = True
    print(f"Magnit demo started as @{STATE['username']}. Virtual-only mode.", flush=True)
    if HEALTH_PORT:
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", HEALTH_PORT), Health)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        except OSError as exc:
            print("Health endpoint unavailable:", type(exc).__name__, flush=True)
    offset = get_offset()
    while True:
        updates = api("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]})
        STATE["last_poll"] = time.time()
        if updates is None:
            STATE["ok"] = False
            time.sleep(3)
            continue
        STATE["ok"] = True
        STATE["last_error"] = ""
        for item in updates:
            try:
                handle(item)
            except Exception as exc:
                print("Update handler failed:", item.get("update_id"), type(exc).__name__, flush=True)
            offset = item["update_id"] + 1
            set_offset(offset)
            STATE["last_update"] = time.time()
            STATE["updates"] += 1

if __name__ == "__main__":
    main()
