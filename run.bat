@echo off
rem One-command start (Windows): creates the Python environment on the first run, installs packages,
rem and opens the chat at http://localhost:8501. Extra arguments go to Streamlit, e.g. run.bat --server.port 8502
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Creating the Python environment, first run only...
    python -m venv .venv || goto :error
)

echo Installing packages...
.venv\Scripts\python -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto :error

echo Starting the app. Your browser will open; if not, go to http://localhost:8501
.venv\Scripts\python -m streamlit run app.py %*
goto :eof

:error
echo.
echo Setup failed. Check that Python 3.11 or newer is installed and on your PATH.
exit /b 1
