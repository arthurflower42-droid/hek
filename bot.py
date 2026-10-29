#!/usr/bin/env python3
"""МАГНИТ — образовательный Telegram-бот: на что смотреть, чтобы не потерять деньги
на финансовых площадках.

Настройки берутся из config.json рядом с ботом (token, expected_username,
health_port, database); любое значение можно переопределить переменной окружения
(TELEGRAM_BOT_TOKEN, HEALTH_PORT, DATABASE). Токен в лог и в текст ошибок не попадает.
"""
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
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

# Живое состояние для health-эндпоинта.
STATE = {"started": time.time(), "last_update": 0.0, "last_poll": 0.0, "updates": 0, "username": "", "ok": False}

MECHANISMS = [
    ("reported", "Показанная доходность",
     "На экране рисуют прибыль, которой может не быть на самом деле. Это подталкивает вносить всё больше."),
    ("payouts", "Выплаты за счёт новых вкладов",
     "Деньги новых вкладчиков идут на выплаты прежним — создаётся видимость прибыльного бизнеса. Это признак пирамиды."),
    ("withdrawals", "Платежи перед выводом",
     "Перед выводом просят доплатить «налог», «проверку» или «разблокировку». Эти деньги, как правило, тоже не возвращаются."),
    ("fees", "Комиссии и цена сделки",
     "Скрытые сборы и невыгодная цена исполнения незаметно перекладывают ваши деньги оператору."),
    ("referrals", "Заработок на приглашённых",
     "Промоутеры получают процент за новых вкладчиков — независимо от того, заработают те или потеряют."),
    ("volume", "Поощрение частых сделок",
     "Оператор зарабатывает на комиссии с оборота, поэтому подталкивает торговать чаще — даже когда вы в минусе."),
    ("positions", "Ставка против клиента",
     "Часть дилеров зарабатывает на ваших убытках по позициям, которые держит у себя. При лицензии и честном раскрытии это законно; скрытая манипуляция — отдельная проблема."),
    ("closure", "Остановка выплат",
     "Собирают вклады, а потом ограничивают вывод или просто закрываются."),
]
BY_ID = {row[0]: row for row in MECHANISMS}


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


# ---------------------------------------------------------------- база (sqlite)
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


# ---------------------------------------------------------------- тексты и меню
def keyboard():
    rows = []
    for start in range(0, len(MECHANISMS), 2):
        rows.append([{"text": MECHANISMS[i][1], "callback_data": "m:" + MECHANISMS[i][0]}
                     for i in range(start, min(start + 2, len(MECHANISMS)))])
    rows.append([{"text": "⚠ Памятка безопасности", "callback_data": "safety"}])
    return {"inline_keyboard": rows}


def home():
    return (
        "<b>Как площадки зарабатывают на вкладчиках</b>\n\n"
        "Здесь — простым языком о том, как некоторые платформы делают деньги и на что стоит "
        "обращать внимание. Это признаки риска, а не доказательство, что конкретная компания — мошенники.\n\n"
        "Выберите, о чём рассказать подробнее:"
    )


def safety():
    return (
        "<b>Перед тем как отправить деньги</b>\n\n"
        "• Проверьте компанию и её лицензию у финансового регулятора.\n"
        "• Убедитесь, что вывод работает без дополнительных платежей за «разблокировку» или «налог».\n"
        "• Гарантированная доходность и давление «приведи друзей» — тревожные признаки.\n"
        "• Самостоятельно сверяйте выписки и историю сделок.\n"
        "• Никому не сообщайте пароли, seed-фразы и не давайте удалённый доступ.\n\n"
        "Если деньги уже под угрозой — срочно свяжитесь с банком или платёжной системой и сообщите своему регулятору."
    )


def back_row():
    return [{"text": "← Все признаки", "callback_data": "home"}]


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
        if key == "home":
            send(chat_id, home(), keyboard())
        elif key == "safety":
            send(chat_id, safety(), {"inline_keyboard": [back_row()]})
        elif key.startswith("m:") and key[2:] in BY_ID:
            _, title, description = BY_ID[key[2:]]
            send(chat_id, "<b>" + title + "</b>\n\n" + description,
                 {"inline_keyboard": [back_row(), [{"text": "⚠ Памятка безопасности", "callback_data": "safety"}]]})
        return
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return
    text = (message.get("text") or "").strip()
    if text.startswith(("/start", "/help", "/menu")):
        seen((message.get("from") or {}).get("id") or chat.get("id"))
        click("/start")
        send(chat["id"], home(), keyboard())


# ---------------------------------------------------------------- health-сервер
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


# ---------------------------------------------------------------- запуск
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
                # Payload и URL не логируем: в URL Telegram лежит токен.
                pass
        if updates:
            set_offset(offset)


if __name__ == "__main__":
    main()
