from __future__ import annotations

import re
import unicodedata

from .client import JiraClient
from .config import JiraSettings
from .exceptions import JiraConfigurationError
from .models import JiraConnectionInfo, JiraCreateIssueResult, JiraIssueDraft


def _normalize_summary(value: str) -> str:
    summary = " ".join(str(value or "").split())
    return summary[:255]


def _sanitize_label(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = raw.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().strip()
    ascii_text = re.sub(r"[^a-z0-9._-]+", "-", ascii_text)
    ascii_text = re.sub(r"-{2,}", "-", ascii_text).strip("-")
    return ascii_text[:255]


class JiraService:
    def __init__(self, settings: JiraSettings, client: JiraClient | None = None) -> None:
        self.settings = settings
        self._client = client

    @classmethod
    def from_env(cls) -> "JiraService":
        return cls(JiraSettings.from_env())

    @property
    def is_configured(self) -> bool:
        return self.settings.is_configured

    def test_connection(self, project_key: str = "") -> JiraConnectionInfo:
        return self.client.test_connection(project_key=project_key)

    def list_issue_types(self, project_key: str = "") -> tuple[str, ...]:
        return self.test_connection(project_key=project_key).issue_types

    def build_issue_draft(
        self,
        *,
        summary: str,
        description: str,
        project_key: str = "",
        issue_type: str = "",
        labels: list[str] | tuple[str, ...] | None = None,
        attachment_paths: list[str] | tuple[str, ...] | None = None,
        extra_fields: dict | None = None,
    ) -> JiraIssueDraft:
        effective_project_key = str(project_key or self.settings.project_key or "").strip()
        if not effective_project_key:
            raise JiraConfigurationError("JIRA_PROJECT_KEY nao configurado e nenhum projeto foi informado.")

        effective_issue_type = str(issue_type or self.settings.issue_type or "Task").strip() or "Task"
        effective_summary = _normalize_summary(summary)
        if not effective_summary:
            raise JiraConfigurationError("Resumo do issue Jira nao pode ficar vazio.")

        merged_labels = [*self.settings.default_labels, *(labels or ())]
        normalized_labels = []
        seen_labels = set()
        for label in merged_labels:
            sanitized = _sanitize_label(label)
            if not sanitized or sanitized in seen_labels:
                continue
            seen_labels.add(sanitized)
            normalized_labels.append(sanitized)

        normalized_attachments = []
        seen_paths = set()
        for item in attachment_paths or ():
            path = str(item or "").strip()
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            normalized_attachments.append(path)

        return JiraIssueDraft(
            project_key=effective_project_key,
            issue_type=effective_issue_type,
            summary=effective_summary,
            description=str(description or "").strip(),
            labels=tuple(normalized_labels),
            attachment_paths=tuple(normalized_attachments),
            extra_fields=dict(extra_fields or {}),
        )

    def create_issue(self, draft: JiraIssueDraft) -> JiraCreateIssueResult:
        return self.client.create_issue(draft)

    def get_issue(self, issue_key: str, fields: tuple[str, ...] = ("status",)) -> dict:
        return self.client.get_issue(issue_key, fields=fields)

    def get_issue_status(self, issue_key: str) -> str:
        issue = self.get_issue(issue_key, fields=("status",))
        fields = issue.get("fields") or {}
        status = fields.get("status") or {}
        return str(status.get("name") or "").strip()

    def issue_browse_url(self, issue_key: str) -> str:
        return self.client.issue_browse_url(issue_key)

    @property
    def client(self) -> JiraClient:
        if not self.settings.is_configured:
            missing = ", ".join(self.settings.missing_fields)
            raise JiraConfigurationError(f"Configuracao Jira incompleta: {missing}")
        if self._client is None:
            self._client = JiraClient(self.settings)
        return self._client
