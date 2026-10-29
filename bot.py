#!/usr/bin/env python3
"""Magnit paper-trading demo. Standard library only; no real funds or exchange."""
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
try:
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
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
STATE = {"started": time.time(), "last_update": 0, "last_poll": 0, "updates": 0, "username": "", "ok": False}
LOCAL = threading.local()
SEED = 10000
PLANS = {100: "Starter", 500: "Explorer", 1000: "Strategist"}
TEXT = {
 "en": {
  "welcome": "<b>MAGNIT | PAPER TRADING DEMO</b>\n\nExplore a fictional portfolio using virtual credits. No real money, deposits, withdrawals, trading, or investment returns are involved.",
  "menu": "Choose a demo screen:",
  "balance": "Virtual balance", "invested": "In open demos", "portfolio": "Portfolio",
  "plans": "<b>Choose a demo size</b>\n\nOpening a demo position moves virtual credits into your portfolio. It does not place a real trade.",
  "opened": "Demo position opened: <b>{plan}</b> for {amount:,} credits. No real trade was placed.",
  "insufficient": "Not enough virtual credits. Close an open demo position first.",
  "empty": "No open demo positions yet. Choose a demo size to create one.",
  "portfolio_title": "<b>Your demo portfolio</b>",
  "history_title": "<b>Demo activity</b>",
  "closed": "Closed demo position #{id} with a hypothetical {pct:+d}% scenario. Virtual change: {change:+,} credits.",
  "risk": "<b>Risk notes</b>\n\n• Markets can move against you, including loss of the full amount.\n• Past results do not predict future results.\n• This bot uses invented demo data and makes no forecasts.\n• Never share passwords, recovery phrases, or payment details.",
  "about": "<b>About this demo</b>\n\nMagnit is a fictional paper-trading interface for exploring Telegram bot navigation and a virtual portfolio. It is not a broker, exchange, or offer to invest.",
  "help": "Use /start for the menu. Open a demo position, then close it with a hypothetical -10%, 0%, or +10% scenario. Every amount is virtual.",
  "opened_list": "Open demo positions:",
  "closed_list": "No activity yet.",
  "lang": "Language set to English.",
  "open": "Open demo", "portfolio_btn": "Portfolio", "history_btn": "Activity",
  "plans_btn": "Demo plans", "risk_btn": "Risk notes", "about_btn": "About", "help_btn": "Help",
  "back": "← Menu", "close": "Close", "scenario": "Choose a hypothetical demo scenario:",
  "close_btn": "Close position", "scenario_minus": "−10%", "scenario_zero": "0%", "scenario_plus": "+10%",
  "lang_btn": "Русский / English", "no_position": "That demo position is not open."
 },
 "ru": {
  "welcome": "<b>МАГНИТ | ДЕМО-СИМУЛЯТОР</b>\n\nИзучайте вымышленный портфель на виртуальных кредитах. Реальных денег, пополнений, выводов, сделок и доходности здесь нет.",
  "menu": "Выберите экран демо:",
  "balance": "Виртуальный баланс", "invested": "В открытых демо-сделках", "portfolio": "Портфель",
  "plans": "<b>Выберите размер демо-сделки</b>\n\nКредиты переместятся в виртуальный портфель. Реальная сделка не совершается.",
  "opened": "Демо-позиция открыта: <b>{plan}</b>, {amount:,} кредитов. Реальная сделка не совершалась.",
  "insufficient": "Недостаточно виртуальных кредитов. Сначала закройте открытую демо-позицию.",
  "empty": "Открытых демо-позиций пока нет. Выберите размер демо-сделки.",
  "portfolio_title": "<b>Ваш демо-портфель</b>",
  "history_title": "<b>Демо-операции</b>",
  "closed": "Демо-позиция №{id} закрыта со сценарием {pct:+d}%. Виртуальное изменение: {change:+,} кредитов.",
  "risk": "<b>О рисках</b>\n\n• Рынок может двигаться против вас, вплоть до полной потери суммы.\n• Прошлые результаты не предсказывают будущие.\n• Здесь вымышленные данные, бот не делает прогнозов.\n• Не отправляйте пароли, фразы восстановления и платёжные данные.",
  "about": "<b>О демо</b>\n\nМагнит — вымышленный интерфейс для знакомства с Telegram-ботом и виртуальным портфелем. Это не брокер, не биржа и не предложение инвестировать.",
  "help": "Команда /start открывает меню. Откройте демо-позицию и закройте её гипотетическим сценарием −10%, 0% или +10%. Все суммы виртуальные.",
  "opened_list": "Открытые демо-позиции:",
  "closed_list": "Операций пока нет.",
  "lang": "Язык изменён на русский.",
  "open": "Открыть демо", "portfolio_btn": "Портфель", "history_btn": "Операции",
  "plans_btn": "Размер демо", "risk_btn": "О рисках", "about_btn": "О проекте", "help_btn": "Помощь",
  "back": "← Меню", "close": "Закрыть", "scenario": "Выберите гипотетический демо-сценарий:",
  "close_btn": "Закрыть позицию", "scenario_minus": "−10%", "scenario_zero": "0%", "scenario_plus": "+10%",
  "lang_btn": "Русский / English", "no_position": "Эта демо-позиция уже закрыта или не существует."
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
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
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
    api("sendMessage", payload)

def home(chat_id, uid):
    send(chat_id, say(uid, "welcome") + "\n\n" + say(uid, "menu"), menu_markup(uid))

def show_dashboard(chat_id, uid):
    u = user(uid)
    invested = db().execute("SELECT COALESCE(SUM(amount),0) FROM positions WHERE uid=? AND closed IS NULL", (uid,)).fetchone()[0]
    t = TEXT[lang(uid)]
    send(chat_id, "<b>MAGNIT | DEMO</b>\n\n"
         + html.escape(t["balance"]) + ": <b>%s credits</b>\n" % format(u["balance"], ",")
         + html.escape(t["invested"]) + ": <b>%s credits</b>\n\n" % format(invested, ",")
         + "All figures are virtual. No real funds or trading.", menu_markup(uid))

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
            label = f"Opened demo #{e['detail']}: {p['plan']} · {p['amount']:,} credits" if p else f"Opened demo #{e['detail']}"
        else:
            pid, pct, change = e["detail"].split(":")
            label = f"Closed demo #{pid}: hypothetical {int(pct):+d}% · {int(change):+,} credits"
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
        body = {"ok": STATE["ok"], "bot": STATE["username"], "uptime_sec": round(time.time()-STATE["started"]),
                "last_poll_ago": round(time.time()-STATE["last_poll"]) if STATE["last_poll"] else None,
                "updates": STATE["updates"],
                "demo_users": db().execute("SELECT COUNT(*) FROM users").fetchone()[0]}
        data = json.dumps(body).encode()
        self.send_response(200 if STATE["ok"] else 503)
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
        print(f"Warning: token belongs to @{STATE['username']}, expected @{EXPECTED}.", flush=True)
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
