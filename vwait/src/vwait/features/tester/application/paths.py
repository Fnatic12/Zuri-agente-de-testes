from __future__ import annotations

import os

from app.shared.project_paths import project_root, root_path


BASE_DIR = project_root()

SCRIPTS = {
    "Coletar Teste": root_path("Scripts", "coletor_adb.py"),
    "Processar Dataset": root_path("Pre_process", "processar_dataset.py"),
    "Executar Teste": root_path("src", "vwait", "entrypoints", "cli", "run_test.py"),
    "Abrir Dashboard": root_path("src", "vwait", "entrypoints", "streamlit", "visualizador_execucao.py"),
    "Abrir Painel de Logs": root_path("src", "vwait", "entrypoints", "streamlit", "painel_logs_radio.py"),
    "Abrir Controle de Falhas": root_path("src", "vwait", "entrypoints", "streamlit", "controle_falhas.py"),
}

STOP_FLAG_PATH = os.path.join(BASE_DIR, "stop.flag")


__all__ = ["BASE_DIR", "SCRIPTS", "STOP_FLAG_PATH"]
