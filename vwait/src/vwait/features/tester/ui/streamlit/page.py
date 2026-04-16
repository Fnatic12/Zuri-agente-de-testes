from __future__ import annotations

import streamlit as st

from vwait.features.tester.ui.streamlit.context import build_tester_context
from vwait.features.tester.ui.streamlit.sections import (
    render_collection_section,
    render_management_and_execution_sections,
    render_reports_and_links_section,
)
from vwait.features.tester.ui.streamlit.state import initialize_session_state
from vwait.features.tester.ui.streamlit.theme import (
    apply_dark_background,
    apply_menu_tester_styles,
    apply_panel_button_theme,
    titulo_painel,
)


def render_tester_page(*, embedded: bool = False) -> None:
    initialize_session_state()

    if not embedded:
        st.set_page_config(page_title="Menu Tester", page_icon="", layout="centered")
    apply_dark_background(hide_header=True)
    apply_panel_button_theme()
    apply_menu_tester_styles()
    titulo_painel("Painel de Automação de Testes", "Plataforma <b>para</b> Coletar e Processar Testes")
    st.divider()

    context = build_tester_context()
    bancadas = context["listar_bancadas"]()

    coleta_context = render_collection_section(
        base_dir=context["base_dir"],
        stop_flag_path=context["stop_flag_path"],
        scripts=context["scripts"],
        bancadas=bancadas,
        clean_display_text=context["clean_display_text"],
        salvar_resultado_parcial=context["salvar_resultado_parcial"],
        abrir_scrcpy_persistente=context["abrir_scrcpy_persistente"],
        criar_training_episode_draft=context["criar_training_episode_draft"],
        exportar_training_episode=context["exportar_training_episode"],
        resolver_teste_por_serial=context["resolver_teste_por_serial"],
        capturar_logs_radio=context["capturar_logs_radio"],
        resolver_pasta_logs_teste=context["resolver_pasta_logs_teste"],
        abrir_pasta_local=context["abrir_pasta_local"],
    )
    render_management_and_execution_sections(
        base_dir=context["base_dir"],
        scripts=context["scripts"],
        bancadas=bancadas,
        serial_sel=coleta_context["serial_sel"],
        carregar_status_execucao=context["carregar_status_execucao"],
        formatar_resumo_execucao=context["formatar_resumo_execucao"],
        iniciar_execucoes_teste_unico=context["iniciar_execucoes_teste_unico"],
        iniciar_execucoes_configuradas=context["iniciar_execucoes_configuradas"],
        clean_display_text=context["clean_display_text"],
        garantir_painel_streamlit=context["garantir_painel_streamlit"],
    )
    render_reports_and_links_section(
        base_dir=context["base_dir"],
        scripts=context["scripts"],
        garantir_painel_streamlit=context["garantir_painel_streamlit"],
    )


def main() -> None:
    render_tester_page(embedded=False)


if __name__ == "__main__":
    main()
