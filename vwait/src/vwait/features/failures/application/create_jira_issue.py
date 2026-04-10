from __future__ import annotations

from typing import Any

from ..integrations.jira import JiraCreateIssueResult, JiraService
from .update_failure import update_failure_control


def create_jira_issue_for_record(
    record: dict[str, Any],
    *,
    summary: str,
    description: str,
    labels: list[str] | tuple[str, ...] | None = None,
    attachment_paths: list[str] | tuple[str, ...] | None = None,
    priority: str = "",
    assignee: str = "",
    root_cause: str = "",
    notes: str = "",
    jira_issue_status: str = "",
    service: JiraService | None = None,
) -> JiraCreateIssueResult:
    jira_service = service or JiraService.from_env()
    draft = jira_service.build_issue_draft(
        summary=summary,
        description=description,
        labels=labels or (),
        attachment_paths=attachment_paths or (),
    )
    result = jira_service.create_issue(draft)
    update_failure_control(
        record["report_dir"],
        record["report"],
        {
            "workflow_status": "enviado_para_jira",
            "jira_sync_status": "enviado",
            "priority": priority,
            "jira_issue_key": result.issue_key,
            "jira_issue_status": jira_issue_status,
            "jira_issue_url": result.issue_url,
            "assignee": assignee,
            "root_cause": root_cause,
            "notes": notes,
        },
    )
    return result
