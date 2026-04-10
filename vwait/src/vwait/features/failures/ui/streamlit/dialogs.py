from __future__ import annotations

import os
from typing import Any

import streamlit as st

from ...application import (
    create_jira_issue_for_record,
    lane_from_record as lane_from_failure_record,
    update_failure_control,
)
from ...domain.enums import JIRA_SYNC_STATUS_OPTIONS, PRIORITY_OPTIONS, WORKFLOW_STATUS_OPTIONS
from ...integrations.jira import JiraError, JiraService
from ...integrations.jira.failure_issues import (
    build_failure_issue_description,
    build_failure_issue_labels,
    build_failure_issue_summary,
    collect_failure_issue_attachments,
)
from .state import (
    FAILURE_CLAIM_NAME_INPUT_KEY,
    FAILURE_CLAIM_RECORD_ID_KEY,
    FAILURE_JIRA_ISSUE_TYPES_KEY,
    FAILURE_MODAL_RECORD_ID_KEY,
    set_jira_flash_message,
)


def default_claim_name() -> str:
    return (
        os.environ.get("VWAIT_FAILURE_OPERATOR")
        or os.environ.get("USERNAME")
        or os.environ.get("USER")
        or ""
    ).strip()


def _failure_jira_state_key(record: dict[str, Any], name: str) -> str:
    return f"failure_jira::{record['record_id']}::{name}"


def _failure_jira_attachment_key(record: dict[str, Any], path: str) -> str:
    return _failure_jira_state_key(record, f"attachment::{path}")


def _split_csv_values(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _ensure_failure_jira_defaults(record: dict[str, Any]) -> list[dict[str, str]]:
    attachments = collect_failure_issue_attachments(record)
    summary_key = _failure_jira_state_key(record, "summary")
    labels_key = _failure_jira_state_key(record, "labels")
    description_key = _failure_jira_state_key(record, "description")

    if summary_key not in st.session_state:
        st.session_state[summary_key] = build_failure_issue_summary(record)
    if labels_key not in st.session_state:
        st.session_state[labels_key] = ", ".join(build_failure_issue_labels(record))
    if description_key not in st.session_state:
        st.session_state[description_key] = build_failure_issue_description(record)

    for attachment in attachments:
        key = _failure_jira_attachment_key(record, attachment["path"])
        if key not in st.session_state:
            st.session_state[key] = True
    return attachments


@st.dialog("Editar falha", width="large")
def render_failure_edit_dialog(record: dict[str, Any]) -> None:
    report = record.get("report") or {}
    radio_log = report.get("radio_log") or {}
    service = JiraService.from_env()
    jira_settings = service.settings
    available_issue_types = tuple(st.session_state.get(FAILURE_JIRA_ISSUE_TYPES_KEY, ()))
    jira_attachments = _ensure_failure_jira_defaults(record) if jira_settings.is_configured else []

    st.error(record.get("short_text") or "Falha sem resumo.")

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Categoria", record.get("category") or "-")
    top2.metric("Teste", record.get("test_name") or "-")
    top3.metric("Status atual", lane_from_failure_record(record))
    top4.metric("Issue", record.get("jira_issue_key") or "-")

    with st.form(f"failure_control_modal_{record['record_id']}"):
        col1, col2, col3 = st.columns(3)
        workflow_status = col1.selectbox(
            "Workflow",
            options=list(WORKFLOW_STATUS_OPTIONS),
            index=list(WORKFLOW_STATUS_OPTIONS).index(record.get("workflow_status") or "novo"),
        )
        jira_sync_status = col2.selectbox(
            "Status Jira",
            options=list(JIRA_SYNC_STATUS_OPTIONS),
            index=list(JIRA_SYNC_STATUS_OPTIONS).index(record.get("jira_sync_status") or "nao_enviado"),
        )
        priority = col3.selectbox(
            "Prioridade",
            options=list(PRIORITY_OPTIONS),
            index=list(PRIORITY_OPTIONS).index(record.get("priority") or "media"),
        )

        col4, col5, col6 = st.columns(3)
        jira_issue_key = col4.text_input("Issue key", value=record.get("jira_issue_key") or "")
        jira_issue_status = col5.text_input("Issue status", value=record.get("jira_issue_status") or "")
        assignee = col6.text_input("Responsavel", value=record.get("assignee") or "")

        jira_issue_url = st.text_input("URL do issue", value=record.get("jira_issue_url") or "")
        root_cause = st.text_area("Causa raiz", value=record.get("root_cause") or "", height=90)
        notes = st.text_area("Notas", value=record.get("notes") or "", height=130)

        summary_key = _failure_jira_state_key(record, "summary")
        labels_key = _failure_jira_state_key(record, "labels")
        description_key = _failure_jira_state_key(record, "description")

        if jira_settings.is_configured:
            st.markdown("#### Jira")
            st.caption(
                f"Workspace: {jira_settings.base_url} | "
                f"Projeto: {jira_settings.project_key or '-'} | "
                f"Tipo configurado: {jira_settings.issue_type or '-'}"
            )
            if available_issue_types:
                st.caption("Tipos retornados pelo Jira: " + ", ".join(available_issue_types))
                if jira_settings.issue_type not in available_issue_types:
                    st.warning(
                        f"O tipo configurado `{jira_settings.issue_type}` nao apareceu na ultima validacao."
                    )
            if record.get("jira_issue_key"):
                st.info(f"Falha atualmente vinculada a {record.get('jira_issue_key')}.")

            st.text_input("Resumo do card Jira", key=summary_key)
            st.text_input("Labels do Jira", key=labels_key)
            st.text_area("Descricao do card Jira", key=description_key, height=220)

            if jira_attachments:
                st.caption("Anexos opcionais")
                attach_cols = st.columns(2)
                for idx, attachment in enumerate(jira_attachments):
                    attach_key = _failure_jira_attachment_key(record, attachment["path"])
                    attach_cols[idx % 2].checkbox(
                        f"{attachment['label']} ({os.path.basename(attachment['path'])})",
                        key=attach_key,
                    )
            else:
                st.caption("Nenhum anexo local encontrado para envio automatico.")
        else:
            st.warning("Integracao Jira nao configurada. Preencha `.env.jira` para habilitar a criacao de cards.")

        if jira_settings.is_configured:
            action1, action2, action3, action4 = st.columns(4)
            save = action1.form_submit_button("Salvar")
            refresh_jira = action2.form_submit_button("Atualizar desc Jira")
            create_jira = action3.form_submit_button(
                "Criar outro card no Jira" if record.get("jira_issue_key") else "Criar card no Jira"
            )
            close = action4.form_submit_button("Fechar")
        else:
            action1, action2 = st.columns(2)
            save = action1.form_submit_button("Salvar")
            refresh_jira = False
            create_jira = False
            close = action2.form_submit_button("Fechar")

        if refresh_jira:
            st.session_state[description_key] = build_failure_issue_description(
                record,
                root_cause=root_cause,
                notes=notes,
            )
            st.rerun()

        if create_jira:
            attachment_paths = [
                attachment["path"]
                for attachment in jira_attachments
                if st.session_state.get(_failure_jira_attachment_key(record, attachment["path"]), False)
            ]
            try:
                result = create_jira_issue_for_record(
                    record,
                    summary=str(st.session_state.get(summary_key, "") or ""),
                    description=str(st.session_state.get(description_key, "") or ""),
                    labels=_split_csv_values(str(st.session_state.get(labels_key, "") or "")),
                    attachment_paths=attachment_paths,
                    priority=priority,
                    assignee=assignee,
                    root_cause=root_cause,
                    notes=notes,
                    jira_issue_status=jira_issue_status,
                    service=service,
                )
                set_jira_flash_message(
                    f"Issue criada com sucesso: {result.issue_key}",
                    level="success",
                    issue_url=result.issue_url,
                )
                st.rerun()
            except JiraError as exc:
                st.error(str(exc))

        if save:
            update_failure_control(
                record["report_dir"],
                report,
                {
                    "workflow_status": workflow_status,
                    "jira_sync_status": jira_sync_status,
                    "priority": priority,
                    "jira_issue_key": jira_issue_key,
                    "jira_issue_status": jira_issue_status,
                    "jira_issue_url": jira_issue_url,
                    "assignee": assignee,
                    "root_cause": root_cause,
                    "notes": notes,
                },
            )
            st.session_state.pop(FAILURE_MODAL_RECORD_ID_KEY, None)
            st.success("Falha atualizada.")
            st.rerun()
        if close:
            st.session_state.pop(FAILURE_MODAL_RECORD_ID_KEY, None)
            st.rerun()

    with st.expander("Resumo tecnico da falha", expanded=False):
        st.write(report.get("precondition") or "-")
        st.write(report.get("test_result") or "-")
        st.write(report.get("expected_result") or "-")
        st.write(report.get("actual_results") or "-")
        if radio_log.get("summary"):
            st.write(radio_log.get("summary"))


@st.dialog("Assinar falha", width="small")
def render_claim_dialog(record: dict[str, Any]) -> None:
    st.write("Digite seu nome para assinar.")

    with st.form(f"failure_claim_form_{record['record_id']}"):
        assignee_name = st.text_input(
            "Nome",
            key=FAILURE_CLAIM_NAME_INPUT_KEY,
            placeholder="seu nome",
        )

        action1, action2 = st.columns(2)
        sign = action1.form_submit_button("Assinar")
        cancel = action2.form_submit_button("Cancelar")

        if sign:
            assignee_value = assignee_name.strip()
            if not assignee_value:
                st.warning("Informe um nome para assinar a falha.")
            else:
                update_failure_control(
                    record["report_dir"],
                    record["report"],
                    {"assignee": assignee_value},
                )
                st.session_state.pop(FAILURE_CLAIM_RECORD_ID_KEY, None)
                st.session_state.pop(FAILURE_CLAIM_NAME_INPUT_KEY, None)
                st.success("Falha assinada.")
                st.rerun()

        if cancel:
            st.session_state.pop(FAILURE_CLAIM_RECORD_ID_KEY, None)
            st.session_state.pop(FAILURE_CLAIM_NAME_INPUT_KEY, None)
            st.rerun()


__all__ = [
    "default_claim_name",
    "render_claim_dialog",
    "render_failure_edit_dialog",
]
