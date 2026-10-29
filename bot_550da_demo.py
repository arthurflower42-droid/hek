#!/usr/bin/env python3
"""550D&A HYIP demo bot — educational reconstruction. No real funds, no real trading."""

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
DB_NAME = os.environ.get("DATABASE") or CFG.get("database") or "da550-demo.sqlite3"
DB_PATH = DB_NAME if os.path.isabs(DB_NAME) else os.path.join(HERE, DB_NAME)
try:
    HEALTH_PORT = int(os.environ.get("HEALTH_PORT") or CFG.get("health_port") or 0)
except (ValueError, TypeError):
    HEALTH_PORT = 0
API = "https://api.telegram.org/bot" + TOKEN + "/"
STATE = {
    "started": time.time(),
    "last_update": 0,
    "last_poll": 0,
    "updates": 0,
    "username": "",
    "ok": False,
}
LOCAL = threading.local()
REF_COMMISSIONS = {1: 0.10, 2: 0.03, 3: 0.01, 4: 0.01}
DAILY_RATE = 0.03
MIN_DEPOSIT = 50

TEXT = {
    "en": {
        "welcome": (
            "╔══════════════════════╗\n"
            "║  💰 <b>550D&A INVEST</b>  ║\n"
            "║  AI Trading Platform ║\n"
            "╚══════════════════════╝\n\n"
            "🤖 <b>Welcome to 550D&A!</b>\n\n"
            "📊 Earn <b>3% daily</b> on your deposits\n"
            "👥 <b>4-level</b> referral program\n"
            "💎 Minimum deposit: <b>$50</b>\n\n"
            "⚠️ <b>DEMO VERSION</b> — virtual credits only\n"
            "No real money, no real trading."
        ),
        "menu": "📋 <b>Main Menu</b>",
        "dashboard": (
            "╔══════════════════════╗\n"
            "║  💰 <b>550D&A DASHBOARD</b> ║\n"
            "╚══════════════════════╝\n\n"
            "💵 <b>Balance:</b> ${balance:,.2f}\n"
            "📥 <b>Total Deposited:</b> ${deposited:,.2f}\n"
            "📈 <b>Total Earned:</b> ${earned:,.2f}\n"
            "👥 <b>Referrals:</b> {refs} users\n"
            "💎 <b>Referral Earnings:</b> ${ref_earned:,.2f}\n\n"
            "📊 <i>Daily rate: 3% · Next accrual in {next_accrual}</i>"
        ),
        "deposit": (
            "💳 <b>Make a Deposit</b>\n\n"
            "Choose your investment amount:\n"
            "• Minimum: $50\n"
            "• Daily return: 3%\n"
            "• Returns accrue for 30 days\n\n"
            "⚠️ Demo credits only — no real deposit."
        ),
        "deposit_ok": (
            "✅ <b>Deposit Successful!</b>\n\n"
            "💰 Amount: <b>${amount:,.2f}</b>\n"
            "📊 Daily return: <b>${daily:,.2f}</b> (3%)\n"
            "📅 First accrual: in 24 hours\n\n"
            "⚠️ Demo credits only."
        ),
        "insufficient": "❌ <b>Insufficient Balance</b>\n\nYou don't have enough demo credits.",
        "withdraw": (
            "💸 <b>Withdraw Funds</b>\n\n"
            "Available balance: <b>${balance:,.2f}</b>\n\n"
            "Choose amount to withdraw:\n"
            "⚠️ Demo — no real withdrawal processed."
        ),
        "withdraw_ok": (
            "✅ <b>Withdrawal Requested</b>\n\n"
            "💰 Amount: <b>${amount:,.2f}</b>\n"
            "⏳ Processing time: up to 48 hours\n\n"
            "⚠️ Demo — no real funds transferred."
        ),
        "withdraw_pending": ("⏳ <b>Pending Withdrawals</b>\n\n{list}\n\n⚠️ Demo only."),
        "referral": (
            "👥 <b>Referral Program</b>\n\n"
            "Your referral link:\n"
            "<code>https://t.me/{bot}?start={uid}</code>\n\n"
            "📊 <b>Commission Structure:</b>\n"
            "• Level 1: 10%\n"
            "• Level 2: 3%\n"
            "• Level 3: 1%\n"
            "• Level 4: 1%\n\n"
            "👥 Your referrals: <b>{count}</b>\n"
            "💎 Total earned: <b>${earned:,.2f}</b>"
        ),
        "history": "📜 <b>Transaction History</b>",
        "no_history": "📭 No transactions yet.",
        "about": (
            "ℹ️ <b>About 550D&A</b>\n\n"
            "550D&A claims to use AI-powered trading to generate 3% daily returns.\n\n"
            "⚠️ <b>THIS IS A DEMO RECONSTRUCTION</b>\n"
            "• No real AI trading\n"
            "• No real deposits\n"
            "• No real withdrawals\n"
            "• Educational purpose only\n\n"
            "The real 550D&A bot shows similar patterns to known HYIP schemes."
        ),
        "risk": (
            "⚠️ <b>Risk Warning</b>\n\n"
            "• 3% daily = ~2,000,000% yearly (compound)\n"
            "• No verified trading history exists\n"
            "• No audited financial statements\n"
            "• Referral-heavy structure = recruitment incentive\n"
            "• Pattern matches documented Ponzi schemes\n\n"
            "This demo exists to illustrate the mechanics.\n"
            "Never deposit real money into unverified platforms."
        ),
        "lang": "✅ Language set to English 🇬🇧",
        "deposit_btn": "💳 Deposit",
        "withdraw_btn": "💸 Withdraw",
        "referral_btn": "👥 Referrals",
        "history_btn": "📜 History",
        "about_btn": "ℹ️ About",
        "risk_btn": "⚠️ Risks",
        "back": "◀️ Back",
        "amount_50": "$50",
        "amount_100": "$100",
        "amount_500": "$500",
        "amount_1000": "$1,000",
        "withdraw_all": "💸 Withdraw All",
        "withdraw_half": "💸 Withdraw 50%",
        "withdraw_custom": "✏️ Custom Amount",
        "lang_btn": "🌐 Русский / English",
    },
    "ru": {
        "welcome": (
            "╔══════════════════════╗\n"
            "║  💰 <b>550D&A INVEST</b>  ║\n"
            "║  AI Торговая Платформа║\n"
            "╚══════════════════════╝\n\n"
            "🤖 <b>Добро пожаловать в 550D&A!</b>\n\n"
            "📊 Зарабатывайте <b>3% в день</b> на депозитах\n"
            "👥 <b>4-уровневая</b> реферальная программа\n"
            "💎 Минимальный депозит: <b>$50</b>\n\n"
            "⚠️ <b>ДЕМО-ВЕРСИЯ</b> — только виртуальные кредиты\n"
            "Реальных денег и торговли нет."
        ),
        "menu": "📋 <b>Главное Меню</b>",
        "dashboard": (
            "╔══════════════════════╗\n"
            "║  💰 <b>550D&A КАБИНЕТ</b> ║\n"
            "╚══════════════════════╝\n\n"
            "💵 <b>Баланс:</b> ${balance:,.2f}\n"
            "📥 <b>Всего внесено:</b> ${deposited:,.2f}\n"
            "📈 <b>Заработано:</b> ${earned:,.2f}\n"
            "👥 <b>Рефералы:</b> {refs} чел.\n"
            "💎 <b>Реф. доход:</b> ${ref_earned:,.2f}\n\n"
            "📊 <i>Дневная ставка: 3% · След. начисление через {next_accrual}</i>"
        ),
        "deposit": (
            "💳 <b>Сделать Депозит</b>\n\n"
            "Выберите сумму инвестиции:\n"
            "• Минимум: $50\n"
            "• Дневной доход: 3%\n"
            "• Начисления идут 30 дней\n\n"
            "⚠️ Только демо-кредиты — реальных депозитов нет."
        ),
        "deposit_ok": (
            "✅ <b>Депозит Успешен!</b>\n\n"
            "💰 Сумма: <b>${amount:,.2f}</b>\n"
            "📊 Дневной доход: <b>${daily:,.2f}</b> (3%)\n"
            "📅 Первое начисление: через 24 часа\n\n"
            "⚠️ Только демо-кредиты."
        ),
        "insufficient": "❌ <b>Недостаточно Средств</b>\n\nУ вас не хватает демо-кредитов.",
        "withdraw": (
            "💸 <b>Вывод Средств</b>\n\n"
            "Доступный баланс: <b>${balance:,.2f}</b>\n\n"
            "Выберите сумму для вывода:\n"
            "⚠️ Демо — реальных переводов нет."
        ),
        "withdraw_ok": (
            "✅ <b>Заявка на Вывод</b>\n\n"
            "💰 Сумма: <b>${amount:,.2f}</b>\n"
            "⏳ Время обработки: до 48 часов\n\n"
            "⚠️ Демо — реальные средства не переводятся."
        ),
        "withdraw_pending": ("⏳ <b>Ожидают Вывода</b>\n\n{list}\n\n⚠️ Только демо."),
        "referral": (
            "👥 <b>Реферальная Программа</b>\n\n"
            "Ваша реферальная ссылка:\n"
            "<code>https://t.me/{bot}?start={uid}</code>\n\n"
            "📊 <b>Структура Комиссий:</b>\n"
            "• Уровень 1: 10%\n"
            "• Уровень 2: 3%\n"
            "• Уровень 3: 1%\n"
            "• Уровень 4: 1%\n\n"
            "👥 Ваши рефералы: <b>{count}</b>\n"
            "💎 Всего заработано: <b>${earned:,.2f}</b>"
        ),
        "history": "📜 <b>История Операций</b>",
        "no_history": "📭 Операций пока нет.",
        "about": (
            "ℹ️ <b>О 550D&A</b>\n\n"
            "550D&A заявляет об использовании AI-трейдинга для генерации 3% дневного дохода.\n\n"
            "⚠️ <b>ЭТО ДЕМО-РЕКОНСТРУКЦИЯ</b>\n"
            "• Нет реального AI-трейдинга\n"
            "• Нет реальных депозитов\n"
            "• Нет реальных выводов\n"
            "• Только для образовательных целей\n\n"
            "Настоящий бот 550D&A показывает паттерны, типичные для HYIP-схем."
        ),
        "risk": (
            "⚠️ <b>Предупреждение о Рисках</b>\n\n"
            "• 3% в день = ~2 000 000% годовых (сложный %)\n"
            "• Нет подтверждённой торговой истории\n"
            "• Нет аудированной отчётности\n"
            "• Упор на рефералов = стимул вербовать\n"
            "• Паттерн совпадает с документированными схемами Понци\n\n"
            "Это демо иллюстрирует механику.\n"
            "Никогда не вносите реальные деньги в непроверенные платформы."
        ),
        "lang": "✅ Язык изменён на русский 🇷🇺",
        "deposit_btn": "💳 Депозит",
        "withdraw_btn": "💸 Вывод",
        "referral_btn": "👥 Рефералы",
        "history_btn": "📜 История",
        "about_btn": "ℹ️ О проекте",
        "risk_btn": "⚠️ Риски",
        "back": "◀️ Назад",
        "amount_50": "$50",
        "amount_100": "$100",
        "amount_500": "$500",
        "amount_1000": "$1 000",
        "withdraw_all": "💸 Вывести Всё",
        "withdraw_half": "💸 Вывести 50%",
        "withdraw_custom": "✏️ Своя Сумма",
        "lang_btn": "🌐 Русский / English",
    },
}


