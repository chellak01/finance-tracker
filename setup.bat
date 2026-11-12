@echo off
rem One-time setup for Windows: makes a private Python environment (venv) and installs what the tracker needs.
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py -3
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)
if not exist venv\Scripts\python.exe (
  echo Creating the environment ...
  %PY% -m venv venv
  if errorlevel 1 ( echo Could not create the environment. & pause & exit /b 1 )
)
call venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 ( echo. & echo The install failed. See the message above. & pause & exit /b 1 )
echo.
python check_setup.py
echo.
echo Setup finished. Double-click run.bat to start the dashboard.
pause
