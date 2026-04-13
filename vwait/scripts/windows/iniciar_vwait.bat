@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"

cd /d "%PROJECT_ROOT%"
set "STREAMLIT_SERVER_FILE_WATCHER_TYPE=none"
set "STREAMLIT_SERVER_RUN_ON_SAVE=false"
set "LAUNCHER_SCRIPT=scripts\windows\start_vwait_apps.py"
set "SETUP_SCRIPT=scripts\windows\setup_vwait.bat"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "PYTHONW_EXE=%PROJECT_ROOT%\.venv\Scripts\pythonw.exe"
set "EXIT_CODE=0"

if exist "%PROJECT_ROOT%\.env.tester" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_ROOT%\.env.tester") do (
        if /i "%%~A"=="ADB_PATH" set "ADB_PATH=%%~B"
    )
)

if not exist "%PYTHON_EXE%" (
    echo [VWAIT] Ambiente .venv nao encontrado.
    echo [VWAIT] Tentando preparar o ambiente automaticamente...
    call "%PROJECT_ROOT%\%SETUP_SCRIPT%"
    if errorlevel 1 (
        set "EXIT_CODE=1"
        goto :end
    )
)

call :runtime_ready
if errorlevel 1 (
    echo [VWAIT] A .venv existe, mas esta incompleta, invalida ou ficou orfa.
    echo [VWAIT] Tentando reparar automaticamente o ambiente...
    call "%PROJECT_ROOT%\%SETUP_SCRIPT%"
    if errorlevel 1 (
        set "EXIT_CODE=1"
        goto :end
    )
    call :runtime_ready
    if errorlevel 1 (
        echo [VWAIT] O ambiente Python ainda nao ficou funcional apos o reparo.
        echo [VWAIT] Verifique a instalacao do Python 3 no Windows e rode scripts\windows\setup_vwait.bat manualmente.
        pause
        set "EXIT_CODE=1"
        goto :end
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*scripts\\windows\\dev_streamlit_watcher.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul
if exist "%PROJECT_ROOT%\.streamlit\dev_streamlit_watcher.lock" del /f /q "%PROJECT_ROOT%\.streamlit\dev_streamlit_watcher.lock" >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8502 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8503 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8504 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8505 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8506 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul

if exist "%PYTHONW_EXE%" (
    start "" "%PYTHONW_EXE%" "%LAUNCHER_SCRIPT%"
) else (
    start "VWAIT" "%PYTHON_EXE%" "%LAUNCHER_SCRIPT%"
)

:end
endlocal & exit /b %EXIT_CODE%

:runtime_ready
if not exist "%PYTHON_EXE%" exit /b 1
"%PYTHON_EXE%" -c "import sys; import streamlit, pandas, cv2, PIL, matplotlib, skimage" >nul 2>nul
exit /b %ERRORLEVEL%
