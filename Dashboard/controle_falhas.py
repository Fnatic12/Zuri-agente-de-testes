from __future__ import annotations

import os
from typing import Any

import streamlit as st

from KPM.failure_control import (
    JIRA_SYNC_STATUS_OPTIONS,
    PRIORITY_OPTIONS,
    WORKFLOW_STATUS_OPTIONS,
    list_failure_records,
    update_failure_control,
)
from app.shared import ui_theme as _ui_theme
from app.shared.failure_board_component import render_failure_board


LANE_NEW = "Novas"
LANE_SENT = "Enviadas"
LANE_RESOLVED = "Resolvidas"
LANES = (LANE_NEW, LANE_SENT, LANE_RESOLVED)


def apply_panel_button_theme() -> None:
    handler = getattr(_ui_theme, "apply_panel_button_theme", None)
    if callable(handler):
        handler()


def titulo_painel(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            color-scheme: dark;
            --motion-quick: 170ms;
            --motion-smooth: 240ms;
            --motion-curve: cubic-bezier(0.22, 1, 0.36, 1);
        }}
        @keyframes panel-fade-slide {{
            from {{
                opacity: 0;
                transform: translate3d(0, 10px, 0);
            }}
            to {{
                opacity: 1;
                transform: translate3d(0, 0, 0);
            }}
        }}
        @keyframes modal-overlay-in {{
            from {{
                opacity: 0;
                backdrop-filter: blur(0);
                -webkit-backdrop-filter: blur(0);
            }}
            to {{
                opacity: 1;
                backdrop-filter: blur(6px);
                -webkit-backdrop-filter: blur(6px);
            }}
        }}
        @keyframes modal-surface-in {{
            from {{
                opacity: 0;
                transform: translate3d(0, 14px, 0) scale(0.985);
            }}
            to {{
                opacity: 1;
                transform: translate3d(0, 0, 0) scale(1);
            }}
        }}
        html, body, [class*="css"]  {{
            background: #0B0C10 !important;
            color: #E0E0E0 !important;
        }}
        .stApp {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
            color: #e5e7eb !important;
        }}
        [data-testid="stAppViewContainer"] {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
        }}
        [data-testid="stHeader"] {{
            display: none !important;
            height: 0 !important;
        }}
        [data-testid="stToolbar"] {{
            display: none !important;
        }}
        .main .block-container, .block-container {{
            background: transparent !important;
        }}
        .block-container {{
            padding-top: 1.1rem;
            max-width: 1320px;
            animation: panel-fade-slide 260ms var(--motion-curve) both;
        }}
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, rgba(12, 18, 31, 0.92), rgba(8, 12, 22, 0.94)) !important;
            border-right: 1px solid rgba(96, 165, 250, 0.12) !important;
            box-shadow: 18px 0 36px rgba(2, 6, 23, 0.22) !important;
            backdrop-filter: blur(10px) saturate(124%);
            -webkit-backdrop-filter: blur(10px) saturate(124%);
            transition:
                transform var(--motion-smooth) var(--motion-curve),
                opacity var(--motion-smooth) ease,
                box-shadow var(--motion-smooth) ease,
                border-color var(--motion-smooth) ease;
        }}
        .main-title {{
            font-size: 2.05rem;
            line-height: 1.18;
            text-align: center;
            background: linear-gradient(90deg, #22d3ee 0%, #8b5cf6 48%, #d946ef 76%, #fb7185 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.4px;
            margin-top: 0.15em;
            margin-bottom: 0.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #b4c0d2;
            font-size: 0.95rem;
            margin-bottom: 1.1em;
        }}
        .clean-card {{
            position: relative;
            overflow: hidden;
            background: linear-gradient(180deg, rgba(17, 25, 40, 0.78), rgba(10, 16, 28, 0.74));
            border: 1px solid rgba(94, 115, 140, 0.34);
            border-radius: 18px;
            padding: 0.88rem 0.96rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 18px 32px rgba(2, 6, 23, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(18px) saturate(150%);
            -webkit-backdrop-filter: blur(18px) saturate(150%);
            transition:
                transform var(--motion-smooth) var(--motion-curve),
                box-shadow var(--motion-smooth) ease,
                border-color var(--motion-smooth) ease,
                background var(--motion-quick) ease;
            will-change: transform, box-shadow;
        }}
        .clean-card::before {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0));
            pointer-events: none;
        }}
        .clean-card:hover {{
            transform: translate3d(0, -2px, 0);
            border-color: rgba(125, 211, 252, 0.24);
            box-shadow: 0 24px 38px rgba(2, 6, 23, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.04);
        }}
        .card-kpi-label {{
            color: #9fb0c7;
            font-size: 0.78rem;
            margin-bottom: 0.15rem;
        }}
        .card-kpi-value {{
            color: #f8fbff;
            font-weight: 700;
            font-size: 1.34rem;
            line-height: 1.1;
        }}
        [data-testid="stTextInputRootElement"] > div,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea {{
            background: rgba(18, 26, 40, 0.78) !important;
            border: 1px solid rgba(94, 115, 140, 0.34) !important;
            border-radius: 16px !important;
            box-shadow: 0 12px 28px rgba(2, 6, 23, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.03) !important;
            backdrop-filter: blur(18px) saturate(140%);
            -webkit-backdrop-filter: blur(18px) saturate(140%);
            transition:
                transform var(--motion-quick) var(--motion-curve),
                border-color var(--motion-quick) ease,
                box-shadow var(--motion-quick) ease,
                background var(--motion-quick) ease;
        }}
        [data-testid="stTextInputRootElement"] > div:hover,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover,
        [data-testid="stTextArea"] textarea:hover {{
            transform: translate3d(0, -1px, 0);
            border-color: rgba(118, 151, 194, 0.42) !important;
        }}
        [data-testid="stTextInputRootElement"] > div:focus-within,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within,
        [data-testid="stTextArea"] textarea:focus {{
            border-color: rgba(96, 165, 250, 0.44) !important;
            box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.14), 0 18px 34px rgba(2, 6, 23, 0.22) !important;
            transform: translate3d(0, -1px, 0);
        }}
        [data-testid="stTextInputRootElement"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] * {{
            color: #e8edf6 !important;
        }}
        div[data-baseweb="popover"] > div {{
            border-radius: 18px !important;
            border: 1px solid rgba(96, 165, 250, 0.14) !important;
            box-shadow: 0 24px 42px rgba(2, 6, 23, 0.28) !important;
            backdrop-filter: blur(16px) saturate(136%);
            -webkit-backdrop-filter: blur(16px) saturate(136%);
            animation: panel-fade-slide 180ms var(--motion-curve) both;
        }}
        [data-testid="stDialog"] {{
            background: rgba(5, 9, 18, 0.18) !important;
            backdrop-filter: blur(6px) saturate(118%);
            -webkit-backdrop-filter: blur(6px) saturate(118%);
            animation: modal-overlay-in 180ms ease-out both;
        }}
        [data-testid="stDialog"] > div {{
            background: linear-gradient(180deg, rgba(14, 20, 34, 0.96), rgba(9, 14, 25, 0.94)) !important;
            border: 1px solid rgba(96, 165, 250, 0.16) !important;
            border-radius: 24px !important;
            box-shadow: 0 36px 80px rgba(2, 6, 23, 0.46) !important;
            backdrop-filter: blur(24px) saturate(140%);
            -webkit-backdrop-filter: blur(24px) saturate(140%);
            animation: modal-surface-in 240ms var(--motion-curve) both;
            transform-origin: top center;
        }}
        [data-testid="stDialog"] [data-testid="stVerticalBlock"] {{
            gap: 0.65rem;
        }}
        [data-testid="stForm"] button[kind="secondary"],
        [data-testid="stForm"] button[kind="primary"] {{
            border-radius: 14px !important;
            transition: transform 180ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 180ms ease, filter 180ms ease !important;
            will-change: transform, box-shadow;
        }}
        [data-testid="stForm"] button[kind="secondary"]:hover,
        [data-testid="stForm"] button[kind="primary"]:hover {{
            transform: translate3d(0, -1px, 0);
            box-shadow: 0 14px 24px rgba(2, 6, 23, 0.24) !important;
            filter: saturate(112%);
        }}
        [data-testid="stForm"] button[kind="secondary"]:active,
        [data-testid="stForm"] button[kind="primary"]:active {{
            transform: translate3d(0, 0, 0);
        }}
        @media (prefers-reduced-motion: reduce) {{
            *,
            *::before,
            *::after {{
                animation-duration: 1ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 1ms !important;
                scroll-behavior: auto !important;
            }}
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True,
    )


def _kpi_card(label: str, value: str) -> None:
    st.markdown(
        (
            "<div class='clean-card'>"
            f"<div class='card-kpi-label'>{label}</div>"
            f"<div class='card-kpi-value'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _lane_from_record(record: dict[str, Any]) -> str:
    workflow = str(record.get("workflow_status") or "").strip().lower()
    jira_sync = str(record.get("jira_sync_status") or "").strip().lower()
    if workflow in {"resolvido", "descartado"}:
        return LANE_RESOLVED
    if workflow == "enviado_para_jira" or jira_sync == "enviado":
        return LANE_SENT
    return LANE_NEW


def _updates_for_lane(lane: str) -> dict[str, str]:
    if lane == LANE_SENT:
        return {"workflow_status": "enviado_para_jira", "jira_sync_status": "enviado"}
    if lane == LANE_RESOLVED:
        return {"workflow_status": "resolvido"}
    return {"workflow_status": "novo", "jira_sync_status": "nao_enviado"}


def _compact_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    text = text.replace("T", " ")
    if "." in text:
        text = text.split(".", 1)[0]
    return text[:19]


def _truncate(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _default_claim_name() -> str:
    return (
        os.environ.get("VWAIT_FAILURE_OPERATOR")
        or os.environ.get("USERNAME")
        or os.environ.get("USER")
        or ""
    ).strip()


def _initials(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "+"
    parts = [part for part in text.replace("_", " ").replace("-", " ").split() if part]
    if not parts:
        return text[:2].upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _filter_records(records: list[dict[str, Any]], search_text: str) -> list[dict[str, Any]]:
    search_norm = search_text.strip().lower()
    if not search_norm:
        return records

    filtered: list[dict[str, Any]] = []
    for record in records:
        haystack = " ".join(
            [
                str(record.get("category") or ""),
                str(record.get("test_name") or ""),
                str(record.get("short_text") or ""),
                str(record.get("jira_issue_key") or ""),
                str(record.get("jira_issue_status") or ""),
                str(record.get("assignee") or ""),
            ]
        ).lower()
        if search_norm in haystack:
            filtered.append(record)
    return filtered


def _record_to_card(record: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(record["record_id"]),
        "title": f"{record['category']}/{record['test_name']}",
        "summary": _truncate(record.get("short_text") or "Falha sem resumo.", 92),
        "meta": _compact_timestamp(record.get("generated_at")),
        "assignee": str(record.get("assignee") or ""),
        "assigneeInitials": _initials(record.get("assignee")),
    }


def _build_board_payload(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lane_groups = {lane: [] for lane in LANES}
    for record in records:
        lane_groups[_lane_from_record(record)].append(_record_to_card(record))
    return [
        {"id": lane, "header": lane, "items": lane_groups[lane]}
        for lane in LANES
    ]


def _persist_board_changes(
    current_records: list[dict[str, Any]],
    updated_containers: list[dict[str, Any]],
) -> bool:
    record_map = {str(record["record_id"]): record for record in current_records}
    changed = False
    for container in updated_containers:
        lane = str(container.get("id") or container.get("header") or "").strip()
        for item in container.get("items") or []:
            record = record_map.get(str(item.get("id") or ""))
            if not record:
                continue
            if _lane_from_record(record) == lane:
                continue
            update_failure_control(record["report_dir"], record["report"], _updates_for_lane(lane))
            changed = True
    return changed


@st.dialog("Editar falha", width="large")
def _failure_edit_dialog(record: dict[str, Any]) -> None:
    report = record.get("report") or {}
    radio_log = report.get("radio_log") or {}

    st.error(record.get("short_text") or "Falha sem resumo.")

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Categoria", record.get("category") or "-")
    top2.metric("Teste", record.get("test_name") or "-")
    top3.metric("Status atual", _lane_from_record(record))
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

        action1, action2 = st.columns(2)
        save = action1.form_submit_button("Salvar")
        close = action2.form_submit_button("Fechar")

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
            st.session_state.pop("failure_modal_record_id", None)
            st.success("Falha atualizada.")
            st.rerun()
        if close:
            st.session_state.pop("failure_modal_record_id", None)
            st.rerun()

    with st.expander("Resumo tecnico da falha", expanded=False):
        st.write(report.get("precondition") or "-")
        st.write(report.get("test_result") or "-")
        st.write(report.get("expected_result") or "-")
        st.write(report.get("actual_results") or "-")
        if radio_log.get("summary"):
            st.write(radio_log.get("summary"))


@st.dialog("Assinar falha", width="small")
def _claim_dialog(record: dict[str, Any]) -> None:
    st.write("Digite seu nome para assinar.")

    with st.form(f"failure_claim_form_{record['record_id']}"):
        assignee_name = st.text_input(
            "Nome",
            key="failure_claim_name_input",
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
                st.session_state.pop("failure_claim_record_id", None)
                st.session_state.pop("failure_claim_name_input", None)
                st.success("Falha assinada.")
                st.rerun()

        if cancel:
            st.session_state.pop("failure_claim_record_id", None)
            st.session_state.pop("failure_claim_name_input", None)
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Controle de Falhas - VWAIT", page_icon="", layout="wide")
    apply_panel_button_theme()
    titulo_painel("Controle de Falhas", "Quadro visual das falhas coletadas.")

    all_records = list_failure_records()
    if not all_records:
        st.info("Nenhuma falha coletada encontrada em KPM/reports.")
        return

    search_text = st.text_input(
        "Buscar falha",
        placeholder="categoria, teste, resumo, issue ou responsavel",
    )
    filtered = _filter_records(all_records, search_text)

    total_mapped = len(filtered)
    total_new = sum(1 for item in filtered if _lane_from_record(item) == LANE_NEW)
    total_sent = sum(1 for item in filtered if _lane_from_record(item) == LANE_SENT)
    total_resolved = sum(1 for item in filtered if _lane_from_record(item) == LANE_RESOLVED)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _kpi_card("Falhas mapeadas", str(total_mapped))
    with c2:
        _kpi_card("Novas", str(total_new))
    with c3:
        _kpi_card("Enviadas", str(total_sent))
    with c4:
        _kpi_card("Resolvidas", str(total_resolved))

    if not filtered:
        st.warning("Nenhuma falha atende a busca atual.")
        return

    st.caption(
        "Clique e arraste o card para mover a falha, clique no card para editar e use a bolinha para assinar o ticket."
    )
    board_payload = _build_board_payload(filtered)
    event = render_failure_board(board_payload, key="failure_control_board")

    last_event_id = st.session_state.get("failure_board_last_event_id")
    event_id = str(event.get("eventId") or "")
    if event_id and event_id != last_event_id:
        st.session_state["failure_board_last_event_id"] = event_id
        event_type = str(event.get("event") or "")
        if event_type == "reorder":
            updated_containers = event.get("containers") or []
            if _persist_board_changes(filtered, updated_containers):
                st.rerun()
        elif event_type == "claim":
            item_id = str(event.get("itemId") or "")
            if item_id:
                record_map = {str(record["record_id"]): record for record in all_records}
                record = record_map.get(item_id)
                if record:
                    st.session_state["failure_claim_record_id"] = item_id
                    st.session_state["failure_claim_name_input"] = (
                        str(record.get("assignee") or "").strip() or _default_claim_name()
                    )
                    st.session_state.pop("failure_modal_record_id", None)
        elif event_type == "click":
            item_id = str(event.get("itemId") or "")
            if item_id:
                st.session_state.pop("failure_claim_record_id", None)
                st.session_state["failure_modal_record_id"] = item_id

    claim_record_id = st.session_state.get("failure_claim_record_id")
    if claim_record_id:
        record_map = {str(record["record_id"]): record for record in all_records}
        record = record_map.get(str(claim_record_id))
        if record:
            _claim_dialog(record)

    modal_record_id = st.session_state.get("failure_modal_record_id")
    if modal_record_id:
        record_map = {str(record["record_id"]): record for record in all_records}
        record = record_map.get(str(modal_record_id))
        if record:
            _failure_edit_dialog(record)


if __name__ == "__main__":
    main()
