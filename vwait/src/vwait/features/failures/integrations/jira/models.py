from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class JiraIssueDraft:
    project_key: str
    issue_type: str
    summary: str
    description: str
    labels: tuple[str, ...] = ()
    attachment_paths: tuple[str, ...] = ()
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JiraCreateIssueResult:
    issue_id: str
    issue_key: str
    issue_url: str
    attachment_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class JiraConnectionInfo:
    base_url: str
    account_id: str
    display_name: str
    email: str
    project_key: str = ""
    project_name: str = ""
    issue_types: tuple[str, ...] = ()
