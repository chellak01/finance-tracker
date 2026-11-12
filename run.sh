#!/usr/bin/env bash
# Starts the dashboard. Your browser opens at http://localhost:8501. Press Ctrl+C to stop it.
cd "$(dirname "$0")" || exit 1
[ -x venv/bin/python ] || { echo "Run ./setup.sh first."; exit 1; }
source venv/bin/activate
python -m streamlit run dashboard/app.py
