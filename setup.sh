#!/usr/bin/env bash
# One-time setup for Mac or Linux: makes a private Python environment (venv) and installs what the tracker needs.
cd "$(dirname "$0")" || exit 1
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
  echo "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and run this again."
  exit 1
fi
[ -x venv/bin/python ] || { echo "Creating the environment ..."; "$PY" -m venv venv || exit 1; }
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || { echo; echo "The install failed. See the message above."; exit 1; }
echo
python check_setup.py
echo
echo "Setup finished. Run ./run.sh to start the dashboard."
