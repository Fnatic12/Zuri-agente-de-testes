@echo off
setlocal

set "ROOT=%~dp0..\.."
cd /d "%ROOT%"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

%PY% src\vwait\entrypoints\cli\build_index.py --reference-dir reference_images --index-dir artifacts\vector_index --recursive %*

endlocal
