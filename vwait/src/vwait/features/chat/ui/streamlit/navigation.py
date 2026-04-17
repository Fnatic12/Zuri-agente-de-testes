from __future__ import annotations

import streamlit as st

from vwait.core.paths import project_root, root_path


PAGINA_CHAT = "Chat"
PAGINA_DASHBOARD = "Resultados dos Testes"
PAGINA_LOGS_RADIO = "Painel de Logs"
PAGINA_CONTROLE_FALHAS = "Controle de Falhas"
PAGINA_MENU_TESTER = "Menu Tester"
PAGINA_VALIDACAO_HMI = "HMI"
PAGINA_MAPA_NEURAL_IA = "Arquitetura"
NAV_RADIO_KEY = "pagina_navegacao"
NAV_PENDING_KEY = "pagina_navegacao_pendente"
DASHBOARD_PORT = 8504
LOGS_PANEL_PORT = 8505
FAILURE_CONTROL_PORT = 8506
MENU_TESTER_PORT = 8503


def init_navigation_state() -> None:
    if NAV_RADIO_KEY not in st.session_state:
        st.session_state[NAV_RADIO_KEY] = PAGINA_CHAT
    if NAV_PENDING_KEY not in st.session_state:
        st.session_state[NAV_PENDING_KEY] = None


def select_page(nome_pagina: str) -> None:
    st.session_state[NAV_PENDING_KEY] = nome_pagina


def apply_pending_navigation() -> None:
    pagina_pendente = st.session_state.get(NAV_PENDING_KEY)
    if pagina_pendente:
        st.session_state[NAV_RADIO_KEY] = pagina_pendente
        st.session_state[NAV_PENDING_KEY] = None


def sidebar_page_selector():
    st.sidebar.title("Menu")
    return st.sidebar.radio(
        "",
        [
            PAGINA_CHAT,
            PAGINA_MAPA_NEURAL_IA,
            PAGINA_DASHBOARD,
            PAGINA_LOGS_RADIO,
            PAGINA_CONTROLE_FALHAS,
            PAGINA_MENU_TESTER,
            PAGINA_VALIDACAO_HMI,
        ],
        key=NAV_RADIO_KEY,
    )


def render_selected_page(
    pagina: str,
    *,
    render_mapa_neural_ia_coder,
    apply_panel_button_theme,
    abrir_menu_tester,
) -> None:
    from vwait.features.execution.ui.streamlit import render_dashboard_page
    from vwait.features.failures.ui.streamlit import render_failure_control_page
    from vwait.features.hmi.ui.streamlit import render_hmi_validation_page
    from vwait.features.logs.ui.streamlit import render_logs_panel_page
    from vwait.features.tester.ui.streamlit import render_tester_page

    project_root_path = project_root()
    data_root = root_path("Data")

    if pagina == PAGINA_DASHBOARD:
        apply_panel_button_theme()
        render_dashboard_page()
        return
    if pagina == PAGINA_MAPA_NEURAL_IA:
        render_mapa_neural_ia_coder()
        return
    if pagina == PAGINA_LOGS_RADIO:
        apply_panel_button_theme()
        render_logs_panel_page()
        return
    if pagina == PAGINA_CONTROLE_FALHAS:
        apply_panel_button_theme()
        render_failure_control_page()
        return
    if pagina == PAGINA_MENU_TESTER:
        apply_panel_button_theme()
        render_tester_page(embedded=True)
        return
    if pagina == PAGINA_VALIDACAO_HMI:
        render_hmi_validation_page(str(project_root_path), data_root)
        return
    st.error(f"Pagina desconhecida: {pagina}")


__all__ = [
    "DASHBOARD_PORT",
    "FAILURE_CONTROL_PORT",
    "LOGS_PANEL_PORT",
    "MENU_TESTER_PORT",
    "NAV_PENDING_KEY",
    "NAV_RADIO_KEY",
    "PAGINA_CHAT",
    "PAGINA_CONTROLE_FALHAS",
    "PAGINA_DASHBOARD",
    "PAGINA_LOGS_RADIO",
    "PAGINA_MAPA_NEURAL_IA",
    "PAGINA_MENU_TESTER",
    "PAGINA_VALIDACAO_HMI",
    "apply_pending_navigation",
    "init_navigation_state",
    "render_selected_page",
    "select_page",
    "sidebar_page_selector",
]
