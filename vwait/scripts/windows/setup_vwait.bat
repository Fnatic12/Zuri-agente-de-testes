@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

set "REQ_FILE=requirements\tester_runtime.txt"
set "VENV_DIR=%PROJECT_ROOT%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "ADB_LOCAL_DIR=%PROJECT_ROOT%\tools\platform-tools"
set "ADB_LOCAL_EXE=%ADB_LOCAL_DIR%\adb.exe"

echo [VWAIT] Projeto: %PROJECT_ROOT%
echo [VWAIT] Preparando ambiente para tester...

call :resolve_python
if errorlevel 1 goto :fail

if not exist "%REQ_FILE%" (
    echo [VWAIT] Arquivo de dependencias nao encontrado: %REQ_FILE%
    goto :fail
)

if exist "%VENV_PY%" (
    call :venv_python_ok
    if errorlevel 1 (
        echo [VWAIT] .venv encontrada, mas o Python dela esta invalido ou orfao.
        echo [VWAIT] Removendo .venv para recriar com um Python valido...
        rmdir /s /q "%VENV_DIR%" >nul 2>nul
        if exist "%VENV_DIR%" (
            echo [VWAIT] Nao foi possivel remover a .venv antiga.
            echo [VWAIT] Feche terminais, editores ou processos que possam estar usando o ambiente.
            goto :fail
        )
    ) else (
        echo [VWAIT] .venv ja existe e esta valida.
    )
)

if not exist "%VENV_PY%" (
    echo [VWAIT] Criando ambiente virtual em .venv...
    if /i "%PYTHON_KIND%"=="launcher" (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        "%PYTHON_EXE%" -m venv "%VENV_DIR%"
    )
    if errorlevel 1 (
        echo [VWAIT] Falha ao criar .venv.
        goto :fail
    )
)

echo [VWAIT] Atualizando pip...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail

echo [VWAIT] Instalando dependencias do runtime...
"%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 goto :fail

echo [VWAIT] Validando imports principais...
"%VENV_PY%" -c "import streamlit, pandas, cv2, PIL, matplotlib, skimage, speech_recognition, seaborn, requests, colorama, termcolor, pyfiglet; print('runtime-ok')"
if errorlevel 1 goto :fail

call :ensure_adb
if errorlevel 1 goto :fail

call :write_env_file
if errorlevel 1 goto :fail

echo [VWAIT] Setup concluido.
echo [VWAIT] Proximo passo: execute scripts\windows\iniciar_vwait.bat
goto :end

:resolve_python
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; print(sys.executable)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_KIND=launcher"
        exit /b 0
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%I in ('where python') do (
        "%%~fI" -c "import sys; print(sys.executable)" >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_KIND=path"
            set "PYTHON_EXE=%%~fI"
            exit /b 0
        )
    )
)

echo [VWAIT] Python 3 nao encontrado ou esta quebrado neste Windows.
echo [VWAIT] Instale ou repare o Python 3.11+ e marque a opcao Add Python to PATH.
exit /b 1

:venv_python_ok
if not exist "%VENV_PY%" exit /b 1
"%VENV_PY%" -c "import sys; print(sys.executable)" >nul 2>nul
exit /b %ERRORLEVEL%

:ensure_adb
if defined ADB_PATH if exist "%ADB_PATH%" (
    echo [VWAIT] Usando ADB definido em ADB_PATH=%ADB_PATH%
    exit /b 0
)

where adb >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%I in ('where adb') do (
        set "ADB_FOUND=%%~fI"
        goto :adb_found
    )
)

if exist "%ADB_LOCAL_EXE%" (
    set "ADB_FOUND=%ADB_LOCAL_EXE%"
    goto :adb_found
)

echo [VWAIT] ADB nao encontrado no PATH nem em %ADB_LOCAL_EXE%
echo [VWAIT] Instale o Android platform-tools e copie o conteudo para:
echo [VWAIT]   %ADB_LOCAL_DIR%
echo [VWAIT] Ou defina a variavel de ambiente ADB_PATH apontando para adb.exe.
exit /b 1

:adb_found
echo [VWAIT] ADB detectado em: %ADB_FOUND%
exit /b 0

:write_env_file
if not defined ADB_FOUND (
    if defined ADB_PATH (
        set "ADB_FOUND=%ADB_PATH%"
    ) else (
        exit /b 0
    )
)

>"%PROJECT_ROOT%\.env.tester" echo ADB_PATH=%ADB_FOUND%
echo [VWAIT] Arquivo .env.tester atualizado.
exit /b 0

:fail
echo [VWAIT] Setup nao concluido.
pause
exit /b 1

:end
endlocal
