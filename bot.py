#!/usr/bin/env python3
"""Educational Telegram guide to warning signs in financial platforms.

Set TELEGRAM_BOT_TOKEN in the process environment before running.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API = "https://api.telegram.org/bot" + TOKEN + "/"
MECHANISMS = [
    ("reported", "Reported returns", "The dashboard displays gains that may not reflect actual performance, encouraging larger deposits."),
    ("payouts", "Deposit-funded payouts", "New deposits support earlier withdrawals, creating the appearance of a profitable business."),
    ("withdrawals", "Withdrawal requirements", "Users are asked to pay additional “tax,” “verification,” or “unlock” charges before withdrawing. These payments may also remain unrecovered."),
    ("fees", "Fees and execution practices", "Additional charges or unfavorable trade prices transfer value from customers to the operator."),
    ("referrals", "Referral-based recruitment", "Promoters receive commissions for bringing in depositors, regardless of whether those depositors profit."),
    ("volume", "Trading-volume incentives", "Operators earn transaction commissions, encouraging frequent trades even when customers experience overall losses."),
    ("positions", "Opposing customer positions", "Some dealers profit from customer losses on positions they retain. This arrangement can be legitimate when properly regulated and disclosed; undisclosed manipulation is a separate concern."),
    ("closure", "Withdrawal discontinuation", "Operators collect deposits, then restrict withdrawals or discontinue operations."),
]
BY_ID = {row[0]: row for row in MECHANISMS}

def call(method, payload):
    request = urllib.request.Request(
        API + method,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            result = json.loads(response.read(1_000_000))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    return result.get("result") if result.get("ok") else None

def keyboard():
    rows = []
    for start in range(0, len(MECHANISMS), 2):
        rows.append([{"text": MECHANISMS[i][1], "callback_data": "m:" + MECHANISMS[i][0]}
                     for i in range(start, min(start + 2, len(MECHANISMS)))])
    rows.append([{"text": "⚠ Safety checklist", "callback_data": "safety"}])
    return {"inline_keyboard": rows}

def home():
    return (
        "<b>Financial platform warning signs</b>\n\n"
        "Learn how some platforms may generate revenue and what to watch for. "
        "These patterns are warning signs, not proof that a specific business is fraudulent.\n\n"
        "Choose a mechanism to read more:"
    )

def safety():
    return (
        "<b>Before sending money</b>\n\n"
        "• Verify the firm and its permissions with your financial regulator.\n"
        "• Check whether withdrawals work without extra “unlock” or “tax” payments.\n"
        "• Treat guaranteed returns and pressure to recruit as warning signs.\n"
        "• Independently verify account statements and trade records.\n"
        "• Do not share passwords, recovery phrases, or remote access.\n\n"
        "If money is at risk, contact your bank or payment provider promptly and report it to your local regulator."
    )

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
        if key == "home":
            send(chat_id, home(), keyboard())
        elif key == "safety":
            send(chat_id, safety(), {"inline_keyboard": [[{"text": "← All mechanisms", "callback_data": "home"}]]})
        elif key.startswith("m:") and key[2:] in BY_ID:
            _, title, description = BY_ID[key[2:]]
            send(chat_id, "<b>" + title + "</b>\n\n" + description,
                 {"inline_keyboard": [[{"text": "← All mechanisms", "callback_data": "home"}],
                                      [{"text": "⚠ Safety checklist", "callback_data": "safety"}]]})
        return
    message = update.get("message") or {}
    if (message.get("chat") or {}).get("type") != "private":
        return
    text = (message.get("text") or "").strip()
    if text.startswith("/start") or text.startswith("/help") or text.startswith("/menu"):
        send(message["chat"]["id"], home(), keyboard())

def main():
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in the environment first.")
    offset = 0
    while True:
        updates = call("getUpdates", {"offset": offset, "timeout": 30,
                                     "allowed_updates": ["message", "callback_query"]})
        if updates is None:
            time.sleep(3)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                handle(update)
            except Exception:
                # Do not log payloads or request URLs, since Telegram URLs contain the token.
                continue

if __name__ == "__main__":
    main()
