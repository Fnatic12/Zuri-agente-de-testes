from __future__ import annotations

from datetime import datetime
from typing import Any

from .enums import JIRA_SYNC_STATUS_OPTIONS, PRIORITY_OPTIONS, WORKFLOW_STATUS_OPTIONS
from .models import JsonDict


_RESOLVED_ISSUE_STATUS_MARKERS = (
    "done",
    "closed",
    "resolved",
    "resolvido",
    "fechado",
    "encerrado",
    "concluido",
    "concluido",
    "homologado",
    "finalizado",
)

_DISCARDED_ISSUE_STATUS_MARKERS = (
    "descartado",
    "cancelado",
    "cancelled",
    "duplicado",
    "duplicate",
    "won't fix",
    "wont fix",
    "won't do",
    "wont do",
    "rejected",
    "rejeitado",
    "invalid",
    "invalido",
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_status_token(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def classify_issue_status(value: Any) -> str:
    token = normalize_status_token(value)
    if not token:
        return ""
    if any(marker in token for marker in _DISCARDED_ISSUE_STATUS_MARKERS):
        return "discarded"
    if any(marker in token for marker in _RESOLVED_ISSUE_STATUS_MARKERS):
        return "resolved"
    return "opened"


def default_control_payload(report: JsonDict) -> JsonDict:
    stamp = clean_text(report.get("generated_at")) or datetime.now().isoformat()
    return {
        "workflow_status": "novo",
        "jira_sync_status": "nao_enviado",
        "jira_issue_key": "",
        "jira_issue_url": "",
        "jira_issue_status": "",
        "assignee": "",
        "priority": "media",
        "root_cause": "",
        "notes": "",
        "created_at": stamp,
        "updated_at": stamp,
    }


def _derive_tracking_statuses(merged: JsonDict, base: JsonDict) -> None:
    workflow_status = clean_text(merged.get("workflow_status")).lower()
    jira_sync_status = clean_text(merged.get("jira_sync_status")).lower()
    jira_issue_key = clean_text(merged.get("jira_issue_key"))
    jira_issue_url = clean_text(merged.get("jira_issue_url"))
    jira_issue_status = clean_text(merged.get("jira_issue_status"))

    issue_status_bucket = classify_issue_status(jira_issue_status)
    has_opened_ticket = bool(jira_issue_key or jira_issue_url or issue_status_bucket)

    if issue_status_bucket == "discarded":
        merged["workflow_status"] = "descartado"
        merged["jira_sync_status"] = "enviado"
        return

    if issue_status_bucket == "resolved":
        merged["workflow_status"] = "resolvido"
        merged["jira_sync_status"] = "enviado"
        return

    if has_opened_ticket:
        merged["jira_sync_status"] = "enviado"
        if workflow_status in {
            "",
            base["workflow_status"],
            "novo",
            "triagem",
            "pronto_para_jira",
        }:
            merged["workflow_status"] = "enviado_para_jira"
        return

    if jira_sync_status == "enviado" and workflow_status in {
        "",
        base["workflow_status"],
        "novo",
        "triagem",
        "pronto_para_jira",
    }:
        merged["workflow_status"] = "enviado_para_jira"


def normalize_failure_control(payload: JsonDict, report: JsonDict) -> JsonDict:
    base = default_control_payload(report)
    merged = {**base, **(payload or {})}

    workflow_status = clean_text(merged.get("workflow_status")).lower()
    jira_sync_status = clean_text(merged.get("jira_sync_status")).lower()
    priority = clean_text(merged.get("priority")).lower()

    merged["workflow_status"] = workflow_status if workflow_status in WORKFLOW_STATUS_OPTIONS else base["workflow_status"]
    merged["jira_sync_status"] = (
        jira_sync_status if jira_sync_status in JIRA_SYNC_STATUS_OPTIONS else base["jira_sync_status"]
    )
    merged["priority"] = priority if priority in PRIORITY_OPTIONS else base["priority"]

    for key in (
        "jira_issue_key",
        "jira_issue_url",
        "jira_issue_status",
        "assignee",
        "root_cause",
        "notes",
        "created_at",
        "updated_at",
    ):
        merged[key] = clean_text(merged.get(key))

    _derive_tracking_statuses(merged, base)

    if not merged["created_at"]:
        merged["created_at"] = base["created_at"]
    if not merged["updated_at"]:
        merged["updated_at"] = merged["created_at"]
    return merged
