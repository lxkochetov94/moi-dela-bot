@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set BOT_TIMEZONE=Europe/Moscow
if not exist ".venv\Scripts\python.exe" (
  echo Настраиваю локальную версию бота...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Нужен Python 3.11 или новее: https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r local_requirements.txt
if errorlevel 1 (
  echo Не удалось установить openpyxl. Проверь интернет.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" local_run.py
echo.
echo Окно закрывать можно. Данные на компьютере сохранены.
pause
