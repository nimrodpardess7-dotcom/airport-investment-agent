#!/usr/bin/env sh
# One-command start (Mac/Linux): creates the Python environment on the first run, installs packages,
# and opens the chat at http://localhost:8501. Extra arguments go to Streamlit, e.g. ./run.sh --server.port 8502
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "Creating the Python environment, first run only..."
    python3 -m venv .venv || { echo "Setup failed. Check that Python 3.11 or newer is installed."; exit 1; }
fi

echo "Installing packages..."
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

echo "Starting the app. Your browser will open; if not, go to http://localhost:8501"
exec .venv/bin/python -m streamlit run app.py "$@"
