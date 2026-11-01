@echo off
echo Setting up DataGuard...
python -m venv .venv
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from python.org and try again.
  pause
  exit /b 1
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Setup finished. Double-click run.bat to start DataGuard.
pause
