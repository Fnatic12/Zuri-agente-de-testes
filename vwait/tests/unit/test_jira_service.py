from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.failures.integrations.jira.config import JiraSettings
from vwait.features.failures.integrations.jira.models import JiraCreateIssueResult
from vwait.features.failures.integrations.jira.service import JiraService


class _FakeClient:
    def __init__(self) -> None:
        self.last_draft = None
        self.last_issue_key = None

    def create_issue(self, draft):
        self.last_draft = draft
        return JiraCreateIssueResult(
            issue_id="10001",
            issue_key="RAD-101",
            issue_url="https://jira.exemplo.com/browse/RAD-101",
            attachment_names=tuple(draft.attachment_paths),
        )

    def get_issue(self, issue_key, fields=("status",)):
        self.last_issue_key = issue_key
        return {"fields": {"status": {"name": "Done"}}}

    def issue_browse_url(self, issue_key):
        return f"https://jira.exemplo.com/browse/{issue_key}"


def test_build_issue_draft_uses_defaults_and_normalizes_labels():
    service = JiraService(
        JiraSettings(
            base_url="https://jira.exemplo.com",
            email="qa@example.com",
            api_token="token",
            project_key="RAD",
            issue_type="Bug",
            default_labels=("vwait", "logs"),
        )
    )

    draft = service.build_issue_draft(
        summary="  Falha  no  radio   apos reboot  ",
        description="Descricao objetiva",
        labels=["Radio Log", "logs", "android auto"],
        attachment_paths=["/tmp/a.txt", "", "/tmp/a.txt"],
    )

    assert draft.project_key == "RAD"
    assert draft.issue_type == "Bug"
    assert draft.summary == "Falha no radio apos reboot"
    assert draft.labels == ("vwait", "logs", "radio-log", "android-auto")
    assert draft.attachment_paths == ("/tmp/a.txt",)


def test_create_issue_delegates_to_client():
    fake_client = _FakeClient()
    service = JiraService(
        JiraSettings(
            base_url="https://jira.exemplo.com",
            email="qa@example.com",
            api_token="token",
            project_key="RAD",
        ),
        client=fake_client,
    )

    draft = service.build_issue_draft(summary="Falha", description="Detalhes")
    result = service.create_issue(draft)

    assert fake_client.last_draft == draft
    assert result.issue_key == "RAD-101"


def test_get_issue_status_delegates_to_client():
    fake_client = _FakeClient()
    service = JiraService(
        JiraSettings(
            base_url="https://jira.exemplo.com",
            email="qa@example.com",
            api_token="token",
            project_key="RAD",
        ),
        client=fake_client,
    )

    status_name = service.get_issue_status("RAD-10")

    assert fake_client.last_issue_key == "RAD-10"
    assert status_name == "Done"
