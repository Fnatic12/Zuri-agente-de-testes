@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"

cd /d "%PROJECT_ROOT%"
set "STREAMLIT_SERVER_FILE_WATCHER_TYPE=none"
set "STREAMLIT_SERVER_RUN_ON_SAVE=false"
set "WATCHER_SCRIPT=Scripts\windows\dev_streamlit_watcher.py"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if exist "%PROJECT_ROOT%\.env.tester" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_ROOT%\.env.tester") do (
        if /i "%%~A"=="ADB_PATH" set "ADB_PATH=%%~B"
    )
)

if not exist "%PYTHON_EXE%" (
    echo [VWAIT] Ambiente .venv nao encontrado.
    echo [VWAIT] Rode primeiro Scripts\windows\setup_vwait.bat
    pause
    goto :end
)

"%PYTHON_EXE%" -c "import streamlit, pandas, cv2, PIL, matplotlib, skimage" >nul 2>nul
if errorlevel 1 (
    echo [VWAIT] Dependencias do runtime nao encontradas na .venv.
    echo [VWAIT] Rode primeiro Scripts\windows\setup_vwait.bat
    pause
    goto :end
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Scripts\\windows\\dev_streamlit_watcher.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8502 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8503 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8504 .*LISTENING"') do taskkill /f /pid %%P >nul 2>nul

start "VWAIT Watcher" "%PYTHON_EXE%" "%WATCHER_SCRIPT%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports = 8502,8503; foreach ($port in $ports) { $ok = $false; for ($i = 0; $i -lt 60; $i++) { if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { $ok = $true; break }; Start-Sleep -Seconds 1 }; if ($ok) { Start-Process ('http://localhost:' + $port) } }"

:end
endlocal
