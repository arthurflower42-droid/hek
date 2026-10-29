# Магнит, Telegram paper-trading demo

Magnit is a fictional Telegram bot demo. It demonstrates menus, language switching, a virtual-credit portfolio, simulated positions, and an activity history.

**No real funds are accepted or transferred.** There are no deposits, withdrawals, wallet addresses, live trades, forecasts, or promised returns. Closing a demo position applies only a selectable hypothetical -10%, 0%, or +10% scenario to virtual credits.

## What works

- `/start`, `/menu`, `/dashboard`, `/help`, `/language`
- English and Russian menus
- New users receive 10,000 virtual credits
- Open and close demo positions, view portfolio and recent activity
- SQLite persistence in `magnit-demo.sqlite3`
- Optional local health endpoint

## Run

Python 3.10+; standard library only.

Set `TELEGRAM_BOT_TOKEN` in the environment (or put a BotFather token in an untracked `config.json` beside `bot.py`), then run:
