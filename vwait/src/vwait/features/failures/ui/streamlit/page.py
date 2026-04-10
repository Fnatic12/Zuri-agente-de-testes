from __future__ import annotations

import streamlit as st

from ...application import (
    LANE_NEW,
    LANE_RESOLVED,
    LANE_SENT,
    filter_failure_records,
    lane_from_record,
    list_failure_records_use_case as list_failure_records,
    sync_jira_statuses,
)
from ...integrations.jira import JiraError, JiraService
from .board_runtime import render_failure_board_runtime
from .presenters import (
    render_jira_flash_message,
    render_kpi_card,
    titulo_painel,
)
from .state import (
    FAILURE_JIRA_CONNECTION_KEY,
    FAILURE_JIRA_ISSUE_TYPES_KEY,
    set_jira_flash_message,
)


def _render_jira_connection_section() -> None:
    st.markdown("##### Jira")
    service = JiraService.from_env()
    settings = service.settings

    if not settings.is_configured:
        missing = ", ".join(settings.missing_fields)
        st.warning(f"Integracao Jira ainda nao configurada. Variaveis ausentes: {missing}")
        st.caption("Preencha `.env.jira` para habilitar teste de conexao e criacao de cards.")
        return

    col1, col2, col3 = st.columns([2.2, 1.8, 1.2])
    col1.caption(f"Workspace: {settings.base_url}")
    col2.caption(f"Projeto: {settings.project_key or '-'} | Tipo: {settings.issue_type or '-'}")
    test_clicked = col3.button("Testar conexao com Jira", key="failure_control_jira_test_connection")

    if test_clicked:
        try:
            connection = service.test_connection(project_key=settings.project_key)
            st.session_state[FAILURE_JIRA_CONNECTION_KEY] = {
                "display_name": connection.display_name,
                "email": connection.email,
                "project_key": connection.project_key,
                "project_name": connection.project_name,
            }
            st.session_state[FAILURE_JIRA_ISSUE_TYPES_KEY] = tuple(connection.issue_types)
        except JiraError as exc:
            st.session_state[FAILURE_JIRA_CONNECTION_KEY] = {"error": str(exc)}
            st.session_state.pop(FAILURE_JIRA_ISSUE_TYPES_KEY, None)

    connection_state = st.session_state.get(FAILURE_JIRA_CONNECTION_KEY)
    if isinstance(connection_state, dict) and connection_state:
        if connection_state.get("error"):
            st.error(str(connection_state["error"]))
        else:
            st.success(
                "Conexao Jira validada com "
                f"{connection_state.get('display_name') or connection_state.get('email')}"
            )
            st.caption(
                f"Projeto validado: {connection_state.get('project_key') or '-'} - "
                f"{connection_state.get('project_name') or '-'}"
            )

    issue_types = tuple(st.session_state.get(FAILURE_JIRA_ISSUE_TYPES_KEY, ()))
    if issue_types:
        st.caption("Tipos disponiveis no projeto: " + ", ".join(issue_types))
        if settings.issue_type not in issue_types:
            st.warning(
                f"O tipo configurado `{settings.issue_type}` nao apareceu entre os tipos retornados pelo Jira."
            )


def _render_summary_metrics(records: list[dict[str, object]]) -> None:
    total_mapped = len(records)
    total_new = sum(1 for item in records if lane_from_record(item) == LANE_NEW)
    total_sent = sum(1 for item in records if lane_from_record(item) == LANE_SENT)
    total_resolved = sum(1 for item in records if lane_from_record(item) == LANE_RESOLVED)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card("Falhas mapeadas", str(total_mapped))
    with c2:
        render_kpi_card("Novas", str(total_new))
    with c3:
        render_kpi_card("Enviadas", str(total_sent))
    with c4:
        render_kpi_card("Resolvidas", str(total_resolved))


def _handle_jira_sync_action(records: list[dict[str, object]]) -> None:
    if not st.button("Sincronizar status do Jira", key="failure_control_jira_sync_status"):
        return
    try:
        sync_result = sync_jira_statuses(records)
        total = int(sync_result.get("total") or 0)
        updated = int(sync_result.get("updated") or 0)
        errors = list(sync_result.get("errors") or [])
        if total == 0:
            set_jira_flash_message("Nenhuma falha visivel com issue key para sincronizar.")
        elif errors:
            set_jira_flash_message(
                (
                    f"Sincronizacao parcial: {updated}/{total} issue(s) atualizadas. "
                    f"Falhas: {' | '.join(errors[:3])}"
                ),
                level="error",
            )
        else:
            set_jira_flash_message(
                f"Sincronizacao concluida: {updated}/{total} issue(s) atualizadas.",
                level="success",
            )
        st.rerun()
    except JiraError as exc:
        st.error(str(exc))


def render_failure_control_page() -> None:
    titulo_painel("Controle de Falhas", "Quadro visual das falhas coletadas.")
    render_jira_flash_message()

    all_records = list_failure_records()
    if not all_records:
        st.info("Nenhuma falha coletada encontrada em workspace/reports/failures.")
        return

    search_text = st.text_input(
        "Buscar falha",
        placeholder="categoria, teste, resumo, issue ou responsavel",
    )
    filtered = filter_failure_records(all_records, search_text)

    _render_summary_metrics(filtered)
    _render_jira_connection_section()
    _handle_jira_sync_action(filtered)

    if not filtered:
        st.warning("Nenhuma falha atende a busca atual.")
        return

    render_failure_board_runtime(all_records=all_records, filtered_records=filtered)


__all__ = ["render_failure_control_page"]
