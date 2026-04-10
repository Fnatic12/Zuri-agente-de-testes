from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from ...application import build_board_payload, persist_board_changes
from .board_component import render_failure_board
from .dialogs import default_claim_name, render_claim_dialog, render_failure_edit_dialog
from .presenters import build_status_workbook
from .state import (
    FAILURE_BOARD_LAST_EVENT_ID_KEY,
    FAILURE_CLAIM_NAME_INPUT_KEY,
    FAILURE_CLAIM_RECORD_ID_KEY,
    FAILURE_MODAL_RECORD_ID_KEY,
    build_record_map,
)


def _handle_board_event(
    event: dict[str, Any],
    *,
    all_records: list[dict[str, Any]],
    filtered_records: list[dict[str, Any]],
) -> None:
    last_event_id = st.session_state.get(FAILURE_BOARD_LAST_EVENT_ID_KEY)
    event_id = str(event.get("eventId") or "")
    if not event_id or event_id == last_event_id:
        return

    st.session_state[FAILURE_BOARD_LAST_EVENT_ID_KEY] = event_id
    event_type = str(event.get("event") or "")
    if event_type == "reorder":
        updated_containers = event.get("containers") or []
        if persist_board_changes(filtered_records, updated_containers):
            st.rerun()
        return

    item_id = str(event.get("itemId") or "")
    if not item_id:
        return

    record = build_record_map(all_records).get(item_id)
    if not record:
        return

    if event_type == "claim":
        st.session_state[FAILURE_CLAIM_RECORD_ID_KEY] = item_id
        st.session_state[FAILURE_CLAIM_NAME_INPUT_KEY] = (
            str(record.get("assignee") or "").strip() or default_claim_name()
        )
        st.session_state.pop(FAILURE_MODAL_RECORD_ID_KEY, None)
    elif event_type == "click":
        st.session_state.pop(FAILURE_CLAIM_RECORD_ID_KEY, None)
        st.session_state[FAILURE_MODAL_RECORD_ID_KEY] = item_id


def _render_active_dialogs(all_records: list[dict[str, Any]]) -> None:
    record_map = build_record_map(all_records)

    claim_record_id = st.session_state.get(FAILURE_CLAIM_RECORD_ID_KEY)
    if claim_record_id:
        record = record_map.get(str(claim_record_id))
        if record:
            render_claim_dialog(record)

    modal_record_id = st.session_state.get(FAILURE_MODAL_RECORD_ID_KEY)
    if modal_record_id:
        record = record_map.get(str(modal_record_id))
        if record:
            render_failure_edit_dialog(record)


def render_failure_board_runtime(
    *,
    all_records: list[dict[str, Any]],
    filtered_records: list[dict[str, Any]],
) -> None:
    st.caption(
        "Clique e arraste o card para mover a falha, clique no card para editar e use a bolinha para assinar o ticket."
    )
    export_filename = f"controle_falhas_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    st.download_button(
        "Extrair status em Excel",
        data=build_status_workbook(filtered_records),
        file_name=export_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Exporta os tickets visiveis na busca atual com a coluna e os status associados.",
    )
    board_payload = build_board_payload(filtered_records)
    event = render_failure_board(board_payload, key="failure_control_board")

    _handle_board_event(event, all_records=all_records, filtered_records=filtered_records)
    _render_active_dialogs(all_records)


__all__ = ["render_failure_board_runtime"]

