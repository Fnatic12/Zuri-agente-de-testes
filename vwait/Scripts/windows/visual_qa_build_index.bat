@echo off
setlocal

set "ROOT=%~dp0..\.."
cd /d "%ROOT%"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

%PY% -m visual_qa.interfaces.cli.build_index_cli --reference-dir reference_images --index-dir artifacts\vector_index --recursive %*

endlocal
