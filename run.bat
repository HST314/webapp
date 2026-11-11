@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv || goto :error
)

call ".venv\Scripts\activate.bat"

echo [2/3] Installing dependencies...
python -m pip install -q -r requirements.txt || goto :error

echo [3/3] Starting server...
python run.py
if errorlevel 1 goto :error
goto :eof

:error
echo.
echo Startup failed. See the messages above.
pause
