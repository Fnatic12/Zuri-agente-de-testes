from __future__ import annotations

from typing import Any

from ..integrations.jira import JiraError, JiraService
from .update_failure import update_failure_control


def sync_jira_statuses(records: list[dict[str, Any]], service: JiraService | None = None) -> dict[str, Any]:
    jira_service = service or JiraService.from_env()
    if not jira_service.settings.is_configured:
        missing = ", ".join(jira_service.settings.missing_fields)
        raise JiraError(f"Integracao Jira ainda nao configurada: {missing}")

    syncable = [
        record
        for record in records
        if str(record.get("jira_issue_key") or "").strip()
    ]
    if not syncable:
        return {"total": 0, "updated": 0, "errors": []}

    updated = 0
    errors: list[str] = []
    for record in syncable:
        issue_key = str(record.get("jira_issue_key") or "").strip()
        try:
            status_name = jira_service.get_issue_status(issue_key)
            update_failure_control(
                record["report_dir"],
                record["report"],
                {
                    "jira_sync_status": "enviado",
                    "jira_issue_key": issue_key,
                    "jira_issue_status": status_name,
                    "jira_issue_url": jira_service.issue_browse_url(issue_key),
                },
            )
            updated += 1
        except JiraError as exc:
            update_failure_control(
                record["report_dir"],
                record["report"],
                {
                    "jira_sync_status": "erro",
                },
            )
            errors.append(f"{issue_key}: {exc}")

    return {"total": len(syncable), "updated": updated, "errors": errors}
