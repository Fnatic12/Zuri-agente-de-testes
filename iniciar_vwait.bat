@echo off
setlocal

cd /d C:\Users\Automation01\Desktop\zuri_agente

REM Se usa venv, descomente:
REM call .venv\Scripts\activate

start "Menu Chat" cmd /k "py -m streamlit run menu_chat.py --server.port 8502"
start "Menu Tester" cmd /k "py -m streamlit run menu_tester.py --server.port 8503"

timeout /t 3 /nobreak >nul
start "" http://localhost:8502
start "" http://localhost:8503

endlocal
