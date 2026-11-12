@echo off
rem Starts the dashboard. Your browser opens at http://localhost:8501. Close this window to stop it.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo Run setup.bat first.
  pause
  exit /b 1
)
call venv\Scripts\activate
python -m streamlit run dashboard/app.py
pause
