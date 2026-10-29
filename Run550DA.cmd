@echo off
cd /d "%~dp0"
if not exist config.json (
  echo Не найден config.json - вставь токен от BotFather в поле "token".
  pause
  exit /b 1
)
python bot_550da_demo.py
pause