def db():
    conn = getattr(LOCAL, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY, language TEXT NOT NULL DEFAULT 'en',
            balance REAL NOT NULL DEFAULT 0, deposited REAL NOT NULL DEFAULT 0,
            earned REAL NOT NULL DEFAULT 0, ref_earned REAL NOT NULL DEFAULT 0,
            referrer INTEGER, ref_level INTEGER, created REAL NOT NULL,
            last_accrual REAL NOT NULL DEFAULT 0)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
            amount REAL NOT NULL, daily REAL NOT NULL, created REAL NOT NULL,
            days_paid INTEGER NOT NULL DEFAULT 0, max_days INTEGER NOT NULL DEFAULT 30)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
            kind TEXT NOT NULL, amount REAL NOT NULL, detail TEXT,
            created REAL NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
            amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created REAL NOT NULL)""")
        conn.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
        conn.commit()
        LOCAL.conn = conn
    return conn


def user(uid, referrer=None):
    c = db()
    now = time.time()
    row = c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        ref_id = None
        ref_level = None
        if referrer and referrer != uid:
            ref_row = c.execute(
                "SELECT uid FROM users WHERE uid=?", (referrer,)
            ).fetchone()
            if ref_row:
                ref_id = referrer
                ref_level = 1
        c.execute(
            """INSERT INTO users(uid, balance, deposited, earned, ref_earned,
                     referrer, ref_level, created, last_accrual)
                     VALUES(?, 100, 0, 0, 0, ?, ?, ?, ?)""",
            (uid, ref_id, ref_level, now, now),
        )
        c.commit()
        if ref_id:
            process_referral_bonus(uid, ref_id, 100)
        return c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
    return row


def process_referral_bonus(new_uid, referrer_uid, deposit_amount):
    c = db()
    current = referrer_uid
    level = 1
    while current and level <= 4:
        ref_row = c.execute("SELECT * FROM users WHERE uid=?", (current,)).fetchone()
        if not ref_row:
            break
        commission = deposit_amount * REF_COMMISSIONS[level]
        c.execute(
            "UPDATE users SET balance=balance+?, ref_earned=ref_earned+? WHERE uid=?",
            (commission, commission, current),
        )
        c.execute(
            """INSERT INTO transactions(uid, kind, amount, detail, created)
                     VALUES(?, 'ref_commission', ?, ?, ?)""",
            (current, commission, f"Level {level} from user {new_uid}", time.time()),
        )
        current = ref_row["referrer"]
        level += 1
    c.commit()


def lang(uid):
    return user(uid)["language"]


def say(uid, key, **kwargs):
    return TEXT[lang(uid)][key].format(**kwargs)


def keyboard(rows):
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for label, data in row]
            for row in rows
        ]
    }


def menu_markup(uid):
    t = TEXT[lang(uid)]
    return keyboard(
        [
            [(t["deposit_btn"], "deposit"), (t["withdraw_btn"], "withdraw")],
            [(t["referral_btn"], "referral"), (t["history_btn"], "history")],
            [(t["about_btn"], "about"), (t["risk_btn"], "risk")],
            [(t["lang_btn"], "language")],
        ]
    )


def api(method, payload):
    req = urllib.request.Request(
        API + method,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read(2_000_000))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print("Telegram request failed:", method, type(exc).__name__, flush=True)
        return None
    if not result.get("ok"):
        print(
            "Telegram API error:",
            method,
            result.get("error_code", "?"),
            result.get("description", "unknown error"),
            flush=True,
        )
        return None
    return result.get("result")


def send(chat_id, body, markup=None):
    payload = {
        "chat_id": chat_id,
        "text": body,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if markup:
        payload["reply_markup"] = markup
    api("sendMessage", payload)


def home(chat_id, uid):
    send(chat_id, say(uid, "welcome") + "\n\n" + say(uid, "menu"), menu_markup(uid))


def show_dashboard(chat_id, uid):
    u = user(uid)
    now = time.time()
    next_accrual = max(0, 86400 - (now - u["last_accrual"]))
    hours = int(next_accrual // 3600)
    mins = int((next_accrual % 3600) // 60)
    send(
        chat_id,
        say(
            uid,
            "dashboard",
            balance=u["balance"],
            deposited=u["deposited"],
            earned=u["earned"],
            refs=count_referrals(uid),
            ref_earned=u["ref_earned"],
            next_accrual=f"{hours}h {mins}m",
        ),
        menu_markup(uid),
    )


def count_referrals(uid):
    return (
        db()
        .execute("SELECT COUNT(*) FROM users WHERE referrer=?", (uid,))
        .fetchone()[0]
    )


def show_deposit(chat_id, uid):
    t = TEXT[lang(uid)]
    send(
        chat_id,
        say(uid, "deposit"),
        keyboard(
            [
                [
                    (t["amount_50"], "do_deposit:50"),
                    (t["amount_100"], "do_deposit:100"),
                ],
                [
                    (t["amount_500"], "do_deposit:500"),
                    (t["amount_1000"], "do_deposit:1000"),
                ],
                [(t["back"], "home")],
            ]
        ),
    )


def do_deposit(chat_id, uid, amount):
    if amount < MIN_DEPOSIT:
        return
    c = db()
    c.execute("BEGIN IMMEDIATE")
    u = c.execute("SELECT balance FROM users WHERE uid=?", (uid,)).fetchone()
    if not u or u["balance"] < amount:
        c.rollback()
        send(chat_id, say(uid, "insufficient"), menu_markup(uid))
        return
    now = time.time()
    daily = amount * DAILY_RATE
    c.execute(
        "UPDATE users SET balance=balance-?, deposited=deposited+? WHERE uid=?",
        (amount, amount, uid),
    )
    c.execute(
        "INSERT INTO deposits(uid, amount, daily, created) VALUES(?,?,?,?)",
        (uid, amount, daily, now),
    )
    c.execute(
        "INSERT INTO transactions(uid, kind, amount, detail, created) VALUES(?, 'deposit', ?, 'Deposit', ?)",
        (uid, amount, now),
    )
    c.commit()
    send(chat_id, say(uid, "deposit_ok", amount=amount, daily=daily), menu_markup(uid))


def show_withdraw(chat_id, uid):
    u = user(uid)
    t = TEXT[lang(uid)]
    send(
        chat_id,
        say(uid, "withdraw", balance=u["balance"]),
        keyboard(
            [
                [(t["withdraw_all"], f"do_withdraw:{u['balance']:.0f}")],
                [(t["withdraw_half"], f"do_withdraw:{u['balance'] / 2:.0f}")],
                [(t["back"], "home")],
            ]
        ),
    )


def do_withdraw(chat_id, uid, amount):
    c = db()
    c.execute("BEGIN IMMEDIATE")
    u = c.execute("SELECT balance FROM users WHERE uid=?", (uid,)).fetchone()
    if not u or u["balance"] < amount or amount <= 0:
        c.rollback()
        send(chat_id, say(uid, "insufficient"), menu_markup(uid))
        return
    now = time.time()
    c.execute("UPDATE users SET balance=balance-? WHERE uid=?", (amount, uid))
    c.execute(
        "INSERT INTO withdrawals(uid, amount, created) VALUES(?,?,?)",
        (uid, amount, now),
    )
    c.execute(
        "INSERT INTO transactions(uid, kind, amount, detail, created) VALUES(?, 'withdraw', ?, 'Pending', ?)",
        (uid, amount, now),
    )
    c.commit()
    send(chat_id, say(uid, "withdraw_ok", amount=amount), menu_markup(uid))


def show_referral(chat_id, uid):
    u = user(uid)
    bot_name = STATE.get("username", "DA550_bot")
    send(
        chat_id,
        say(
            uid,
            "referral",
            bot=bot_name,
            uid=uid,
            count=count_referrals(uid),
            earned=u["ref_earned"],
        ),
        menu_markup(uid),
    )


def show_history(chat_id, uid):
    rows = (
        db()
        .execute(
            "SELECT kind, amount, detail, created FROM transactions WHERE uid=? ORDER BY id DESC LIMIT 15",
            (uid,),
        )
        .fetchall()
    )
    if not rows:
        send(chat_id, say(uid, "no_history"), menu_markup(uid))
        return
    lines = []
    for r in rows:
        stamp = time.strftime("%d.%m %H:%M", time.gmtime(r["created"]))
        emoji = {
            "deposit": "📥",
            "withdraw": "📤",
            "accrual": "📈",
            "ref_commission": "👥",
        }.get(r["kind"], "•")
        lines.append(
            f"{emoji} <b>{stamp}</b> — {r['kind']}: ${r['amount']:,.2f} — {r['detail']}"
        )
    send(chat_id, say(uid, "history") + "\n\n" + "\n".join(lines), menu_markup(uid))


def process_accruals():
    """Run periodically to simulate daily 3% accruals."""
    while True:
        try:
            c = db()
            now = time.time()
            deposits = c.execute(
                "SELECT * FROM deposits WHERE days_paid < max_days AND created + (days_paid+1)*86400 <= ?",
                (now,),
            ).fetchall()
            for d in deposits:
                c.execute("BEGIN IMMEDIATE")
                c.execute(
                    "UPDATE users SET balance=balance+?, earned=earned+? WHERE uid=?",
                    (d["daily"], d["daily"], d["uid"]),
                )
                c.execute(
                    "UPDATE deposits SET days_paid=days_paid+1 WHERE id=?", (d["id"],)
                )
                c.execute(
                    "UPDATE users SET last_accrual=? WHERE uid=?", (now, d["uid"])
                )
                c.execute(
                    """INSERT INTO transactions(uid, kind, amount, detail, created)
                             VALUES(?, 'accrual', ?, ?, ?)""",
                    (d["uid"], d["daily"], f"Daily 3% on deposit #{d['id']}", now),
                )
                c.commit()
        except Exception as e:
            print("Accrual error:", type(e).__name__, flush=True)
        time.sleep(300)


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
            c.execute("UPDATE users SET language=? WHERE uid=?", (nxt, uid))
            c.commit()
            send(chat_id, say(uid, "lang"), menu_markup(uid))
        elif data == "home":
            show_dashboard(chat_id, uid)
        elif data == "deposit":
            show_deposit(chat_id, uid)
        elif data.startswith("do_deposit:"):
            try:
                do_deposit(chat_id, uid, float(data.split(":")[1]))
            except (ValueError, IndexError):
                pass
        elif data == "withdraw":
            show_withdraw(chat_id, uid)
        elif data.startswith("do_withdraw:"):
            try:
                do_withdraw(chat_id, uid, float(data.split(":")[1]))
            except (ValueError, IndexError):
                pass
        elif data == "referral":
            show_referral(chat_id, uid)
        elif data == "history":
            show_history(chat_id, uid)
        elif data in ("about", "risk"):
            send(chat_id, say(uid, data), menu_markup(uid))
        return
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return
    raw = (msg.get("text") or "").strip()
    command = (
        raw.split(maxsplit=1)[0].split("@", 1)[0].lower() if raw.startswith("/") else ""
    )
    uid, chat_id = (msg.get("from") or {}).get("id"), chat.get("id")
    if not uid or not chat_id:
        return
    referrer = None
    if raw.startswith("/start ") and len(raw) > 7:
        try:
            referrer = int(raw[7:].strip())
        except ValueError:
            pass
    user(uid, referrer)
    if command in ("/start", "/menu"):
        show_dashboard(chat_id, uid)
    elif command == "/dashboard":
        show_dashboard(chat_id, uid)


def get_offset():
    row = db().execute("SELECT v FROM kv WHERE k='offset'").fetchone()
    return int(row["v"]) if row else 0


def set_offset(value):
    c = db()
    c.execute(
        "INSERT INTO kv(k,v) VALUES('offset',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (str(value),),
    )
    c.commit()


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        body = {
            "ok": STATE["ok"],
            "bot": STATE["username"],
            "uptime_sec": round(time.time() - STATE["started"]),
            "last_poll_ago": round(time.time() - STATE["last_poll"])
            if STATE["last_poll"]
            else None,
            "updates": STATE["updates"],
            "demo_users": db().execute("SELECT COUNT(*) FROM users").fetchone()[0],
        }
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
    STATE["ok"] = True
    print(
        f"550D&A demo started as @{STATE['username']}. Virtual-only mode.", flush=True
    )
    if HEALTH_PORT:
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", HEALTH_PORT), Health)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        except OSError as exc:
            print("Health endpoint unavailable:", type(exc).__name__, flush=True)
    threading.Thread(target=process_accruals, daemon=True).start()
    offset = get_offset()
    while True:
        updates = api(
            "getUpdates",
            {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            },
        )
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
                print(
                    "Update handler failed:",
                    item.get("update_id"),
                    type(exc).__name__,
                    flush=True,
                )
            offset = item["update_id"] + 1
            set_offset(offset)
            STATE["last_update"] = time.time()
            STATE["updates"] += 1


if __name__ == "__main__":
    main()
