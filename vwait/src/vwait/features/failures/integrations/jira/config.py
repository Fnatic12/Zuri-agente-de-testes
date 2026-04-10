from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from .env_loader import load_project_env


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


@dataclass(frozen=True)
class JiraSettings:
    base_url: str = ""
    email: str = ""
    api_token: str = ""
    project_key: str = ""
    issue_type: str = "Task"
    default_labels: tuple[str, ...] = ()
    timeout_s: float = 20.0
    verify_ssl: bool = True

    @classmethod
    def from_env(cls) -> "JiraSettings":
        load_project_env()
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "JiraSettings":
        timeout_raw = str(values.get("JIRA_TIMEOUT_S", "20") or "20").strip()
        try:
            timeout_s = max(1.0, float(timeout_raw))
        except ValueError:
            timeout_s = 20.0

        return cls(
            base_url=str(values.get("JIRA_BASE_URL", "") or "").strip().rstrip("/"),
            email=str(values.get("JIRA_EMAIL", "") or "").strip(),
            api_token=str(values.get("JIRA_API_TOKEN", "") or "").strip(),
            project_key=str(values.get("JIRA_PROJECT_KEY", "") or "").strip(),
            issue_type=str(values.get("JIRA_ISSUE_TYPE", "Task") or "Task").strip() or "Task",
            default_labels=_split_csv(values.get("JIRA_DEFAULT_LABELS")),
            timeout_s=timeout_s,
            verify_ssl=_parse_bool(values.get("JIRA_VERIFY_SSL"), default=True),
        )

    @property
    def is_configured(self) -> bool:
        return not self.missing_fields

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing = []
        if not self.base_url:
            missing.append("JIRA_BASE_URL")
        if not self.email:
            missing.append("JIRA_EMAIL")
        if not self.api_token:
            missing.append("JIRA_API_TOKEN")
        return tuple(missing)
