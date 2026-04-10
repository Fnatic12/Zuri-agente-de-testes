from __future__ import annotations

from typing import Any

import streamlit as st


FAILURE_JIRA_CONNECTION_KEY = "failure_control_jira_connection"
FAILURE_JIRA_ISSUE_TYPES_KEY = "failure_control_jira_issue_types"
FAILURE_JIRA_FLASH_KEY = "failure_control_jira_flash"
FAILURE_BOARD_LAST_EVENT_ID_KEY = "failure_board_last_event_id"
FAILURE_CLAIM_RECORD_ID_KEY = "failure_claim_record_id"
FAILURE_CLAIM_NAME_INPUT_KEY = "failure_claim_name_input"
FAILURE_MODAL_RECORD_ID_KEY = "failure_modal_record_id"


def build_record_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(record["record_id"]): record for record in records}


def set_jira_flash_message(message: str, *, level: str = "info", issue_url: str = "") -> None:
    st.session_state[FAILURE_JIRA_FLASH_KEY] = {
        "type": str(level or "info"),
        "message": str(message or ""),
        "issue_url": str(issue_url or ""),
    }


__all__ = [
    "FAILURE_BOARD_LAST_EVENT_ID_KEY",
    "FAILURE_CLAIM_NAME_INPUT_KEY",
    "FAILURE_CLAIM_RECORD_ID_KEY",
    "FAILURE_JIRA_CONNECTION_KEY",
    "FAILURE_JIRA_FLASH_KEY",
    "FAILURE_JIRA_ISSUE_TYPES_KEY",
    "FAILURE_MODAL_RECORD_ID_KEY",
    "build_record_map",
    "set_jira_flash_message",
]

