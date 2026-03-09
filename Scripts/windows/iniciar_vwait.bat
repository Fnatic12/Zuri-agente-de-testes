@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"

cd /d "%PROJECT_ROOT%"
set "STREAMLIT_SERVER_FILE_WATCHER_TYPE=none"
set "STREAMLIT_SERVER_RUN_ON_SAVE=false"

REM Se usa venv, descomente:
REM call .venv\Scripts\activate

start "VWAIT Watcher" cmd /k "py Scripts\windows\dev_streamlit_watcher.py"

timeout /t 4 /nobreak >nul
start "" http://localhost:8502
start "" http://localhost:8503

endlocal
