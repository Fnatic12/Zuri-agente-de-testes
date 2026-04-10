@echo off
setlocal

set "ROOT=%~dp0..\.."
cd /d "%ROOT%"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

if "%~1"=="" (
  echo Usage: %~n0 path\to\screenshot.png [extra args]
  exit /b 1
)

set "IMG=%~1"
shift

%PY% -m visual_qa.interfaces.cli.classify_cli --image "%IMG%" --index-dir artifacts\vector_index --top-k 5 --threshold 0.35 --strategy best %*

endlocal
