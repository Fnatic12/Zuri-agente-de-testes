from __future__ import annotations

import streamlit as st


def initialize_session_state() -> None:
    defaults = {
        "proc_coleta": None,
        "coleta_log_path": None,
        "coleta_log_file": None,
        "coleta_expected_pending": None,
        "coleta_training_payload": None,
        "proc_execucao_unica": None,
        "execucao_unica_status": "",
        "execucao_log_path": None,
        "execucao_unica_processos": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


__all__ = ["initialize_session_state"]
