#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_EXE="${PROJECT_ROOT}/.venv/bin/python"
LAUNCHER_SCRIPT="${PROJECT_ROOT}/scripts/linux/start_vwait_apps.py"

cd "${PROJECT_ROOT}"
export STREAMLIT_SERVER_FILE_WATCHER_TYPE=none
export STREAMLIT_SERVER_RUN_ON_SAVE=false
export BROWSER_GATHER_USAGE_STATS=false

if [[ ! -x "${PYTHON_EXE}" ]]; then
  echo "Ambiente Python nao encontrado em ${PYTHON_EXE}."
  echo "Verifique a pasta .venv do projeto."
  exit 1
fi

exec "${PYTHON_EXE}" "${LAUNCHER_SCRIPT}"
