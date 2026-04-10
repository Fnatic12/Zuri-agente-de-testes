from __future__ import annotations

from typing import Any

from .update_failure import update_failure_control


LANE_NEW = "Novas"
LANE_SENT = "Enviadas"
LANE_RESOLVED = "Resolvidas"
LANES = (LANE_NEW, LANE_SENT, LANE_RESOLVED)


def lane_from_record(record: dict[str, Any]) -> str:
    workflow = str(record.get("workflow_status") or "").strip().lower()
    jira_sync = str(record.get("jira_sync_status") or "").strip().lower()
    jira_issue_key = str(record.get("jira_issue_key") or "").strip()
    jira_issue_url = str(record.get("jira_issue_url") or "").strip()
    jira_issue_status = str(record.get("jira_issue_status") or "").strip()
    if workflow in {"resolvido", "descartado"}:
        return LANE_RESOLVED
    if workflow in {"enviado_para_jira", "em_correcao"}:
        return LANE_SENT
    if jira_sync == "enviado" or jira_issue_key or jira_issue_url or jira_issue_status:
        return LANE_SENT
    return LANE_NEW


def updates_for_lane(lane: str) -> dict[str, str]:
    if lane == LANE_SENT:
        return {"workflow_status": "enviado_para_jira", "jira_sync_status": "enviado"}
    if lane == LANE_RESOLVED:
        return {"workflow_status": "resolvido"}
    return {"workflow_status": "novo", "jira_sync_status": "nao_enviado"}


def compact_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    text = text.replace("T", " ")
    if "." in text:
        text = text.split(".", 1)[0]
    return text[:19]


def truncate(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def initials(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "+"
    parts = [part for part in text.replace("_", " ").replace("-", " ").split() if part]
    if not parts:
        return text[:2].upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def filter_failure_records(records: list[dict[str, Any]], search_text: str) -> list[dict[str, Any]]:
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


def record_to_card(record: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(record["record_id"]),
        "title": f"{record['category']}/{record['test_name']}",
        "summary": truncate(record.get("short_text") or "Falha sem resumo.", 92),
        "meta": compact_timestamp(record.get("generated_at")),
        "assignee": str(record.get("assignee") or ""),
        "assigneeInitials": initials(record.get("assignee")),
        "jiraUrl": str(record.get("jira_issue_url") or ""),
        "jiraIssueKey": str(record.get("jira_issue_key") or ""),
    }


def build_board_payload(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lane_groups = {lane: [] for lane in LANES}
    for record in records:
        lane_groups[lane_from_record(record)].append(record_to_card(record))
    return [
        {"id": lane, "header": lane, "items": lane_groups[lane]}
        for lane in LANES
    ]


def ticket_export_rows(records: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for record in records:
        rows.append(
            [
                str(record.get("record_id") or ""),
                lane_from_record(record),
                str(record.get("category") or ""),
                str(record.get("test_name") or ""),
                str(record.get("short_text") or ""),
                str(record.get("workflow_status") or ""),
                str(record.get("jira_sync_status") or ""),
                str(record.get("jira_issue_key") or ""),
                str(record.get("jira_issue_status") or ""),
                str(record.get("assignee") or ""),
                str(record.get("priority") or ""),
                str(record.get("resultado_final") or ""),
                str(record.get("log_capture_status") or ""),
                compact_timestamp(record.get("generated_at")),
                compact_timestamp(record.get("updated_at")),
                str(record.get("jira_issue_url") or ""),
            ]
        )
    return rows


def persist_board_changes(
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
            if lane_from_record(record) == lane:
                continue
            update_failure_control(record["report_dir"], record["report"], updates_for_lane(lane))
            changed = True
    return changed
